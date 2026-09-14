"""Unit tests for the cookiemunch client. No network — the HTTP transport is mocked.

Written with ``unittest.TestCase`` so it runs under both ``pytest`` and
``python -m unittest``.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List, Optional

from cookiemunch import CookieMunch, CookieMunchApiError, ConsentChoices
from cookiemunch._transport import HttpResponse
from cookiemunch.types import camel_to_snake


class RecordingTransport:
    """A fake transport that records requests and returns queued responses."""

    def __init__(self, responses: Optional[List[HttpResponse]] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._responses = list(responses or [])
        self.default = HttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=b"{}",
        )

    def __call__(self, method, url, headers, body):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": json.loads(body.decode()) if body else None,
            }
        )
        return self._responses.pop(0) if self._responses else self.default

    @property
    def last(self) -> Dict[str, Any]:
        return self.calls[-1]


def _json_response(payload: Any, status: int = 200) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload).encode(),
    )


class AuthHeaderTests(unittest.TestCase):
    def test_bearer_and_x_api_key_headers_are_sent(self):
        tr = RecordingTransport([_json_response({"orgId": "org_1", "plan": "pro", "keyPrefix": "fck_ab"})])
        cm = CookieMunch(api_key="fck_secret123", base_url="https://api.example.com", transport=tr)
        cm.me()
        headers = tr.last["headers"]
        self.assertEqual(headers["Authorization"], "Bearer fck_secret123")
        self.assertEqual(headers["X-API-Key"], "fck_secret123")

    def test_base_url_v1_prefix(self):
        tr = RecordingTransport([_json_response({})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com/", transport=tr)
        cm.me()
        # Trailing slash on base_url is stripped; /v1 prefix appended.
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/me")

    def test_empty_api_key_rejected(self):
        with self.assertRaises(ValueError):
            CookieMunch(api_key="", transport=RecordingTransport())


class GetTests(unittest.TestCase):
    def test_me_maps_camelcase_to_snake(self):
        tr = RecordingTransport([_json_response({"orgId": "org_9", "plan": "scale", "keyPrefix": "fck_zz"})])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        ident = cm.me()
        self.assertEqual(ident.org_id, "org_9")
        self.assertEqual(ident.plan, "scale")
        self.assertEqual(ident.key_prefix, "fck_zz")
        self.assertEqual(tr.last["method"], "GET")

    def test_sites_list_returns_dataclasses(self):
        tr = RecordingTransport(
            [
                _json_response(
                    [
                        {"cbid": "abc", "orgId": "org_1", "domain": "a.com"},
                        {"cbid": "def", "orgId": "org_1", "domain": "b.com"},
                    ]
                )
            ]
        )
        cm = CookieMunch(api_key="fck_x", transport=tr)
        sites = cm.sites.list()
        self.assertEqual(len(sites), 2)
        self.assertEqual(sites[0].cbid, "abc")
        self.assertEqual(sites[1].domain, "b.com")
        self.assertTrue(tr.last["url"].endswith("/v1/sites"))

    def test_consent_receipt_path_encoding_and_query(self):
        tr = RecordingTransport([_json_response({"ok": True})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.consent.receipt("site/1", "stamp 42")
        self.assertEqual(
            tr.last["url"],
            "https://api.example.com/v1/sites/site%2F1/receipt/stamp%2042",
        )

    def test_snippet_query_params(self):
        tr = RecordingTransport([_json_response({"snippet": "<script>", "cbid": "c1"})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        snip = cm.sites.snippet("c1", blocking_mode="manual", culture="fr")
        self.assertIn("blockingmode=manual", tr.last["url"])
        self.assertIn("culture=fr", tr.last["url"])
        self.assertEqual(snip.cbid, "c1")

    def test_stats_omits_none_query_params(self):
        tr = RecordingTransport([_json_response([])])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.consent.stats("c1", from_=1000)
        self.assertIn("from=1000", tr.last["url"])
        self.assertNotIn("to=", tr.last["url"])


class PostTests(unittest.TestCase):
    def test_log_consent_public_ingest(self):
        tr = RecordingTransport([HttpResponse(status=204, headers={}, body=b"")])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        result = cm.log_consent(
            cbid="c1",
            choices=ConsentChoices(preferences=True, statistics=True, marketing=False),
            method="explicit",
            url="https://site.com/",
            stamp="stamp1",
            utc=1234567890,
            region="US-CA",
        )
        self.assertIsNone(result)  # 204 -> None
        call = tr.last
        self.assertEqual(call["method"], "POST")
        # Public ingest uses /api/v1/consent, NOT the /v1 authed prefix.
        self.assertEqual(call["url"], "https://api.example.com/api/v1/consent")
        self.assertEqual(call["headers"]["X-CookieMunch-Region"], "US-CA")
        body = call["body"]
        self.assertEqual(body["cbid"], "c1")
        self.assertEqual(body["stamp"], "stamp1")
        self.assertEqual(body["utc"], 1234567890)
        self.assertEqual(body["ver"], 1)
        self.assertEqual(
            body["choices"], {"preferences": True, "statistics": True, "marketing": False}
        )

    def test_log_consent_omits_subject_id_when_absent(self):
        tr = RecordingTransport([HttpResponse(status=204, headers={}, body=b"")])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.log_consent(cbid="c1", choices={"marketing": True})
        self.assertNotIn("subjectId", tr.last["body"])

    def test_log_consent_includes_subject_id_when_set(self):
        tr = RecordingTransport([HttpResponse(status=204, headers={}, body=b"")])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.log_consent(cbid="c1", choices={"marketing": True}, subject_id="user-42")
        self.assertEqual(tr.last["body"]["subjectId"], "user-42")

    def test_log_consent_accepts_dict_choices_and_autofills(self):
        tr = RecordingTransport([HttpResponse(status=204, headers={}, body=b"")])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.log_consent(cbid="c1", choices={"marketing": True})
        body = tr.last["body"]
        self.assertEqual(
            body["choices"], {"preferences": False, "statistics": False, "marketing": True}
        )
        self.assertTrue(body["stamp"])  # auto-generated
        self.assertIsInstance(body["utc"], int)

    def test_sites_create_post_body(self):
        tr = RecordingTransport([_json_response({"cbid": "new", "orgId": "o", "domain": "x.com"})])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        site = cm.sites.create(domain="x.com")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["body"], {"domain": "x.com"})
        self.assertEqual(site.cbid, "new")

    def test_dsar_create_camel_body(self):
        tr = RecordingTransport([_json_response({"request": {"id": "d1"}}, status=201)])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        out = cm.dsar.create(type="access", subject_email="a@b.com", regulation="gdpr")
        self.assertEqual(tr.last["body"]["subjectEmail"], "a@b.com")
        self.assertEqual(out["request"]["id"], "d1")

    def test_delete_returns_none_on_204(self):
        tr = RecordingTransport([HttpResponse(status=204, headers={}, body=b"")])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        self.assertIsNone(cm.sites.delete("c1"))
        self.assertEqual(tr.last["method"], "DELETE")


class ErrorMappingTests(unittest.TestCase):
    def test_non_2xx_raises_with_error_field(self):
        tr = RecordingTransport(
            [_json_response({"error": "cbid already claimed", "code": "conflict"}, status=409)]
        )
        cm = CookieMunch(api_key="fck_x", transport=tr)
        with self.assertRaises(CookieMunchApiError) as ctx:
            cm.sites.create(domain="dup.com")
        err = ctx.exception
        self.assertEqual(err.status, 409)
        self.assertIn("cbid already claimed", str(err))
        self.assertEqual(err.code, "conflict")

    def test_non_json_error_body_keeps_default_message(self):
        tr = RecordingTransport(
            [HttpResponse(status=500, headers={"Content-Type": "text/html"}, body=b"<h1>oops</h1>")]
        )
        cm = CookieMunch(api_key="fck_x", transport=tr)
        with self.assertRaises(CookieMunchApiError) as ctx:
            cm.me()
        self.assertEqual(ctx.exception.status, 500)
        self.assertIn("status 500", str(ctx.exception))
        self.assertEqual(ctx.exception.body, "<h1>oops</h1>")

    def test_401_maps(self):
        tr = RecordingTransport([_json_response({"error": "authentication required"}, status=401)])
        cm = CookieMunch(api_key="fck_bad", transport=tr)
        with self.assertRaises(CookieMunchApiError) as ctx:
            cm.sites.list()
        self.assertEqual(ctx.exception.status, 401)


class DecoderTests(unittest.TestCase):
    def test_camel_to_snake(self):
        self.assertEqual(camel_to_snake("orgId"), "org_id")
        self.assertEqual(camel_to_snake("keyPrefix"), "key_prefix")
        self.assertEqual(camel_to_snake("OptInImplied"), "opt_in_implied")
        self.assertEqual(camel_to_snake("Date"), "date")
        self.assertEqual(camel_to_snake("TypeOptInPref"), "type_opt_in_pref")
        self.assertEqual(camel_to_snake("cbid"), "cbid")

    def test_consent_day_pascalcase_decoding(self):
        tr = RecordingTransport(
            [
                _json_response(
                    [
                        {
                            "Date": "2026-01-01",
                            "OptIn": 10,
                            "OptOut": 2,
                            "OptInImplied": 3,
                            "Countries": {"US": 5},
                        }
                    ]
                )
            ]
        )
        cm = CookieMunch(api_key="fck_x", transport=tr)
        days = cm.consent.stats("c1")
        self.assertEqual(days[0].date, "2026-01-01")
        self.assertEqual(days[0].opt_in, 10)
        self.assertEqual(days[0].opt_in_implied, 3)
        self.assertEqual(days[0].countries, {"US": 5})


if __name__ == "__main__":
    unittest.main()

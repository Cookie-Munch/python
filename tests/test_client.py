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


class NewOperationsTests(unittest.TestCase):
    """Pins method+path+body for the 13 operations added in commit 1c08ee6."""

    def test_org_get(self):
        tr = RecordingTransport([_json_response({"id": "org_1", "name": "Acme", "plan": "pro", "logoUrl": None})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        org = cm.org.get()
        self.assertEqual(tr.last["method"], "GET")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/org")
        self.assertEqual(org.id, "org_1")

    def test_org_update_logo_url_none_sends_json_null(self):
        tr = RecordingTransport([_json_response({"id": "org_1", "name": "Acme", "plan": "pro", "logoUrl": None})])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.org.update(logo_url=None)
        self.assertEqual(tr.last["method"], "PATCH")
        self.assertIn("logoUrl", tr.last["body"])
        self.assertIsNone(tr.last["body"]["logoUrl"])

    def test_org_update_omitted_logo_url_sends_no_key(self):
        tr = RecordingTransport([_json_response({"id": "org_1", "name": "Acme", "plan": "pro", "logoUrl": None})])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.org.update(name="New Name")
        self.assertEqual(tr.last["body"], {"name": "New Name"})
        self.assertNotIn("logoUrl", tr.last["body"])

    def test_audit_query_param(self):
        tr = RecordingTransport([_json_response({"entries": []})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.audit(limit=50)
        self.assertEqual(tr.last["method"], "GET")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/audit?limit=50")

    def test_audit_omits_limit_when_absent(self):
        tr = RecordingTransport([_json_response({"entries": []})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.audit()
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/audit")

    def test_assets_upload(self):
        tr = RecordingTransport([_json_response({"url": "https://cdn.example.com/x.png"})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        result = cm.assets.upload(data="Zm9v", content_type="image/png")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/assets")
        self.assertEqual(tr.last["body"], {"data": "Zm9v", "contentType": "image/png"})
        self.assertEqual(result["url"], "https://cdn.example.com/x.png")

    def test_keys_roll(self):
        tr = RecordingTransport([_json_response({"key": "fck_new", "prefix": "fck_ab"})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.keys.roll("fck_ab")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/keys/fck_ab/roll")

    def test_keys_update_sends_only_provided_fields(self):
        tr = RecordingTransport([_json_response({"ok": True})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.keys.update("fck_ab", name="renamed")
        self.assertEqual(tr.last["method"], "PATCH")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/keys/fck_ab")
        self.assertEqual(tr.last["body"], {"name": "renamed"})

    def test_keys_update_scopes_and_cbids(self):
        tr = RecordingTransport([_json_response({"ok": True})])
        cm = CookieMunch(api_key="fck_x", transport=tr)
        cm.keys.update("fck_ab", scopes=["sites:read"], cbids=["c1"])
        self.assertEqual(tr.last["body"], {"scopes": ["sites:read"], "cbids": ["c1"]})

    def test_webhooks_roll_secret(self):
        tr = RecordingTransport([_json_response({"secret": "whsec_new"})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.webhooks.roll_secret("wh_1")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/webhooks/wh_1/roll")

    def test_webhooks_test(self):
        tr = RecordingTransport([_json_response({"ok": True, "status": 200})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        result = cm.webhooks.test("wh_1")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/webhooks/wh_1/test")
        self.assertTrue(result["ok"])

    def test_webhooks_dead_letters(self):
        tr = RecordingTransport([_json_response({"deadLetters": []})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.webhooks.dead_letters()
        self.assertEqual(tr.last["method"], "GET")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/webhooks/dead-letters")

    def test_webhooks_replay_dead_letter(self):
        tr = RecordingTransport([_json_response({"ok": True})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.webhooks.replay_dead_letter("dl_1")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/webhooks/dead-letters/dl_1/replay")

    def test_preferences_get(self):
        tr = RecordingTransport([_json_response({"subjectId": "sub_1", "purposes": {}})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.preferences.get("sub 1")
        self.assertEqual(tr.last["method"], "GET")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/preferences/sub%201")

    def test_dsar_erase(self):
        tr = RecordingTransport([_json_response({"erased": 1, "encryptionEnabled": True, "request": {"id": "d1"}})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.dsar.erase("d1", "cbid1", "stamp1")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/dsar/d1/erase")
        self.assertEqual(tr.last["body"], {"cbid": "cbid1", "stamp": "stamp1"})

    def test_dsar_export(self):
        tr = RecordingTransport([_json_response({"records": [], "count": 0, "request": {"id": "d1"}})])
        cm = CookieMunch(api_key="fck_x", base_url="https://api.example.com", transport=tr)
        cm.dsar.export("d1", "cbid1", "stamp1")
        self.assertEqual(tr.last["method"], "POST")
        self.assertEqual(tr.last["url"], "https://api.example.com/v1/dsar/d1/export")
        self.assertEqual(tr.last["body"], {"cbid": "cbid1", "stamp": "stamp1"})


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

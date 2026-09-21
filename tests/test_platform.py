"""The shapes that matter on the platform surface: what is sent, and what comes back."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List

from cookiemunch import CookieMunch
from cookiemunch._transport import HttpResponse


class Recorder:
    def __init__(self, body: bytes = b"{}", content_type: str = "application/json", status: int = 200) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._response = HttpResponse(status=status, headers={"Content-Type": content_type}, body=body)

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "body": json.loads(body) if body else None})
        return self._response


def client(rec: Recorder) -> CookieMunch:
    return CookieMunch("fck_test", base_url="https://api.example.com", transport=rec)


class ResellerTest(unittest.TestCase):
    def test_deprovision_suspends_by_default_and_purges_only_when_asked(self) -> None:
        rec = Recorder(status=204, body=b"")
        c = client(rec)
        c.reseller.deprovision("c1")
        c.reseller.deprovision("c1", purge=True)
        self.assertEqual(rec.calls[0]["url"], "https://api.example.com/v1/reseller/customers/c1")
        self.assertEqual(rec.calls[1]["url"], "https://api.example.com/v1/reseller/customers/c1?purge=true")

    def test_update_distinguishes_clearing_routing_from_leaving_it(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.reseller.update("c1", status="suspended")
        c.reseller.update("c1", dsar_routing=None)
        self.assertEqual(rec.calls[0]["body"], {"status": "suspended"})
        self.assertEqual(rec.calls[1]["body"], {"dsarRouting": None})

    def test_create_sends_camel_case(self) -> None:
        rec = Recorder()
        client(rec).reseller.create(name="Acme", mint_key=True, key_scopes=["sites:read"], owner_email="o@x.com")
        self.assertEqual(
            rec.calls[0]["body"],
            {"name": "Acme", "ownerEmail": "o@x.com", "mintKey": True, "keyScopes": ["sites:read"]},
        )


class KeysTest(unittest.TestCase):
    def test_issue_sends_least_privilege_fields(self) -> None:
        rec = Recorder()
        client(rec).keys.issue(name="agency", scopes=["consent:read"], cbids=["cb_shop"], expires_in_days=30)
        self.assertEqual(
            rec.calls[0]["body"],
            {"name": "agency", "scopes": ["consent:read"], "cbids": ["cb_shop"], "expiresInDays": 30},
        )


class TextResponsesTest(unittest.TestCase):
    def test_policy_is_markdown_with_options_in_the_query(self) -> None:
        rec = Recorder(body=b"# Privacy policy", content_type="text/markdown")
        md = client(rec).sites.policy("s1", contact_email="dpo@x.com", jurisdictions=["gdpr", "ccpa"])
        self.assertEqual(md, "# Privacy policy")
        self.assertEqual(
            rec.calls[0]["url"],
            "https://api.example.com/v1/sites/s1/policy?contactEmail=dpo%40x.com&jurisdictions=gdpr%2Cccpa",
        )

    def test_ropa_export_and_dsar_notice_are_text(self) -> None:
        self.assertEqual(client(Recorder(body=b"a,b\n", content_type="text/csv")).ropa.export_csv(), "a,b\n")
        self.assertEqual(client(Recorder(body=b"Dear subject", content_type="text/plain")).dsar.response("d1"), "Dear subject")


class GrowthTest(unittest.TestCase):
    def test_identifiers_travel_in_the_body_never_the_url(self) -> None:
        rec = Recorder()
        ids = [{"space": "email_sha256", "value": "abc"}]
        c = client(rec)
        c.identity.resolve(ids)
        c.vault.current(ids)
        c.profile.activate(ids, "marketing")
        for call in rec.calls:
            self.assertEqual(call["method"], "POST")
            self.assertNotIn("abc", call["url"])
            self.assertEqual(call["body"]["identifiers"], ids)


if __name__ == "__main__":
    unittest.main()

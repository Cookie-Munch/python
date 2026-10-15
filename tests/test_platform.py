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


class OrgMailProviderTest(unittest.TestCase):
    def test_get_set_test_remove(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.org.mail_provider()
        c.org.set_mail_provider(
            provider="ses", from_email="p@acme.com", from_name="Acme", secret="aws-secret",
            ses={"region": "eu-west-1", "accessKeyId": "AKIAEXAMPLE12345"},
        )
        c.org.test_mail_provider("me@acme.com")
        c.org.test_mail_provider()
        rec._response = rec._response.__class__(status=204, headers={}, body=b"")
        c.org.remove_mail_provider()
        self.assertEqual(
            [(x["method"], x["url"]) for x in rec.calls],
            [
                ("GET", "https://api.example.com/v1/org/mail-provider"),
                ("PUT", "https://api.example.com/v1/org/mail-provider"),
                ("POST", "https://api.example.com/v1/org/mail-provider/test"),
                ("POST", "https://api.example.com/v1/org/mail-provider/test"),
                ("DELETE", "https://api.example.com/v1/org/mail-provider"),
            ],
        )
        self.assertEqual(
            rec.calls[1]["body"],
            {"provider": "ses", "fromEmail": "p@acme.com", "fromName": "Acme", "secret": "aws-secret",
             "ses": {"region": "eu-west-1", "accessKeyId": "AKIAEXAMPLE12345"}},
        )
        self.assertEqual(rec.calls[2]["body"], {"to": "me@acme.com"})
        self.assertEqual(rec.calls[3]["body"], {})


class RightsPageDomainsTest(unittest.TestCase):
    def test_list_add_verify_remove(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.rights_page.list_domains("s 1")
        c.rights_page.add_domain("s", "privacy.acme.com")
        c.rights_page.verify_domain("s", "datenschutz.bücher.de")
        c.rights_page.remove_domain("s", "privacy.acme.com")
        base = "https://api.example.com/v1/sites"
        self.assertEqual([x["method"] for x in rec.calls], ["GET", "POST", "POST", "DELETE"])
        self.assertEqual(rec.calls[0]["url"], f"{base}/s%201/rights-page/domains")
        self.assertEqual(rec.calls[1]["body"], {"hostname": "privacy.acme.com"})
        self.assertEqual(rec.calls[2]["url"], f"{base}/s/rights-page/domains/datenschutz.b%C3%BCcher.de/verify")
        self.assertEqual(rec.calls[3]["url"], f"{base}/s/rights-page/domains/privacy.acme.com")


class RightsCaptchaTest(unittest.TestCase):
    def test_site_and_org_default(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.rights_captcha.get("s 1")
        c.rights_captcha.set("s1", mode="own", provider="recaptcha_v3", site_key="k-12345678", secret="sec", min_score=0.7)
        c.rights_captcha.remove("s1")
        c.org.rights_captcha()
        c.org.set_rights_captcha(mode="off")
        c.org.remove_rights_captcha()
        self.assertEqual(
            [(x["method"], x["url"]) for x in rec.calls],
            [
                ("GET", "https://api.example.com/v1/sites/s%201/rights-captcha"),
                ("PUT", "https://api.example.com/v1/sites/s1/rights-captcha"),
                ("DELETE", "https://api.example.com/v1/sites/s1/rights-captcha"),
                ("GET", "https://api.example.com/v1/org/rights-captcha"),
                ("PUT", "https://api.example.com/v1/org/rights-captcha"),
                ("DELETE", "https://api.example.com/v1/org/rights-captcha"),
            ],
        )
        self.assertEqual(rec.calls[1]["body"], {"mode": "own", "provider": "recaptcha_v3", "siteKey": "k-12345678", "secret": "sec", "minScore": 0.7})
        self.assertEqual(rec.calls[4]["body"], {"mode": "off"})


class RightsIdentityTest(unittest.TestCase):
    def test_site_and_org_default(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.rights_identity.get("s 1")
        c.rights_identity.set("s1", type="clerk", issuer="https://clerk.acme.example", authorized_parties=["https://www.acme.example"], trust_email_claim=True)
        c.rights_identity.remove("s1")
        c.org.rights_identity()
        c.org.set_rights_identity(type="oidc_jwt", issuer="https://id.acme.example", jwks_url="https://id.acme.example/keys", audience="acme-rights", session_cookie_name="sid")
        c.org.remove_rights_identity()
        self.assertEqual(
            [(x["method"], x["url"]) for x in rec.calls],
            [
                ("GET", "https://api.example.com/v1/sites/s%201/rights-identity"),
                ("PUT", "https://api.example.com/v1/sites/s1/rights-identity"),
                ("DELETE", "https://api.example.com/v1/sites/s1/rights-identity"),
                ("GET", "https://api.example.com/v1/org/rights-identity"),
                ("PUT", "https://api.example.com/v1/org/rights-identity"),
                ("DELETE", "https://api.example.com/v1/org/rights-identity"),
            ],
        )
        self.assertEqual(rec.calls[1]["body"], {"type": "clerk", "issuer": "https://clerk.acme.example", "authorizedParties": ["https://www.acme.example"], "trustEmailClaim": True})
        self.assertEqual(rec.calls[4]["body"], {"type": "oidc_jwt", "issuer": "https://id.acme.example", "jwksUrl": "https://id.acme.example/keys", "audience": "acme-rights", "sessionCookieName": "sid"})


class ExecutorWebhookTest(unittest.TestCase):
    def test_webhook_check_deliveries_and_dry_runs(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.fulfillment.test_executor_webhook("ex 1", {"x-sig": "v1,abc"}, '{"a":1}')
        c.fulfillment.executor_webhook_deliveries("ex 1")
        c.fulfillment.connect_executor("crm", "https://crm.example", "sk_12345678", {"open": {}}, dry_run=True)
        c.fulfillment.update_executor("ex 1", auto=False, dry_run=True)
        c.fulfillment.update_executor("ex 1", auto=False)
        self.assertEqual(
            [(x["method"], x["url"]) for x in rec.calls],
            [
                ("POST", "https://api.example.com/v1/dsar/executors/ex%201/webhook/test"),
                ("GET", "https://api.example.com/v1/dsar/executors/ex%201/webhook/deliveries"),
                ("POST", "https://api.example.com/v1/dsar/executors?dryRun=1"),
                ("PATCH", "https://api.example.com/v1/dsar/executors/ex%201?dryRun=1"),
                ("PATCH", "https://api.example.com/v1/dsar/executors/ex%201"),
            ],
        )
        self.assertEqual(rec.calls[0]["body"], {"headers": {"x-sig": "v1,abc"}, "body": '{"a":1}'})


class DeclaredCookiesTest(unittest.TestCase):
    """Numestri F-01: per-language purposes, and dry_run on every declaration write."""

    def test_purposes_and_dry_run(self) -> None:
        rec = Recorder()
        c = client(rec)
        c.sites.declare_cookie("cb", "sid", "necessary", "Signed in.", purposes={"es": "Sesión."})
        c.sites.declare_cookie("cb", "sid", "necessary", "Signed in.", dry_run=True)
        c.sites.declare_cookies("cb", [{"name": "a", "category": "necessary", "purpose": "A"}], replace=True, dry_run=True)
        out = c.sites.undeclare_cookie("cb", "sid", dry_run=True)
        self.assertEqual(rec.calls[0]["url"], "https://api.example.com/v1/sites/cb/cookies/sid")
        self.assertEqual(rec.calls[0]["body"], {"category": "necessary", "purpose": "Signed in.", "purposes": {"es": "Sesión."}})
        self.assertEqual(rec.calls[1]["url"], "https://api.example.com/v1/sites/cb/cookies/sid?dryRun=1")
        self.assertEqual(rec.calls[2]["url"], "https://api.example.com/v1/sites/cb/cookies?dryRun=1")
        self.assertEqual(rec.calls[2]["body"]["replace"], True)
        self.assertEqual((rec.calls[3]["method"], rec.calls[3]["url"]), ("DELETE", "https://api.example.com/v1/sites/cb/cookies/sid?dryRun=1"))
        self.assertEqual(out, {})

    def test_undeclare_without_dry_run_returns_none(self) -> None:
        rec = Recorder(status=204, body=b"")
        self.assertIsNone(client(rec).sites.undeclare_cookie("cb", "sid"))
        self.assertEqual(rec.calls[0]["url"], "https://api.example.com/v1/sites/cb/cookies/sid")

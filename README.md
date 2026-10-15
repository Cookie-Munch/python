# cookiemunch — Python SDK

A small, typed Python client for the **Cookie Munch Developer API** — the
Consent Management Platform (a Cookiebot / CookieYes alternative). It mirrors the
official TypeScript SDK (`@cookiemunch/sdk`): construct it with an API key and the org
is derived server-side, so you never pass an `orgId`.

- **Zero required dependencies.** Uses only the Python standard library (`urllib`), so
  it installs anywhere. The HTTP transport is injectable if you'd rather use `httpx`.
- **Type-hinted** dataclasses for the main entities.
- Python **3.10+**.

## Install

```bash
pip install cookiemunch
# from a checkout:
pip install -e .
```

## Usage

```python
from cookiemunch import CookieMunch, ConsentChoices

cm = CookieMunch(api_key="fck_your_key", base_url="https://api.cookiemunch.net")

# Identity / bootstrap
me = cm.me()
print(me.org_id, me.plan)

# Sites
sites = cm.sites.list()
site = cm.sites.create(domain="example.com")
config = cm.sites.get_config(site.cbid)
cm.sites.put_config(site.cbid, {"consentMode": {"enabled": True}})
# Consent-button parity: is "Accept all" pushed harder than "Reject all"? Nothing is saved.
lint = cm.sites.lint_config(site.cbid, {"banner": {"type": "accept-decline"}})
for f in lint["designWarnings"]:
    print(f["severity"], f["code"], f["fix"])
snippet = cm.sites.snippet(site.cbid, blocking_mode="auto")

# Consent analytics + audit
stats = cm.consent.stats(site.cbid, from_=1735689600000)
log = cm.consent.log(site.cbid, limit=100)
csv_text = cm.consent.export(site.cbid)          # raw CSV string
receipt = cm.consent.receipt(site.cbid, "stamp") # signed ISO-27560 receipt

# Governance
dsars = cm.dsar.list()
cm.dsar.create(type="access", subject_email="user@example.com", regulation="gdpr")
vendors = cm.vendors.list()
ropa = cm.ropa.list()

# Banners, brand kits, members, keys, webhooks, usage ...
banners = cm.banners.list()
cm.usage()
```

### Logging consent from a server (public ingest)

App/server integrations that capture consent outside the browser embed can log a
record directly to the **public** ingest endpoint (`POST /api/v1/consent`, no auth):

```python
cm.log_consent(
    cbid="your_cbid",
    choices=ConsentChoices(preferences=True, statistics=True, marketing=False),
    method="explicit",           # or "implied"
    url="https://example.com/",
    region="US-CA",              # optional; sent as X-CookieMunch-Region
    # stamp and utc are auto-generated when omitted
)
```

### Errors

Any non-2xx response raises `CookieMunchApiError`, carrying `.status`, `.code`
(the server's machine-readable code, when present), and the raw `.body`:

```python
from cookiemunch import CookieMunchApiError

try:
    cm.sites.get("missing")
except CookieMunchApiError as e:
    print(e.status, e.code, e)
```

### Custom / mocked transport

The HTTP layer is a plain callable `(method, url, headers, body) -> HttpResponse`,
which makes testing without a network trivial and lets you swap in another client:

```python
from cookiemunch import CookieMunch
from cookiemunch._transport import HttpResponse

def fake(method, url, headers, body):
    return HttpResponse(status=200, headers={"Content-Type": "application/json"}, body=b'{"orgId":"o"}')

cm = CookieMunch(api_key="fck_test", transport=fake)
```

## Resource surface

`me()`, `usage()`, `audit(limit=None)`, `log_consent(...)`, plus:

- **Consent platform** — `sites` · `consent` · `dsar` · `vendors` · `ropa` · `brand_kits` ·
  `preferences` · `members` · `keys` · `webhooks` · `banners` · `org` · `assets`
- **Privacy platform** — `identity` · `vault` · `profile` · `subscriptions` ·
  `assessments` · `discovery` · `ai` · `fulfillment` · `regulatory`
- **Rights page** — `rights_page`: the page (`get`, `put`, `patch`, `dry_run`, `get_published`, `publish`, `versions`, `rollback`; pass `base_updated_at=` to `publish`/`rollback` so only the draft you read goes live, and note a rollback replaces the draft) and its custom domains (`list_domains`, `add_domain`, `verify_domain`, `remove_domain`)
- **Rights links** — `rights_links.create(...)`: a signed, single-use link to the rights page for a signed-in person
- **Mail for rights requests** — `org.mail_provider`, `set_mail_provider`, `test_mail_provider`, `remove_mail_provider` (no code mail until a test succeeds; there is no shared sender)
- **Rights-page captcha** — `rights_captcha.get`, `set`, `remove` per site; the org default via `org.rights_captcha`, `set_rights_captcha`, `remove_rights_captcha`
- **Sign-in verification for rights requests** — `rights_identity.get`, `set(cbid, type=, issuer=, jwks_url=, audience=, authorized_parties=, email_claim=, email_verified_claim=, session_cookie_name=)`, `remove` per site; the org default via `org.rights_identity`, `set_rights_identity`, `remove_rights_identity`. Connect Clerk, Atlas or any JWKS issuer (`oidc_jwt`): a signed-in visitor is verified by their session, with no code mail
- **Resellers** — `reseller`

Every operation of the `/v1` Developer API is reachable. `tests/test_parity.py` checks
that against `sdks/operations.json`, which is generated from the server's OpenAPI
document — so a new endpoint fails this suite until the SDK implements it.

Identity, vault and profile reads are `POST`s on purpose: a person's identifiers travel
in the request body, never in a URL where logs and proxies would keep them.

## Development

```bash
python3 -m pytest -q      # or: python3 -m unittest
```

## License

MIT

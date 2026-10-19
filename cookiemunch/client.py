"""The Cookie Munch Developer API client.

``CookieMunch`` mirrors the reference TypeScript client (``@cookiemunch/sdk``): a
Bearer-authenticated client whose org is derived server-side from the API key, with
resource groups (``sites``, ``consent``, ``dsar``, ``vendors``, ``ropa``,
``brand_kits``, ``preferences``, ``members``, ``keys``, ``webhooks``, ``banners``)
that map one-to-one onto the ``/v1`` surface.

It also exposes :meth:`CookieMunch.log_consent`, a helper for the PUBLIC consent
ingest endpoint (``POST /api/v1/consent``) that application integrations need.
"""

from __future__ import annotations

import json as _json
import time
import urllib.parse
import uuid
from typing import Any, Dict, List, Mapping, Optional, Union

from . import types as t
from ._transport import HttpResponse, Transport, urllib_transport
from .errors import CookieMunchApiError

__all__ = ["CookieMunch"]

DEFAULT_BASE_URL = "https://api.cookiemunch.net"
_SDK_VERSION = "0.1.0"

_JSONDict = Dict[str, Any]
_ChoicesLike = Union[t.ConsentChoices, Mapping[str, bool]]


_UNSET: Any = object()
"""Sentinel: distinguishes 'clear this field' (None) from 'leave it alone'."""


def _num(v: Optional[float]) -> Optional[str]:
    """A number for a query string: ``30`` not ``30.0``."""
    if v is None:
        return None
    return str(int(v)) if float(v).is_integer() else str(round(float(v), 3))


def _qs(params: Optional[Mapping[str, Any]]) -> str:
    if not params:
        return ""
    pairs = [(k, v) for k, v in params.items() if v is not None]
    if not pairs:
        return ""
    return "?" + urllib.parse.urlencode(pairs)


class CookieMunch:
    """Typed REST client for the Cookie Munch Developer API.

    Args:
        api_key: The API key (``fck_…``). Sent as ``Authorization: Bearer <key>``
            and, for compatibility, also as ``X-API-Key``.
        base_url: API origin. The ``/v1`` prefix is appended automatically.
        transport: Optional injectable HTTP transport (for tests / custom runtimes).
            Defaults to a stdlib ``urllib`` transport.
        timeout: Request timeout in seconds (applies to the default transport).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[Transport] = None,
        timeout: float = 30.0,
        strict_unknown_fields: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        # Send ``Prefer: strict-unknown-fields`` on writes: an undeclared body field is refused
        # (400 ``unknown_field``) instead of ignored.
        self.strict_unknown_fields = strict_unknown_fields
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        if transport is not None:
            self._transport: Transport = transport
        else:
            self._transport = lambda m, u, h, b: urllib_transport(m, u, h, b, timeout=timeout)

        # Resource groups (mirror the TS SDK surface).
        self.sites = _Sites(self)
        self.consent = _Consent(self)
        self.dsar = _Dsar(self)
        self.vendors = _Vendors(self)
        self.ropa = _Ropa(self)
        self.brand_kits = _BrandKits(self)
        self.rights_page = _RightsPage(self)
        self.preferences = _Preferences(self)
        self.members = _Members(self)
        self.keys = _Keys(self)
        self.webhooks = _Webhooks(self)
        self.banners = _Banners(self)
        # The privacy platform beyond the banner.
        self.identity = _Identity(self)
        self.vault = _Vault(self)
        self.profile = _Profile(self)
        self.subscriptions = _Subscriptions(self)
        self.assessments = _Assessments(self)
        self.discovery = _Discovery(self)
        self.ai = _Ai(self)
        self.fulfillment = _Fulfillment(self)
        self.regulatory = _Regulatory(self)
        self.reseller = _Reseller(self)
        self.subjects = _Subjects(self)
        self.rights_links = _RightsLinks(self)
        self.rights_captcha = _RightsCaptcha(self)
        self.rights_identity = _RightsIdentity(self)
        self.org = _Org(self)
        self.assets = _Assets(self)

    # -- transport ---------------------------------------------------------

    def _headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            # urllib's default "Python-urllib/3.x" is refused at the API's edge with a bare
            # 403 "error code: 1010" (CMN-14), so every call from the default transport failed.
            "User-Agent": f"cookiemunch-python/{_SDK_VERSION}",
        }
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        raw: bool = False,
        prefix: str = "/v1",
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """Perform an HTTP request and decode the response.

        Returns ``None`` for 204, the decoded text for ``raw=True``, a parsed
        object for JSON responses, and text otherwise. Raises
        :class:`CookieMunchApiError` on any non-2xx status.
        """
        url = f"{self.base_url}{prefix}{path}"
        hdrs = self._headers(headers)
        if self.strict_unknown_fields and method.upper() != "GET":
            hdrs["Prefer"] = "strict-unknown-fields"
        data: Optional[bytes] = None
        if body is not None:
            hdrs["Content-Type"] = "application/json"
            data = _json.dumps(body).encode("utf-8")

        resp: HttpResponse = self._transport(method.upper(), url, hdrs, data)

        if not (200 <= resp.status < 300):
            self._raise_for_status(resp)

        if resp.status == 204 or not resp.body:
            return None
        text = resp.body.decode("utf-8", errors="replace")
        if raw:
            return text
        ctype = resp.header("content-type") or ""
        if "application/json" in ctype:
            return _json.loads(text) if text else None
        return text

    @staticmethod
    def _raise_for_status(resp: HttpResponse) -> None:
        message = f"request failed with status {resp.status}"
        code: Optional[str] = None
        body_text = resp.body.decode("utf-8", errors="replace") if resp.body else ""
        try:
            parsed = _json.loads(body_text) if body_text else None
            if isinstance(parsed, dict):
                if isinstance(parsed.get("error"), str):
                    message = parsed["error"]
                if isinstance(parsed.get("code"), str):
                    code = parsed["code"]
        except (ValueError, TypeError):
            pass  # non-JSON error body — keep the default message
        raise CookieMunchApiError(resp.status, message, code=code, body=body_text)

    def _get(self, path: str) -> Any:
        return self.request("GET", path)

    # -- top-level endpoints ----------------------------------------------

    def me(self) -> t.Identity:
        """GET /v1/me — identity for SDK bootstrapping."""
        return t.from_dict(t.Identity, self._get("/me"))

    def list_orgs(self) -> _JSONDict:
        """GET /v1/orgs — every organisation on this key's account.

        Each carries its effective ``plan``, ``planSource`` (``org`` = its own subscription,
        ``account`` = covered by a higher plan another org on the account pays for) and
        ``subscribedPlan``; the response also has ``orgLimit`` (``max``/``plan``/``used``) and
        ``upgradeUrl``. Needs an unscoped key that is not locked to properties.
        """
        return self._get("/orgs")

    def create_org(self, name: str) -> _JSONDict:
        """POST /v1/orgs — create a sibling organisation owned by the same account.

        For starting a separate business of your own. Needs an unscoped key, and counts
        against the account's plan org allowance (403 ``org_limit`` names the plan). This is
        not reseller provisioning: ``/v1/reseller/customers`` is for organisations you run on
        behalf of YOUR customers.
        """
        return self.request("POST", "/orgs", body={"name": name})

    def languages(self) -> List[t.SupportedLanguage]:
        """GET /v1/languages — the languages the banner already speaks.

        Diff this against your visitors' locales to see which ones you still have to
        write copy for in ``banner.i18n``.
        """
        return [t.from_dict(t.SupportedLanguage, r) for r in self._get("/languages")]

    def usage(self) -> t.Usage:
        """GET /v1/usage — current resource usage for the org."""
        return t.from_dict(t.Usage, self._get("/usage"))

    def integration_health(self, cbid: Optional[str] = None) -> _JSONDict:
        """GET /v1/integration-health — one row per link the site's privacy wiring depends on,
        each with ``ok`` (``None`` = could not check) and a ``fixHint``. ``cbid`` may be omitted
        when the org has one site."""
        return self._get(f"/integration-health{_qs({'cbid': cbid})}")

    def provision(self, input: Mapping[str, Any], dry_run: bool = False) -> _JSONDict:
        """POST /v1/provision — wire a product's privacy in one call (site, connected systems,
        Atlas, Forumulate). Idempotent; ``dry_run=True`` writes nothing anywhere. The Atlas key and
        Forumulate token in ``input`` are used for this request only; no secret is returned."""
        return self.request("POST", f"/provision{_qs({'dryRun': '1' if dry_run else None})}", body=dict(input))

    def audit(self, limit: Optional[int] = None) -> _JSONDict:
        """GET /v1/audit — the org's audit log, newest first. API actions appear as
        ``apikey:<prefix>``. Requires an unscoped key that is not property-locked."""
        return self._get(f"/audit{_qs({'limit': limit})}")

    # -- public consent ingest --------------------------------------------

    def log_consent(
        self,
        *,
        cbid: str,
        choices: _ChoicesLike,
        method: str = "explicit",
        url: str = "",
        stamp: Optional[str] = None,
        ver: int = 1,
        utc: Optional[int] = None,
        tc_string: Optional[str] = None,
        gpp_string: Optional[str] = None,
        purposes: Optional[Mapping[str, bool]] = None,
        subject_policy_hash: Optional[str] = None,
        variant: Optional[str] = None,
        subject_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        """Record a consent decision via the PUBLIC ingest endpoint
        ``POST /api/v1/consent`` (no ``/v1`` prefix, no auth required).

        This is what app/server integrations use to log consent captured outside the
        browser embed. ``stamp`` and ``utc`` are auto-generated when omitted.

        Args:
            cbid: The site identifier.
            choices: Category decisions — a :class:`~cookiemunch.types.ConsentChoices`
                or a mapping with ``preferences``/``statistics``/``marketing`` bools.
            method: ``"explicit"`` or ``"implied"``.
            url: The page URL the consent was captured on.
            stamp: Unique receipt id; auto-generated (uuid4) when omitted.
            ver: Consent schema version (default 1).
            utc: Epoch milliseconds of the decision; defaults to now.
            tc_string / gpp_string: Optional IAB TCF / GPP strings.
            purposes: Optional named purpose -> bool map.
            subject_policy_hash: Optional opaque digest of the notice text shown.
            variant: Optional A/B variant id.
            subject_id: Optional stable cross-surface subject id (e.g. a logged-in
                account id). Lets an org correlate one subject's consent across all its
                sites/surfaces. Opaque; stored and hashed server-side, never interpreted.
            region: Optional region; sent via the ``X-CookieMunch-Region`` header.
        """
        if isinstance(choices, t.ConsentChoices):
            choices_json = choices.to_json()
        else:
            choices_json = {
                "preferences": bool(choices.get("preferences", False)),
                "statistics": bool(choices.get("statistics", False)),
                "marketing": bool(choices.get("marketing", False)),
            }
        payload: _JSONDict = {
            "cbid": cbid,
            "stamp": stamp or uuid.uuid4().hex,
            "choices": choices_json,
            "method": method,
            "ver": ver,
            "utc": utc if utc is not None else int(time.time() * 1000),
            "url": url,
        }
        if tc_string is not None:
            payload["tcString"] = tc_string
        if gpp_string is not None:
            payload["gppString"] = gpp_string
        if purposes is not None:
            payload["purposes"] = dict(purposes)
        if subject_policy_hash is not None:
            payload["subjectPolicyHash"] = subject_policy_hash
        if variant is not None:
            payload["variant"] = variant
        if subject_id is not None:
            payload["subjectId"] = subject_id

        headers = {"X-CookieMunch-Region": region} if region else None
        self.request("POST", "/consent", body=payload, prefix="/api/v1", headers=headers)


class _Resource:
    def __init__(self, client: CookieMunch) -> None:
        self._c = client


class _Sites(_Resource):
    def list(self) -> List[t.Site]:
        return t.from_list(t.Site, self._c._get("/sites"))

    def create(self, *, domain: str, cbid: Optional[str] = None) -> t.Site:
        body: _JSONDict = {"domain": domain}
        if cbid is not None:
            body["cbid"] = cbid
        return t.from_dict(t.Site, self._c.request("POST", "/sites", body=body))

    def get(self, cbid: str) -> t.Site:
        return t.from_dict(t.Site, self._c._get(f"/sites/{_e(cbid)}"))

    def update(
        self,
        cbid: str,
        *,
        domain: Optional[str] = None,
        name: Any = _UNSET,
        aliases: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """PATCH /v1/sites/{cbid} — rename or move a site. The cbid and the consent ledger stay;
        a domain move clears verification. ``name=None`` clears the display name; ``aliases=[]``
        clears the aliases. ``dry_run=True`` answers with the diff and stores nothing."""
        body: _JSONDict = {}
        if domain is not None:
            body["domain"] = domain
        if name is not _UNSET:
            body["name"] = name
        if aliases is not None:
            body["aliases"] = list(aliases)
        return self._c.request("PATCH", f"/sites/{_e(cbid)}{_qs({'dryRun': '1' if dry_run else None})}", body=body)

    def delete(self, cbid: str) -> None:
        self._c.request("DELETE", f"/sites/{_e(cbid)}")

    def list_partners(self, cbid: str) -> _JSONDict:
        """GET /v1/sites/{cbid}/partners — partner links and the partner catalogue."""
        return self._c._get(f"/sites/{_e(cbid)}/partners")

    def link_partner(
        self,
        cbid: str,
        *,
        partner: str,
        external_id: str,
        label: Optional[str] = None,
        events: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """POST /v1/sites/{cbid}/partners — grant a partner platform (``forumulate``, ``atlas``)
        the site's consent events. No secret is created; idempotent."""
        body: _JSONDict = {"partner": partner, "externalId": external_id}
        if label is not None:
            body["label"] = label
        if events is not None:
            body["events"] = list(events)
        return self._c.request("POST", f"/sites/{_e(cbid)}/partners{_qs({'dryRun': '1' if dry_run else None})}", body=body)

    def unlink_partner(self, cbid: str, link_id: str) -> _JSONDict:
        """DELETE /v1/sites/{cbid}/partners/{link_id} — revoke; deliveries stop at once."""
        return self._c.request("DELETE", f"/sites/{_e(cbid)}/partners/{_e(link_id)}")

    def get_config(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/config")

    def put_config(self, cbid: str, config: Mapping[str, Any], keep_unspecified: bool = False) -> _JSONDict:
        """Replace a site's config. A top-level field ``config`` omits reverts to its default —
        unless ``keep_unspecified=True`` (``?keep=unspecified``), which keeps its stored value.
        A top-level field sent as ``None`` reverts to its default."""
        query = "?keep=unspecified" if keep_unspecified else ""
        return self._c.request("PUT", f"/sites/{_e(cbid)}/config{query}", body=dict(config))

    def patch_config(self, cbid: str, config: Mapping[str, Any]) -> _JSONDict:
        """Change part of a site's config — a JSON Merge Patch (RFC 7386): omitted fields keep
        their stored value, and a field set to ``None`` is removed (it takes its default)."""
        return self._c.request("PATCH", f"/sites/{_e(cbid)}/config", body=dict(config))

    def dry_run_config(
        self, cbid: str, config: Mapping[str, Any], replace: bool = False, keep_unspecified: bool = False
    ) -> _JSONDict:
        """Preview a config write without saving it (``?dryRun=1``).

        Returns ``config`` as it would be saved, ``diff`` (every leaf that would change)
        and any ``warnings``. ``replace=True`` previews a PUT: the diff then lists what
        a replace would revert to its default.
        """
        method = "PUT" if replace else "PATCH"
        keep = "&keep=unspecified" if replace and keep_unspecified else ""
        return self._c.request(method, f"/sites/{_e(cbid)}/config?dryRun=1{keep}", body=dict(config))

    def lint_config(self, cbid: str, config: Mapping[str, Any], replace: bool = False) -> _JSONDict:
        """Check a proposed config for consent-button parity without saving it
        (``POST /v1/sites/{cbid}/config/lint``): is "Accept all" more prominent than
        "Reject all" anywhere (colour, size, placement, copy, custom CSS)?

        Returns ``designWarnings`` (the findings), ``score`` (0-100) and ``suggestedReject``
        (the reject style that would match). It checks exactly what the write would store:
        merged as ``patch_config`` would, or with ``replace=True`` replaced as ``put_config``
        would. Needs only ``sites:read``.
        """
        query = "?replace=1" if replace else ""
        return self._c.request("POST", f"/sites/{_e(cbid)}/config/lint{query}", body=dict(config))

    def cookies(self, cbid: str) -> List[t.SiteCookie]:
        return t.from_list(t.SiteCookie, self._c._get(f"/sites/{_e(cbid)}/cookies"))

    def scan(self, cbid: str, *, wait: Optional[float] = None) -> t.ScanResult:
        """Start a cookie crawl: answers at once with ``scan_id`` and ``state="queued"``.
        ``wait`` (seconds, at most 60) holds the request until it is done or failed."""
        return t.from_dict(t.ScanResult, self._c.request("POST", f"/sites/{_e(cbid)}/scan{_qs({'wait': _num(wait)})}"))

    def scan_status(self, cbid: str, *, wait: Optional[float] = None) -> t.ScanResult:
        """The last scan: ``state``, timings, ``cookie_count``, ``pages_visited``, ``error``.
        ``wait`` (seconds, at most 60) holds the request until a running scan settles."""
        return t.from_dict(t.ScanResult, self._c._get(f"/sites/{_e(cbid)}/scan{_qs({'wait': _num(wait)})}"))

    def wait_for_scan(self, cbid: str, *, timeout_ms: int = 120_000) -> t.ScanResult:
        """Return once the site's scan is done or failed (read ``state`` and ``error``),
        long-polling the server; at ``timeout_ms`` it returns the still-running state.
        Each request asks the server to hold no longer than this client's own timeout."""
        until = time.monotonic() + timeout_ms / 1000
        while True:
            left = until - time.monotonic()
            asked = max(0.0, min(60.0, left, self._c._timeout - 5))
            started = time.monotonic()
            r = self.scan_status(cbid, wait=asked)
            if r.status != "scanning" or until - time.monotonic() <= 0:
                return r
            # A server that answered sooner than asked is not hammered.
            early = min(1.0, until - time.monotonic()) - (time.monotonic() - started)
            if early > 0:
                time.sleep(early)

    def ab(self, cbid: str) -> List[t.AbResult]:
        return t.from_list(t.AbResult, self._c._get(f"/sites/{_e(cbid)}/ab"))

    def banner(self, cbid: str) -> _JSONDict:
        """Which banner design the site uses: ``{"bannerId": str | None}``."""
        return self._c._get(f"/sites/{_e(cbid)}/banner")

    def blocked(self, cbid: str) -> _JSONDict:
        """Pages where the embed could not load its banner renderer — the host page's
        CSP or Trusted Types policy refused it, so nobody there can be asked. An empty
        list is the healthy answer."""
        return self._c._get(f"/sites/{_e(cbid)}/blocked")

    def import_declaration(self, cbid: str, data: str) -> _JSONDict:
        """Read a cookie declaration exported from another CMP and translate its
        categories into ours. Nothing is applied: their vocabulary is not ours, and a
        cookie in the wrong category is a tag firing against a refusal, so the result
        comes back for review."""
        return self._c.request("POST", f"/sites/{_e(cbid)}/import", body={"data": data})

    def apply_import(self, cbid: str, data: str, *, overwrite: bool = False) -> _JSONDict:
        """Import a declaration exported from another CMP AND declare it: every row whose
        category mapped to ours and that has a purpose is declared; the rest come back in
        ``skipped``. Cookies already declared are kept unless ``overwrite``."""
        query = "?apply=1" + ("&overwrite=1" if overwrite else "")
        return self._c.request("POST", f"/sites/{_e(cbid)}/import{query}", body={"data": data})

    def declare_cookie(
        self,
        cbid: str,
        name: str,
        category: str,
        purpose: str,
        *,
        provider: Optional[str] = None,
        expiry: Optional[str] = None,
        domain: Optional[str] = None,
        pattern: Optional[bool] = None,
        purposes: Optional[Dict[str, str]] = None,
        type: Optional[str] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """Declare what one cookie is. Overrides scanned, observed and database
        classification everywhere (API, preference modal, ``data-cc="declaration"``).
        A name ending in ``*`` (or ``pattern=True``) declares a prefix wildcard.
        ``category`` is a standard category or one of the site's custom category ids.
        ``purposes`` is the purpose in other languages (``{"es": "…", "pt-BR": "…"}``);
        ``purpose`` is the fallback. ``dry_run=True`` stores nothing and answers with the
        would-be list (``declared``) and a ``diff``. ``type`` declares browser storage instead
        of a cookie: ``"localStorage"``, ``"sessionStorage"`` or ``"indexedDB"``."""
        body: _JSONDict = {"category": category, "purpose": purpose}
        for key, value in (
            ("provider", provider),
            ("expiry", expiry),
            ("domain", domain),
            ("pattern", pattern),
            ("purposes", purposes),
            ("type", type),
        ):
            if value is not None:
                body[key] = value
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("PUT", f"/sites/{_e(cbid)}/cookies/{_e(name)}{query}", body=body)

    def declare_cookies(
        self, cbid: str, cookies: List[_JSONDict], *, replace: bool = False, dry_run: bool = False
    ) -> _JSONDict:
        """Declare many cookies at once (each ``{name, category, purpose, purposes?, ...}``).
        All-or-nothing; ``replace=True`` also removes declarations the list does not name.
        ``dry_run=True`` stores nothing and answers with what would be, plus a ``diff``."""
        body: _JSONDict = {"cookies": cookies}
        if replace:
            body["replace"] = True
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("PUT", f"/sites/{_e(cbid)}/cookies{query}", body=body)

    def retire_cookie(
        self,
        cbid: str,
        name: str,
        *,
        renamed_to: Optional[str] = None,
        note: Optional[str] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """Retire a cookie the site renamed or stopped setting: it leaves the banner's
        cookie list, ``data-cc="declaration"`` and the public feed, and stays listed for you
        with ``retired``. A name ending in ``*`` retires every cookie with that prefix. If a
        crawl or a visit sees it again afterwards it is listed again, flagged
        ``review="retired_but_seen"``. ``dry_run=True`` stores nothing."""
        body: _JSONDict = {}
        if renamed_to is not None:
            body["renamedTo"] = renamed_to
        if note is not None:
            body["note"] = note
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("POST", f"/sites/{_e(cbid)}/cookies/{_e(name)}/retire{query}", body=body)

    def unretire_cookie(self, cbid: str, name: str, *, dry_run: bool = False) -> Optional[_JSONDict]:
        """Un-retire a cookie: it is listed again everywhere. With ``dry_run=True`` nothing
        is removed and the answer is the would-be list (``retired``)."""
        if dry_run:
            return self._c.request("DELETE", f"/sites/{_e(cbid)}/cookies/{_e(name)}/retire?dryRun=1")
        self._c.request("DELETE", f"/sites/{_e(cbid)}/cookies/{_e(name)}/retire")
        return None

    def cookie_presets(self, cbid: str) -> _JSONDict:
        """Every declaration preset (atlas, forumulate, chatly, cookiemunch): its parameters,
        what it has declared on this site, and whether the vendor's manifest exists yet."""
        return self._c.request("GET", f"/sites/{_e(cbid)}/cookies/presets")

    def apply_cookie_preset(
        self, cbid: str, vendor: str, params: Optional[_JSONDict] = None, *, dry_run: bool = False
    ) -> _JSONDict:
        """Apply (or re-sync) a vendor preset: declares what that platform writes, marked
        ``vendor``. Atlas takes ``{"frontendApiHost", "crossSubdomainCookies"}``; Chatly
        ``{"publicId", "dragging", "category"}``. Names you declared are kept (``skipped``)."""
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("PUT", f"/sites/{_e(cbid)}/cookies/presets/{_e(vendor)}{query}", body=params or {})

    def remove_cookie_preset(self, cbid: str, vendor: str, *, dry_run: bool = False) -> _JSONDict:
        """Remove every declaration a vendor preset made."""
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("DELETE", f"/sites/{_e(cbid)}/cookies/presets/{_e(vendor)}{query}")

    def delete_observed_cookie(self, cbid: str, name: str, *, dry_run: bool = False) -> Optional[_JSONDict]:
        """Remove every stored (scanned or observed) row of this name; a declaration stays.
        With ``dry_run=True`` nothing is removed and the answer says what would be."""
        if dry_run:
            return self._c.request("DELETE", f"/sites/{_e(cbid)}/observed-cookies/{_e(name)}?dryRun=1")
        self._c.request("DELETE", f"/sites/{_e(cbid)}/observed-cookies/{_e(name)}")
        return None

    def purge_observed_cookies(
        self, cbid: str, since: Any, *, until: Any = None, dry_run: bool = False
    ) -> _JSONDict:
        """Purge observed since T: remove every row a real visit first reported at or after
        ``since`` (and before ``until``) — ISO-8601 or epoch ms. Crawled rows and declarations stay."""
        body: _JSONDict = {"since": since}
        if until is not None:
            body["until"] = until
        query = _qs({"dryRun": "1" if dry_run else None})
        return self._c.request("POST", f"/sites/{_e(cbid)}/observed-cookies/purge{query}", body=body)

    def undeclare_cookie(self, cbid: str, name: str, *, dry_run: bool = False) -> Optional[_JSONDict]:
        """Remove a declaration; the scanned classification applies again. With
        ``dry_run=True`` nothing is removed and the answer is the would-be list and a ``diff``."""
        if dry_run:
            return self._c.request("DELETE", f"/sites/{_e(cbid)}/cookies/{_e(name)}?dryRun=1")
        self._c.request("DELETE", f"/sites/{_e(cbid)}/cookies/{_e(name)}")
        return None

    def policy(
        self,
        cbid: str,
        *,
        contact_email: Optional[str] = None,
        effective_date: Optional[str] = None,
        jurisdictions: Optional[List[str]] = None,
    ) -> str:
        """The site's privacy and cookie policy, as Markdown."""
        query = _qs(
            {
                "contactEmail": contact_email,
                "effectiveDate": effective_date,
                "jurisdictions": ",".join(jurisdictions) if jurisdictions else None,
            }
        )
        return self._c.request("GET", f"/sites/{_e(cbid)}/policy{query}", raw=True)

    def set_ad_personalization(
        self, cbid: str, *, enabled: bool, default: Optional[bool] = None, label: Optional[str] = None
    ) -> _JSONDict:
        """Add or remove the separate personalised-ads choice on the site's banner."""
        body: _JSONDict = {"enabled": enabled}
        if default is not None:
            body["default"] = default
        if label is not None:
            body["label"] = label
        return self._c.request("POST", f"/sites/{_e(cbid)}/elements/ad-personalization", body=body)

    def analyze_session(
        self,
        cbid: str,
        *,
        har: Any = None,
        requests: Optional[List[Any]] = None,
        consent: Optional[Mapping[str, bool]] = None,
        gpc: Optional[bool] = None,
    ) -> _JSONDict:
        """Which trackers fired after opt-out in a captured session, and what personal data left the page."""
        body: _JSONDict = {}
        if har is not None:
            body["har"] = har
        if requests is not None:
            body["requests"] = list(requests)
        if consent is not None:
            body["consent"] = dict(consent)
        if gpc is not None:
            body["gpc"] = gpc
        return self._c.request("POST", f"/sites/{_e(cbid)}/sentry", body=body)

    def snippet(
        self,
        cbid: str,
        *,
        blocking_mode: Optional[str] = None,
        culture: Optional[str] = None,
    ) -> t.InstallSnippet:
        query = _qs({"blockingmode": blocking_mode, "culture": culture})
        return t.from_dict(t.InstallSnippet, self._c._get(f"/sites/{_e(cbid)}/snippet{query}"))

    def verify(self, cbid: str, method: str) -> t.VerifyResult:
        return t.from_dict(
            t.VerifyResult,
            self._c.request("POST", f"/sites/{_e(cbid)}/verify", body={"method": method}),
        )

    def verify_challenge(self, cbid: str) -> _JSONDict:
        """Exactly what to publish to prove control of the domain, for each method."""
        return self._c._get(f"/sites/{_e(cbid)}/verify/challenge")

    def create_bulk(self, sites: List[Mapping[str, Any]]) -> _JSONDict:
        """Create up to 100 sites. Partial success: each item reports ``ok`` or its own error."""
        return self._c.request("POST", "/sites/bulk", body={"sites": [dict(x) for x in sites]})

    def brand(self, cbid: str) -> _JSONDict:
        return self._c.request("POST", f"/sites/{_e(cbid)}/brand", body={})

    def preview_token(
        self,
        cbid: str,
        *,
        region: Optional[str] = None,
        lang: Optional[str] = None,
        url: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> _JSONDict:
        """Mint a short-lived signed token to preview the banner as a visitor in ``region``
        speaking ``lang`` sees it (headless browsers included; nothing is recorded).
        Returns ``{cbid, token, expiresAt, previewUrl?, region?, lang?}``."""
        body: Dict[str, Any] = {}
        if region is not None:
            body["region"] = region
        if lang is not None:
            body["lang"] = lang
        if url is not None:
            body["url"] = url
        if ttl_seconds is not None:
            body["ttlSeconds"] = ttl_seconds
        return self._c.request("POST", f"/sites/{_e(cbid)}/preview-token", body=body)

    def get_flow(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/flow")

    def edit_flow(self, cbid: str, operations: List[Mapping[str, Any]]) -> _JSONDict:
        return self._c.request(
            "POST", f"/sites/{_e(cbid)}/flow/ops", body={"operations": list(operations)}
        )

    def set_flow(self, cbid: str, config: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("PUT", f"/sites/{_e(cbid)}/flow", body=dict(config))


class _Consent(_Resource):
    def verify(self, cbid: str) -> bool:
        """Verify the consent log's tamper-evident hash chain.

        Each record carries the hash of the one before it, so an edited, reordered or
        removed record returns False. This is the evidence behind the log.
        """
        return bool(self._c._get(f"/sites/{_e(cbid)}/consent/verify").get("valid"))

    def stats(
        self, cbid: str, *, from_: Optional[int] = None, to: Optional[int] = None
    ) -> List[t.ConsentDay]:
        query = _qs({"from": from_, "to": to})
        return t.from_list(t.ConsentDay, self._c._get(f"/sites/{_e(cbid)}/consent/stats{query}"))

    def log(
        self,
        cbid: str,
        *,
        from_: Optional[int] = None,
        to: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[t.ConsentLogRow]:
        query = _qs({"from": from_, "to": to, "limit": limit})
        return t.from_list(t.ConsentLogRow, self._c._get(f"/sites/{_e(cbid)}/consent/log{query}"))

    def export(
        self, cbid: str, *, from_: Optional[int] = None, to: Optional[int] = None
    ) -> str:
        query = _qs({"from": from_, "to": to})
        return self._c.request("GET", f"/sites/{_e(cbid)}/consent/export{query}", raw=True)

    def receipt(self, cbid: str, stamp: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/receipt/{_e(stamp)}")

    def erase_subject(self, cbid: str, stamp: str) -> _JSONDict:
        return self._c.request(
            "POST", f"/sites/{_e(cbid)}/erase-consent", body={"stamp": stamp}
        )

    def export_subject(self, cbid: str, stamp: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/subject-export?stamp={_e(stamp)}")


class _Dsar(_Resource):
    def list(self) -> List[t.DsarRequest]:
        return t.from_list(t.DsarRequest, self._c._get("/dsar"))

    def create(
        self,
        *,
        type: str,
        subject_email: str,
        regulation: str,
        note: Optional[str] = None,
        test: Optional[bool] = None,
        message_to_subject: Optional[str] = None,
    ) -> _JSONDict:
        """``test=True`` files a test request: off the SLA board, labelled, deletable.

        ``note`` is internal and never shown to the subject; ``message_to_subject`` is the line
        they read in the response notice."""
        body: _JSONDict = {
            "type": type,
            "subjectEmail": subject_email,
            "regulation": regulation,
        }
        if note is not None:
            body["note"] = note
        if test is not None:
            body["test"] = test
        if message_to_subject is not None:
            body["messageToSubject"] = message_to_subject
        return self._c.request("POST", "/dsar", body=body)

    def get(self, id: str) -> _JSONDict:
        """GET /v1/dsar/{id} — one request, in the shape ``list`` returns."""
        return self._c._get(f"/dsar/{_e(id)}")

    def delete(self, id: str) -> None:
        """DELETE /v1/dsar/{id} — delete a TEST request. Real requests are refused (409)."""
        self._c.request("DELETE", f"/dsar/{_e(id)}")

    def mark_test(self, id: str) -> _JSONDict:
        """POST /v1/dsar/{id}/mark-test — mark a CLOSED request (completed or rejected) as a test,
        after the fact. An open one is refused (409 ``request_not_closed``). Audited; ``delete``
        then works on it. Returns ``{"request": ..., "changed": bool}``."""
        return self._c.request("POST", f"/dsar/{_e(id)}/mark-test")

    def advance(self, id: str, to_status: str, message_to_subject: Optional[str] = None) -> _JSONDict:
        """``message_to_subject`` replaces the line the subject reads in the notice."""
        body: _JSONDict = {"toStatus": to_status}
        if message_to_subject is not None:
            body["messageToSubject"] = message_to_subject
        return self._c.request("POST", f"/dsar/{_e(id)}/advance", body=body)

    def response(self, id: str) -> str:
        """The subject-facing response notice for a request, as plain text."""
        return self._c.request("GET", f"/dsar/{_e(id)}/response", raw=True)

    def erase(self, id: str, cbid: str, stamp: str) -> _JSONDict:
        """Crypto-erase a subject's consent records on a site, for a deletion request.
        The request must be past identity verification. Requires dsar:write and
        consent:write."""
        return self._c.request("POST", f"/dsar/{_e(id)}/erase", body={"cbid": cbid, "stamp": stamp})

    def export(self, id: str, cbid: str, stamp: str) -> _JSONDict:
        """Return a subject's consent records on a site, for an access or portability
        request. The request must be past identity verification. Requires dsar:write
        and consent:read."""
        return self._c.request("POST", f"/dsar/{_e(id)}/export", body={"cbid": cbid, "stamp": stamp})


class _Vendors(_Resource):
    def list(self) -> List[t.ScoredVendor]:
        return t.from_list(t.ScoredVendor, self._c._get("/vendors"))

    def create(self, vendor: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("POST", "/vendors", body=dict(vendor))


class _Ropa(_Resource):
    def list(self) -> List[t.RopaEntry]:
        return t.from_list(t.RopaEntry, self._c._get("/ropa"))

    def create(self, entry: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("POST", "/ropa", body=dict(entry))

    def export_csv(self) -> str:
        """The org's RoPA (GDPR Art. 30), as CSV."""
        return self._c.request("GET", "/ropa/export.csv", raw=True)


class _RightsPage(_Resource):
    """The hosted rights page — /v1/sites/{cbid}/rights-page. Requires sites:read / sites:write."""

    def get(self, cbid: str) -> _JSONDict:
        """The draft (the default document until first saved), with publish warnings."""
        return self._c._get(f"/sites/{_e(cbid)}/rights-page")

    def put(self, cbid: str, page: Mapping[str, Any]) -> _JSONDict:
        """Replace the draft. Nothing is live until :meth:`publish`.

        Add ``"baseUpdatedAt"`` (the draft's ``updatedAt`` as last read; ``None`` if it had none) to
        ``page`` to refuse overwriting a newer save: a mismatch raises a 409 ``draft_conflict``.
        """
        return self._c.request("PUT", f"/sites/{_e(cbid)}/rights-page", body=dict(page))

    def patch(self, cbid: str, page: Mapping[str, Any]) -> _JSONDict:
        """Merge into the draft: objects merge, lists replace, None removes."""
        return self._c.request("PATCH", f"/sites/{_e(cbid)}/rights-page", body=dict(page))

    def dry_run(self, cbid: str, page: Mapping[str, Any], replace: bool = False) -> _JSONDict:
        """Validate a write without saving it (``?dryRun=1``)."""
        return self._c.request("PUT" if replace else "PATCH", f"/sites/{_e(cbid)}/rights-page?dryRun=1", body=dict(page))

    def get_published(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/rights-page/published")

    def publish(self, cbid: str, base_updated_at: Any = _UNSET) -> _JSONDict:
        """Publish the draft; it goes live at once.

        Pass ``base_updated_at`` (the draft's ``updatedAt`` as last read; ``None`` if it had none) so
        only the draft you saw goes live: a mismatch raises a 409 ``draft_conflict``.
        """
        body: _JSONDict = {} if base_updated_at is _UNSET else {"baseUpdatedAt": base_updated_at}
        return self._c.request("POST", f"/sites/{_e(cbid)}/rights-page/publish", body=body)

    def versions(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/rights-page/versions")

    def rollback(self, cbid: str, version: int, base_updated_at: Any = _UNSET) -> _JSONDict:
        """Publish an earlier version again; it goes live at once and REPLACES the current draft
        (unpublished edits are lost). ``base_updated_at`` refuses with a 409 ``draft_conflict``
        if the draft changed since you read it.
        """
        body: _JSONDict = {"version": version}
        if base_updated_at is not _UNSET:
            body["baseUpdatedAt"] = base_updated_at
        return self._c.request("POST", f"/sites/{_e(cbid)}/rights-page/rollback", body=body)

    def list_domains(self, cbid: str) -> _JSONDict:
        """Custom hostnames serving the rights page: ``{domains, limit, used, target}``
        (``limit`` None = unlimited). Requires sites:read."""
        return self._c._get(f"/sites/{_e(cbid)}/rights-page/domains")

    def add_domain(self, cbid: str, hostname: str) -> _JSONDict:
        """Add a custom hostname (e.g. privacy.example.com). The answer's ``dns`` holds the
        exact records to create. Requires sites:write."""
        return self._c.request("POST", f"/sites/{_e(cbid)}/rights-page/domains", body={"hostname": hostname})

    def verify_domain(self, cbid: str, hostname: str) -> _JSONDict:
        """Check it now: DNS while pending, the HTTPS answer once routed. Returns the domain
        as it stands (``status``, ``lastError``, ``dnsSeen``)."""
        return self._c.request("POST", f"/sites/{_e(cbid)}/rights-page/domains/{_e(hostname)}/verify")

    def remove_domain(self, cbid: str, hostname: str) -> None:
        """Remove it: it stops being served and its certificate is no longer renewed."""
        self._c.request("DELETE", f"/sites/{_e(cbid)}/rights-page/domains/{_e(hostname)}")


class _BrandKits(_Resource):
    def list(self) -> List[t.BrandKit]:
        return t.from_list(t.BrandKit, self._c._get("/brand-kits"))

    def create(self, kit: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("POST", "/brand-kits", body=dict(kit))

    def delete(self, id: str) -> None:
        self._c.request("DELETE", f"/brand-kits/{_e(id)}")


class _Preferences(_Resource):
    def list(self) -> List[t.PreferenceItem]:
        return t.from_list(t.PreferenceItem, self._c._get("/preferences"))

    def save(self, subject_id: str, purposes: Mapping[str, bool]) -> Any:
        return self._c.request(
            "POST", "/preferences", body={"subjectId": subject_id, "purposes": dict(purposes)}
        )

    def get(self, subject_id: str) -> _JSONDict:
        """One subject's preference record. A subject with none has empty ``purposes``.
        Requires consent:read."""
        return self._c._get(f"/preferences/{_e(subject_id)}")


class _Members(_Resource):
    def list(self) -> List[t.Member]:
        return t.from_list(t.Member, self._c._get("/members"))

    def invite(self, email: str, role: str) -> _JSONDict:
        return self._c.request("POST", "/members", body={"email": email, "role": role})

    def set_role(self, user_id: str, role: str) -> _JSONDict:
        return self._c.request("PATCH", f"/members/{_e(user_id)}", body={"role": role})

    def remove(self, user_id: str) -> Any:
        return self._c.request("DELETE", f"/members/{_e(user_id)}")


class _Keys(_Resource):
    def list(self) -> List[t.ApiKey]:
        return t.from_list(t.ApiKey, self._c._get("/keys"))

    def issue(
        self,
        *,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        cbids: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
        expires_at: Optional[Union[int, str]] = None,
    ) -> t.ApiKey:
        """Issue an API key; the secret is returned once.

        Pass ``scopes`` and/or ``cbids`` for a least-privilege key — omit both for full
        access to the whole org. A key locked with ``cbids`` works only on those sites and
        on no org-wide endpoint.
        """
        body: _JSONDict = {}
        if name is not None:
            body["name"] = name
        if scopes is not None:
            body["scopes"] = list(scopes)
        if cbids is not None:
            body["cbids"] = list(cbids)
        if expires_in_days is not None:
            body["expiresInDays"] = expires_in_days
        if expires_at is not None:
            body["expiresAt"] = expires_at
        return t.from_dict(t.ApiKey, self._c.request("POST", "/keys", body=body))

    def revoke(self, prefix: str) -> None:
        """Revoke a key by its prefix. Immediate."""
        self._c.request("DELETE", f"/keys/{_e(prefix)}")

    def roll(self, prefix: str) -> t.ApiKey:
        """Rotate a key: a new secret, returned once, with the same scopes, lock and
        expiry. The old one stops working."""
        return t.from_dict(t.ApiKey, self._c.request("POST", f"/keys/{_e(prefix)}/roll"))

    def update(
        self,
        prefix: str,
        *,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        cbids: Optional[List[str]] = None,
        expires_at: Any = _UNSET,
    ) -> _JSONDict:
        """Rename a key, replace its scopes or property lock, or set (epoch ms / ISO) or remove
        (``expires_at=None``) its expiry. Only the fields sent change."""
        body: _JSONDict = {}
        if expires_at is not _UNSET:
            body["expiresAt"] = expires_at
        if name is not None:
            body["name"] = name
        if scopes is not None:
            body["scopes"] = list(scopes)
        if cbids is not None:
            body["cbids"] = list(cbids)
        return self._c.request("PATCH", f"/keys/{_e(prefix)}", body=body)

    def report(self, unused_days: Optional[int] = None, expiring_days: Optional[int] = None) -> _JSONDict:
        """GET /v1/keys/report — keys unused for ``unused_days`` (default 90), keys with broad
        access, and keys expiring within ``expiring_days`` (default 14), each with a reason."""
        return self._c._get(f"/keys/report{_qs({'unusedDays': unused_days, 'expiringDays': expiring_days})}")


class _Webhooks(_Resource):
    def list(self) -> List[t.WebhookSubscription]:
        return t.from_list(t.WebhookSubscription, self._c._get("/webhooks"))

    def create(
        self, *, url: str, events: List[str], cbid: Optional[str] = None
    ) -> t.WebhookSubscription:
        body: _JSONDict = {"url": url, "events": list(events)}
        if cbid is not None:
            body["cbid"] = cbid
        return t.from_dict(t.WebhookSubscription, self._c.request("POST", "/webhooks", body=body))

    def update(
        self,
        id: str,
        *,
        url: Optional[str] = None,
        events: Optional[List[str]] = None,
        cbid: Any = _UNSET,
        active: Optional[bool] = None,
    ) -> _JSONDict:
        """Change or pause a subscription. ``active=False`` pauses it; ``cbid=None`` widens it to the whole org."""
        body: _JSONDict = {}
        if url is not None:
            body["url"] = url
        if events is not None:
            body["events"] = list(events)
        if cbid is not _UNSET:
            body["cbid"] = cbid
        if active is not None:
            body["active"] = active
        return self._c.request("PATCH", f"/webhooks/{_e(id)}", body=body)

    def delete(self, id: str) -> None:
        self._c.request("DELETE", f"/webhooks/{_e(id)}")

    def roll_secret(self, id: str) -> _JSONDict:
        """Rotate the signing secret. The new secret is returned once."""
        return self._c.request("POST", f"/webhooks/{_e(id)}/roll")

    def test(self, id: str) -> _JSONDict:
        """Send a signed test event now and report what the endpoint answered."""
        return self._c.request("POST", f"/webhooks/{_e(id)}/test")

    def dead_letters(self) -> _JSONDict:
        """Deliveries that failed every retry, newest first."""
        return self._c._get("/webhooks/dead-letters")

    def replay_dead_letter(self, id: str) -> _JSONDict:
        """Deliver a dead letter again, to the subscription as it is now."""
        return self._c.request("POST", f"/webhooks/dead-letters/{_e(id)}/replay")


class _Banners(_Resource):
    def list(self) -> List[t.BannerSummary]:
        return t.from_list(t.BannerSummary, self._c._get("/banners"))

    def create(self, *, name: str, json: Mapping[str, Any]) -> t.BannerRecord:
        return t.from_dict(
            t.BannerRecord,
            self._c.request("POST", "/banners", body={"name": name, "json": dict(json)}),
        )

    def get(self, id: str) -> t.BannerRecord:
        return t.from_dict(t.BannerRecord, self._c._get(f"/banners/{_e(id)}"))

    def update(
        self,
        id: str,
        *,
        name: Optional[str] = None,
        json: Optional[Mapping[str, Any]] = None,
    ) -> t.BannerRecord:
        patch: _JSONDict = {}
        if name is not None:
            patch["name"] = name
        if json is not None:
            patch["json"] = dict(json)
        return t.from_dict(t.BannerRecord, self._c.request("PUT", f"/banners/{_e(id)}", body=patch))

    def delete(self, id: str) -> None:
        self._c.request("DELETE", f"/banners/{_e(id)}")

    def assignments(self, id: str) -> _JSONDict:
        return self._c._get(f"/banners/{_e(id)}/assignments")

    def set_assignments(self, id: str, cbids: List[str]) -> _JSONDict:
        return self._c.request("PUT", f"/banners/{_e(id)}/assignments", body={"cbids": list(cbids)})

    def publish(self, id: str) -> _JSONDict:
        return self._c.request("POST", f"/banners/{_e(id)}/publish")


# -- the privacy platform ---------------------------------------------------------------
#
# Identity, vault and profile reads are POSTs on purpose: a person's identifiers travel in
# the request body, never in a URL where logs and proxies would keep them.

Identifiers = List[Mapping[str, str]]
"""A person's identifiers, e.g. ``[{"space": "email_sha256", "value": "<hex>"}]``."""



class _Identity(_Resource):
    def resolve(self, identifiers: Identifiers) -> _JSONDict:
        """The subject id for these identifiers, or ``None`` if unknown."""
        return self._c.request("POST", "/identity/resolve", body={"identifiers": list(identifiers)})

    def link(self, identifiers: Identifiers) -> _JSONDict:
        """Stitch identifiers into one subject. A durable merge."""
        return self._c.request("POST", "/identity/link", body={"identifiers": list(identifiers)})

    def cluster(self, subject_id: str) -> _JSONDict:
        return self._c._get(f"/identity/{_e(subject_id)}")


class _Vault(_Resource):
    def record(self, identifiers: Identifiers, decisions: List[Mapping[str, Any]]) -> _JSONDict:
        return self._c.request(
            "POST", "/vault/record", body={"identifiers": list(identifiers), "decisions": list(decisions)}
        )

    def current(self, identifiers: Identifiers) -> _JSONDict:
        """Allow/deny per purpose, resolved across all of the person's identifiers."""
        return self._c.request("POST", "/vault/current", body={"identifiers": list(identifiers)})

    def permits(self, identifiers: Identifiers) -> _JSONDict:
        """The same decisions in full: legal basis, jurisdiction, provenance, time."""
        return self._c.request("POST", "/vault/permits", body={"identifiers": list(identifiers)})


class _Profile(_Resource):
    def get(self, identifiers: Identifiers) -> _JSONDict:
        return self._c.request("POST", "/profile/get", body={"identifiers": list(identifiers)})

    def set_attributes(self, identifiers: Identifiers, attributes: Mapping[str, Mapping[str, Any]]) -> _JSONDict:
        return self._c.request(
            "POST", "/profile/attributes", body={"identifiers": list(identifiers), "attributes": dict(attributes)}
        )

    def activate(self, identifiers: Identifiers, purpose: str) -> _JSONDict:
        """Attribute values usable for ``purpose`` — empty when the person has not consented to it."""
        return self._c.request(
            "POST", "/profile/activate", body={"identifiers": list(identifiers), "purpose": purpose}
        )


class _Subscriptions(_Resource):
    def topics(self) -> _JSONDict:
        return self._c._get("/subscriptions/topics")

    def set_topics(self, topics: List[Mapping[str, Any]]) -> _JSONDict:
        """Replace the topic catalog. It is authored whole; anything omitted is removed."""
        return self._c.request("PUT", "/subscriptions/topics", body={"topics": list(topics)})

    def get(self, subject_id: str) -> _JSONDict:
        return self._c._get(f"/subscriptions/{_e(subject_id)}")

    def set(self, subject_id: str, topic: str, channel: str, opted_in: bool) -> _JSONDict:
        return self._c.request(
            "PUT",
            f"/subscriptions/{_e(subject_id)}",
            body={"topic": topic, "channel": channel, "optedIn": opted_in},
        )

    def unsubscribe_all(self, subject_id: str) -> _JSONDict:
        return self._c.request("POST", f"/subscriptions/{_e(subject_id)}/unsubscribe-all")

    def resubscribe(self, subject_id: str) -> _JSONDict:
        """Lift a global unsubscribe, restoring the per-topic choices from before it."""
        return self._c.request("POST", f"/subscriptions/{_e(subject_id)}/resubscribe")

    def activation(self, subject_id: str, topics: List[Mapping[str, Any]]) -> _JSONDict:
        return self._c.request(
            "POST", f"/subscriptions/{_e(subject_id)}/activation", body={"topics": list(topics)}
        )


class _Assessments(_Resource):
    def templates(self) -> _JSONDict:
        return self._c._get("/assessments/templates")

    def list(self) -> _JSONDict:
        return self._c._get("/assessments")

    def start(self, template: str, subject: str) -> _JSONDict:
        return self._c.request("POST", "/assessments", body={"template": template, "subject": subject})

    def get(self, id: str) -> _JSONDict:
        return self._c._get(f"/assessments/{_e(id)}")

    def answer(self, id: str, question_id: str, value: Any) -> _JSONDict:
        return self._c.request(
            "POST", f"/assessments/{_e(id)}/answer", body={"questionId": question_id, "value": value}
        )

    def auto_populate_from_map(self, id: str) -> _JSONDict:
        """Fill factual answers from the latest data map. Never overwrites a human answer."""
        return self._c.request("POST", f"/assessments/{_e(id)}/autopopulate-from-map")

    def auto_populate(self, id: str, evidence: Mapping[str, Any], source: Optional[str] = None) -> _JSONDict:
        """Fill from evidence you supply, stamped with ``source``. Never overwrites a human answer."""
        body: _JSONDict = {"evidence": dict(evidence)}
        if source is not None:
            body["source"] = source
        return self._c.request("POST", f"/assessments/{_e(id)}/autopopulate", body=body)

    def submit(self, id: str) -> _JSONDict:
        return self._c.request("POST", f"/assessments/{_e(id)}/submit")

    def approve(self, id: str, by: str) -> _JSONDict:
        """Record approval. ``by`` becomes the approval record — pass the person who approved."""
        return self._c.request("POST", f"/assessments/{_e(id)}/approve", body={"by": by})

    def reject(self, id: str, by: str, reason: str) -> _JSONDict:
        return self._c.request("POST", f"/assessments/{_e(id)}/reject", body={"by": by, "reason": reason})


class _Discovery(_Resource):
    def ingest_map(self, map: Mapping[str, Any]) -> _JSONDict:
        """Upload a data map produced by an in-environment scan (metadata only)."""
        return self._c.request("POST", "/discovery/map", body={"map": dict(map)})

    def get_map(self) -> _JSONDict:
        return self._c._get("/discovery/map")

    def ropa_drafts(self) -> _JSONDict:
        return self._c._get("/discovery/ropa-drafts")

    def evidence(self) -> _JSONDict:
        return self._c._get("/discovery/evidence")

    def drift(self) -> _JSONDict:
        """What changed since the last scan, and where the RoPA disagrees with reality."""
        return self._c._get("/discovery/drift")

    def plan_enforcement(
        self,
        dialect: str,
        rules: List[Mapping[str, Any]],
        *,
        permits_table: Optional[str] = None,
        policy_prefix: Optional[str] = None,
    ) -> _JSONDict:
        """Plan masking / row-access policy for a warehouse. Applies nothing."""
        body: _JSONDict = {"dialect": dialect, "rules": list(rules)}
        if permits_table is not None:
            body["permitsTable"] = permits_table
        if policy_prefix is not None:
            body["policyPrefix"] = policy_prefix
        return self._c.request("POST", "/discovery/enforcement", body=body)


class _Ai(_Resource):
    def get_policy(self) -> _JSONDict:
        return self._c._get("/ai/policy")

    def set_policy(self, policy: Mapping[str, Any]) -> _JSONDict:
        """Replace the AI gateway policy."""
        return self._c.request("PUT", "/ai/policy", body={"policy": dict(policy)})

    def inspect(self, input: Mapping[str, Any]) -> _JSONDict:
        """Enforce consent and policy on a prompt or response. Needs the ``ai:inspect`` scope."""
        return self._c.request("POST", "/ai/inspect", body=dict(input))

    def inventory(self) -> _JSONDict:
        return self._c._get("/ai/inventory")

    def lineage(self) -> _JSONDict:
        return self._c._get("/ai/lineage")

    def register_system(
        self, *, id: str, name: str, provider: Optional[str] = None, purpose: Optional[str] = None
    ) -> _JSONDict:
        body: _JSONDict = {"id": id, "name": name}
        if provider is not None:
            body["provider"] = provider
        if purpose is not None:
            body["purpose"] = purpose
        return self._c.request("POST", "/ai/systems", body=body)

    def systems(self) -> _JSONDict:
        return self._c._get("/ai/systems")

    def audit(self, limit: Optional[int] = None) -> _JSONDict:
        return self._c._get(f"/ai/audit{_qs({'limit': limit})}")


class _Fulfillment(_Resource):
    def sla(self) -> _JSONDict:
        return self._c._get("/dsar/sla")

    def plan(
        self, request_id: str, systems: List[Mapping[str, str]], include_historical: bool = False
    ) -> _JSONDict:
        body: _JSONDict = {"systems": list(systems)}
        if include_historical:
            body["includeHistorical"] = True
        return self._c.request("POST", f"/dsar/{_e(request_id)}/plan", body=body)

    def status(self, request_id: str) -> _JSONDict:
        return self._c._get(f"/dsar/{_e(request_id)}/fulfillment")

    def executors(self) -> List[_JSONDict]:
        """GET /v1/dsar/executors — systems connected to run part of a request."""
        return self._c._get("/dsar/executors")

    def connect_executor(
        self,
        system: str,
        base_url: str,
        secret_key: str,
        profile: Mapping[str, object],
        webhook_secret: Optional[str] = None,
        auto: Optional[bool] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """POST /v1/dsar/executors — connect a system that runs part of a rights request.

        ``profile`` describes that system's API — paths, the words it uses for export and
        erase, its status vocabulary, how it signs webhooks — so connecting a new platform
        needs no code. The secret is stored encrypted and never returned.

        ``dry_run=True`` (``?dryRun=1``) validates everything and returns
        ``{"dryRun": True, "executor": ..., "diff": [...]}`` without storing anything.
        A ``whsec_<base64>`` webhook secret verifies deliveries signed with its
        base64-decoded bytes or with the literal string; any other secret only with its
        UTF-8 bytes.
        """
        body: _JSONDict = {
            "system": system,
            "baseUrl": base_url,
            "secretKey": secret_key,
            "profile": dict(profile),
        }
        if webhook_secret is not None:
            body["webhookSecret"] = webhook_secret
        if auto is not None:
            body["auto"] = auto
        return self._c.request("POST", "/dsar/executors" + ("?dryRun=1" if dry_run else ""), body=body)

    def connect_executor_preset(
        self,
        preset: str,
        secret_key: str,
        *,
        system: Optional[str] = None,
        base_url: Optional[str] = None,
        org_id: Optional[str] = None,
        atlas_id_app_id: Optional[str] = None,
        preset_version: Optional[int] = None,
        webhook_secret: Optional[str] = None,
        auto: Optional[bool] = None,
        cbid: Optional[str] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """POST /v1/dsar/executors with ``preset`` — connect a system from a versioned preset.

        ``atlas`` (optional ``atlas_id_app_id``), ``forumulate`` (``org_id``), ``cm-standard-v1``
        (``base_url`` and ``system``) or ``chatly``. The response carries ``presetVersion`` and
        ``presetDiff``. A preset waiting on another platform's API is refused (409
        ``preset_waiting_on_platform``); see :meth:`executor_presets`.
        """
        body: _JSONDict = {"preset": preset, "secretKey": secret_key}
        for key, value in (
            ("system", system), ("baseUrl", base_url), ("orgId", org_id), ("atlasIdAppId", atlas_id_app_id),
            ("presetVersion", preset_version), ("webhookSecret", webhook_secret), ("auto", auto), ("cbid", cbid),
        ):
            if value is not None:
                body[key] = value
        return self._c.request("POST", "/dsar/executors" + ("?dryRun=1" if dry_run else ""), body=body)

    def executor_presets(self) -> _JSONDict:
        """GET /v1/dsar/executors/presets — the presets, which wait on another platform, and the org canary address."""
        return self._c._get("/dsar/executors/presets")

    def upgrade_executor_preset(
        self,
        id: str,
        *,
        preset: Optional[str] = None,
        preset_version: Optional[int] = None,
        org_id: Optional[str] = None,
        atlas_id_app_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """POST /v1/dsar/executors/{id}/upgrade-preset — rebuild from the preset's latest version.

        Keeps the id and credential. ``preset`` adopts one on a hand-written connection.
        Answers with ``diff``; ``dry_run=True`` (``?dryRun=1``) changes nothing.
        """
        body: _JSONDict = {}
        for key, value in (("preset", preset), ("presetVersion", preset_version), ("orgId", org_id), ("atlasIdAppId", atlas_id_app_id)):
            if value is not None:
                body[key] = value
        return self._c.request("POST", f"/dsar/executors/{_e(id)}/upgrade-preset" + ("?dryRun=1" if dry_run else ""), body=body)

    def update_executor(
        self,
        id: str,
        *,
        profile: Optional[Mapping[str, object]] = None,
        base_url: Optional[str] = None,
        secret_key: Optional[str] = None,
        webhook_secret: Any = _UNSET,
        auto: Optional[bool] = None,
        dry_run: bool = False,
    ) -> _JSONDict:
        """PATCH /v1/dsar/executors/{id} — change a connection in place.

        Only what you pass changes; the stored credential is kept unless ``secret_key`` is
        given. ``webhook_secret=None`` removes the webhook secret. ``dry_run=True``
        (``?dryRun=1``) returns the would-be connection and a diff, and changes nothing.
        """
        body: _JSONDict = {}
        if profile is not None:
            body["profile"] = dict(profile)
        if base_url is not None:
            body["baseUrl"] = base_url
        if secret_key is not None:
            body["secretKey"] = secret_key
        if webhook_secret is not _UNSET:
            body["webhookSecret"] = webhook_secret
        if auto is not None:
            body["auto"] = auto
        return self._c.request("PATCH", f"/dsar/executors/{_e(id)}" + ("?dryRun=1" if dry_run else ""), body=body)

    def test_executor_webhook(self, id: str, headers: Mapping[str, str], body: str) -> _JSONDict:
        """POST /v1/dsar/executors/{id}/webhook/test — would this delivery verify?

        Runs the receiver's exact check on ``headers`` and the raw ``body`` string (the
        bytes that were signed) and acts on nothing. Returns ``{verified, stage, reason}``.
        """
        return self._c.request("POST", f"/dsar/executors/{_e(id)}/webhook/test", body={"headers": dict(headers), "body": body})

    def executor_webhook_deliveries(self, id: str) -> List[_JSONDict]:
        """GET /v1/dsar/executors/{id}/webhook/deliveries — the last 50, each with its reason."""
        return self._c._get(f"/dsar/executors/{_e(id)}/webhook/deliveries")

    def disconnect_executor(self, id: str) -> None:
        """DELETE /v1/dsar/executors/{id}."""
        self._c.request("DELETE", f"/dsar/executors/{_e(id)}")

    def task(self, request_id: str, task_id: str) -> _JSONDict:
        """GET /v1/dsar/{id}/tasks/{taskId} — one task: status history, upstream log, versions."""
        return self._c._get(f"/dsar/{_e(request_id)}/tasks/{_e(task_id)}")

    def test_executor(
        self,
        id: str,
        email: Optional[str] = None,
        operation: Optional[str] = None,
        open: Optional[bool] = None,
        canary: Optional[bool] = None,
    ) -> _JSONDict:
        """POST /v1/dsar/executors/{id}/test — try a connection without filing a request.

        Runs the lookup and returns the raw (redacted) upstream answers. ``open=True`` on an
        export opens and polls a real export once; an erasure is never sent. ``canary=True``
        (instead of ``email``) uses the org canary address — no real person — and a canary
        locate updates the connection's ``health``. ``code: base_url_redirects`` means the
        connection's address redirects; the verdict names where.
        """
        body: _JSONDict = {}
        if email is not None:
            body["email"] = email
        if canary is not None:
            body["canary"] = canary
        if operation is not None:
            body["operation"] = operation
        if open is not None:
            body["open"] = open
        return self._c.request("POST", f"/dsar/executors/{_e(id)}/test", body=body)

    def task_export(self, request_id: str, task_id: str) -> _JSONDict:
        """GET /v1/dsar/{id}/tasks/{taskId}/export — the bundle a connected system produced."""
        return self._c._get(f"/dsar/{_e(request_id)}/tasks/{_e(task_id)}/export")

    def pending_tasks(self, limit: Optional[int] = None) -> _JSONDict:
        """For the in-environment agent: tasks to execute inside your network."""
        return self._c._get(f"/dsar/agent/tasks{_qs({'limit': limit})}")

    def report_task(self, task_id: str, ok: bool, error: Optional[str] = None) -> _JSONDict:
        """For the in-environment agent: report an outcome. Only the outcome crosses the boundary."""
        body: _JSONDict = {"ok": ok}
        if error is not None:
            body["error"] = error
        return self._c.request("POST", f"/dsar/agent/tasks/{_e(task_id)}/result", body=body)


class _Regulatory(_Resource):
    def feed(self, jurisdictions: Optional[List[str]] = None) -> _JSONDict:
        query = _qs({"jurisdictions": ",".join(jurisdictions) if jurisdictions else None})
        return self._c._get(f"/regulatory/feed{query}")

    def upcoming(self, days: Optional[int] = None) -> _JSONDict:
        return self._c._get(f"/regulatory/upcoming{_qs({'days': days})}")


class _Subjects(_Resource):
    def consent(self, subject_id: str) -> _JSONDict:
        """One person's consent across every site in the org, by the subject id your apps attach.
        Needs ``consent:read``; not available to property-locked keys."""
        return self._c._get(f"/subjects/{_e(subject_id)}/consent")


class _RightsLinks(_Resource):
    def create(
        self,
        cbid: str,
        *,
        email: str,
        user_id: Optional[str] = None,
        rights: Optional[List[str]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> _JSONDict:
        """Mint a signed, single-use link to the hosted rights page for a person your backend
        knows is signed in. The page locks their email and skips the code step. Show the
        returned ``url`` only to that person. Needs ``dsar:write``. Returns ``{url, expiresAt}``."""
        subject: Dict[str, Any] = {"email": email}
        if user_id is not None:
            subject["userId"] = user_id
        body: Dict[str, Any] = {"subject": subject}
        if rights is not None:
            body["rights"] = list(rights)
        if ttl_seconds is not None:
            body["ttlSeconds"] = ttl_seconds
        return self._c.request("POST", f"/sites/{_e(cbid)}/rights-links", body=body)


def _captcha_body(mode: str, provider: Optional[str], site_key: Optional[str], secret: Optional[str], min_score: Optional[float]) -> _JSONDict:
    body: _JSONDict = {"mode": mode}
    if provider is not None:
        body["provider"] = provider
    if site_key is not None:
        body["siteKey"] = site_key
    if secret is not None:
        body["secret"] = secret
    if min_score is not None:
        body["minScore"] = min_score
    return body


class _RightsCaptcha(_Resource):
    """A site's rights-page captcha: your own Turnstile, hCaptcha or reCAPTCHA keys
    (recommended), or off. A site without its own setting uses the organisation default
    (``org.rights_captcha()``), else off. Cookie Munch's own captcha is never used on rights
    pages. Requires sites:read / sites:write."""

    def get(self, cbid: str) -> _JSONDict:
        """The setting in force (``source``: site, org or default). Never the secret."""
        return self._c._get(f"/sites/{_e(cbid)}/rights-captcha")

    def set(
        self,
        cbid: str,
        *,
        mode: str,
        provider: Optional[str] = None,
        site_key: Optional[str] = None,
        secret: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> _JSONDict:
        """``mode="own"`` with ``provider`` (turnstile, hcaptcha, recaptcha_v2, recaptcha_v3),
        ``site_key`` and ``secret`` (write-only; omit to keep the stored one) — the provider must
        accept the secret before it is saved. ``min_score`` is for recaptcha_v3 (0.1-0.9).
        ``mode="off"`` removes spam protection beyond the spam-trap field, the rate limits and
        the email code."""
        return self._c.request("PUT", f"/sites/{_e(cbid)}/rights-captcha", body=_captcha_body(mode, provider, site_key, secret, min_score))

    def remove(self, cbid: str) -> _JSONDict:
        """Remove the site's own setting: it inherits the organisation default again. Returns
        the setting now in force."""
        return self._c.request("DELETE", f"/sites/{_e(cbid)}/rights-captcha")


def _identity_body(
    type: str,
    issuer: str,
    jwks_url: Optional[str],
    audience: Optional[str],
    authorized_parties: Optional[List[str]],
    email_claim: Optional[str],
    email_verified_claim: Optional[str],
    session_cookie_name: Optional[str],
    trust_email_claim: Optional[bool] = None,
) -> _JSONDict:
    body: _JSONDict = {"type": type, "issuer": issuer}
    for key, value in (
        ("jwksUrl", jwks_url),
        ("audience", audience),
        ("authorizedParties", authorized_parties),
        ("emailClaim", email_claim),
        ("emailVerifiedClaim", email_verified_claim),
        ("sessionCookieName", session_cookie_name),
        ("trustEmailClaim", trust_email_claim),
    ):
        if value is not None:
            body[key] = value
    return body


class _RightsIdentity(_Resource):
    """A site's sign-in provider (Clerk, Atlas or any JWKS issuer): a visitor signed in to your
    site is verified by their session, with no code mail. A site without its own setting uses the
    organisation default (``org.rights_identity()``). Requires sites:read / sites:write."""

    def get(self, cbid: str) -> _JSONDict:
        """The setting in force (``source``: site, org or default)."""
        return self._c._get(f"/sites/{_e(cbid)}/rights-identity")

    def set(
        self,
        cbid: str,
        *,
        type: str,
        issuer: str,
        jwks_url: Optional[str] = None,
        audience: Optional[str] = None,
        authorized_parties: Optional[List[str]] = None,
        email_claim: Optional[str] = None,
        email_verified_claim: Optional[str] = None,
        session_cookie_name: Optional[str] = None,
        trust_email_claim: Optional[bool] = None,
    ) -> _JSONDict:
        """``type`` is clerk, atlas or oidc_jwt; ``issuer`` exactly the token's ``iss``.
        ``jwks_url`` is required for oidc_jwt (clerk/atlas: ``<issuer>/.well-known/jwks.json``);
        ``authorized_parties`` (your own origins) is required for clerk and atlas. The JWKS is
        fetched and checked before anything is saved; oidc_jwt needs ``audience`` or
        ``authorized_parties``. The token must carry the email and a verified-email claim set to
        true; ``trust_email_claim`` (clerk/atlas only) accepts a token without the verified claim."""
        return self._c.request("PUT", f"/sites/{_e(cbid)}/rights-identity", body=_identity_body(
            type, issuer, jwks_url, audience, authorized_parties, email_claim, email_verified_claim, session_cookie_name,
            trust_email_claim))

    def remove(self, cbid: str) -> _JSONDict:
        """Remove the site's own setting: it inherits the organisation default again."""
        return self._c.request("DELETE", f"/sites/{_e(cbid)}/rights-identity")


class _Org(_Resource):
    """The key's organisation. Requires an unscoped key that is not property-locked."""

    def get(self) -> t.Org:
        return t.from_dict(t.Org, self._c._get("/org"))

    def update(self, *, name: Optional[str] = None, logo_url: Any = _UNSET) -> t.Org:
        """Rename the org or set its logo. ``logo_url=None`` removes the logo; omitting
        it leaves the logo unchanged. Deleting the org is not available through the API."""
        body: _JSONDict = {}
        if name is not None:
            body["name"] = name
        if logo_url is not _UNSET:
            body["logoUrl"] = logo_url
        return t.from_dict(t.Org, self._c.request("PATCH", "/org", body=body))

    def mail_provider(self) -> _JSONDict:
        """Your own mail provider for rights-request mail. Never returns the credential, only
        ``secretLast4``; ``sender`` says whether verification codes go through it now (``own``)
        or are not mailed at all (``none``) — there is no shared sender."""
        return self._c._get("/org/mail-provider")

    def set_mail_provider(
        self,
        *,
        provider: str,
        from_email: str,
        secret: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        ses: Optional[_JSONDict] = None,
        smtp: Optional[_JSONDict] = None,
    ) -> _JSONDict:
        """Connect your own mail provider (recommended): ``brevo``, ``sendgrid``, ``postmark``,
        ``resend``, ``ses`` (``ses={"region", "accessKeyId"}``) or ``smtp``
        (``smtp={"host", "port", "security", "username"}``). Replaces the stored one. It carries
        rights mail only after ``test_mail_provider`` succeeds. ``secret`` is write-only; omit
        it to keep the stored one (same provider only)."""
        body: _JSONDict = {"provider": provider, "fromEmail": from_email}
        if from_name is not None:
            body["fromName"] = from_name
        if reply_to is not None:
            body["replyTo"] = reply_to
        if secret is not None:
            body["secret"] = secret
        if ses is not None:
            body["ses"] = ses
        if smtp is not None:
            body["smtp"] = smtp
        return self._c.request("PUT", "/org/mail-provider", body=body)

    def test_mail_provider(self, to: Optional[str] = None) -> _JSONDict:
        """Send a test through your provider. ``to`` defaults to the reply-to, else the from
        address. A refusal comes back as ``ok: False`` with the provider's reason."""
        return self._c.request("POST", "/org/mail-provider/test", body={"to": to} if to else {})

    def remove_mail_provider(self) -> None:
        """Remove your provider; no verification codes are mailed after this."""
        self._c.request("DELETE", "/org/mail-provider")

    def rights_captcha(self) -> _JSONDict:
        """The default captcha for your rights pages (sites without their own). Never the secret."""
        return self._c._get("/org/rights-captcha")

    def set_rights_captcha(
        self,
        *,
        mode: str,
        provider: Optional[str] = None,
        site_key: Optional[str] = None,
        secret: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> _JSONDict:
        """Set the default: ``own`` keys (recommended) or ``off``. Same fields as
        ``rights_captcha.set``."""
        return self._c.request("PUT", "/org/rights-captcha", body=_captcha_body(mode, provider, site_key, secret, min_score))

    def remove_rights_captcha(self) -> _JSONDict:
        """Remove the default: sites without their own setting have no captcha."""
        return self._c.request("DELETE", "/org/rights-captcha")

    def rights_identity(self) -> _JSONDict:
        """The default sign-in provider rights requests are verified with (sites without their own)."""
        return self._c._get("/org/rights-identity")

    def set_rights_identity(
        self,
        *,
        type: str,
        issuer: str,
        jwks_url: Optional[str] = None,
        audience: Optional[str] = None,
        authorized_parties: Optional[List[str]] = None,
        email_claim: Optional[str] = None,
        email_verified_claim: Optional[str] = None,
        session_cookie_name: Optional[str] = None,
        trust_email_claim: Optional[bool] = None,
    ) -> _JSONDict:
        """Set the default. Same fields as ``rights_identity.set``."""
        return self._c.request("PUT", "/org/rights-identity", body=_identity_body(
            type, issuer, jwks_url, audience, authorized_parties, email_claim, email_verified_claim, session_cookie_name,
            trust_email_claim))

    def remove_rights_identity(self) -> _JSONDict:
        """Remove the default sign-in provider."""
        return self._c.request("DELETE", "/org/rights-identity")


class _Assets(_Resource):
    def upload(self, *, data: str, content_type: str) -> _JSONDict:
        """Upload a banner image (<= 1,000,000 bytes; base64, or a data: URL) and get
        its public URL. Requires sites:write."""
        return self._c.request("POST", "/assets", body={"data": data, "contentType": content_type})

    def delete(self, url_or_file_name: str) -> None:
        """Delete a stored image. Takes the URL ``upload`` returned, or just its file
        name. Only your own org's images are reachable: the folder comes from your API
        key, not from the name you send."""
        name = url_or_file_name.rsplit("/", 1)[-1]
        self._c.request("DELETE", f"/assets/{_e(name)}")


class _Reseller(_Resource):
    """Provision and manage child orgs. Needs a key with the ``reseller:*`` scopes."""

    def list(self) -> _JSONDict:
        return self._c._get("/reseller/customers")

    def create(
        self,
        *,
        name: str,
        owner_email: Optional[str] = None,
        controller: Optional[Mapping[str, Any]] = None,
        white_label: Optional[Mapping[str, Any]] = None,
        delegated_access: Optional[bool] = None,
        mint_key: Optional[bool] = None,
        key_scopes: Optional[List[str]] = None,
    ) -> _JSONDict:
        """Provision a child org. With ``mint_key``, its first API key is returned once as ``apiKey``."""
        body: _JSONDict = {"name": name}
        for key, value in (
            ("ownerEmail", owner_email),
            ("controller", dict(controller) if controller is not None else None),
            ("whiteLabel", dict(white_label) if white_label is not None else None),
            ("delegatedAccess", delegated_access),
            ("mintKey", mint_key),
            ("keyScopes", list(key_scopes) if key_scopes is not None else None),
        ):
            if value is not None:
                body[key] = value
        return self._c.request("POST", "/reseller/customers", body=body)

    def get(self, id: str) -> _JSONDict:
        return self._c._get(f"/reseller/customers/{_e(id)}")

    def update(
        self,
        id: str,
        *,
        status: Optional[str] = None,
        delegated_access: Optional[bool] = None,
        dsar_routing: Any = _UNSET,
        controller: Optional[Mapping[str, Any]] = None,
    ) -> _JSONDict:
        """Update a child. Pass ``dsar_routing=None`` to clear its override."""
        body: _JSONDict = {}
        if status is not None:
            body["status"] = status
        if delegated_access is not None:
            body["delegatedAccess"] = delegated_access
        if dsar_routing is not _UNSET:
            body["dsarRouting"] = dsar_routing
        if controller is not None:
            body["controller"] = dict(controller)
        return self._c.request("PATCH", f"/reseller/customers/{_e(id)}", body=body)

    def deprovision(self, id: str, *, purge: bool = False) -> None:
        """Suspend a child (reversible). ``purge=True`` deletes it and its data — irreversibly."""
        self._c.request("DELETE", f"/reseller/customers/{_e(id)}{_qs({'purge': 'true' if purge else None})}")

    def list_keys(self, id: str) -> Any:
        return self._c._get(f"/reseller/customers/{_e(id)}/keys")

    def mint_key(
        self,
        id: str,
        *,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        cbids: Optional[List[str]] = None,
    ) -> _JSONDict:
        """Mint an API key for a child org; the secret is returned once."""
        body: _JSONDict = {}
        if name is not None:
            body["name"] = name
        if scopes is not None:
            body["scopes"] = list(scopes)
        if cbids is not None:
            body["cbids"] = list(cbids)
        return self._c.request("POST", f"/reseller/customers/{_e(id)}/keys", body=body)

    def revoke_key(self, id: str, prefix: str) -> None:
        self._c.request("DELETE", f"/reseller/customers/{_e(id)}/keys/{_e(prefix)}")


def _e(value: str) -> str:
    """URL-encode a single path segment."""
    return urllib.parse.quote(str(value), safe="")

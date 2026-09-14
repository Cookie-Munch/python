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

_JSONDict = Dict[str, Any]
_ChoicesLike = Union[t.ConsentChoices, Mapping[str, bool]]


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
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
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
        self.preferences = _Preferences(self)
        self.members = _Members(self)
        self.keys = _Keys(self)
        self.webhooks = _Webhooks(self)
        self.banners = _Banners(self)

    # -- transport ---------------------------------------------------------

    def _headers(self, extra: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Accept": "application/json",
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

    def usage(self) -> t.Usage:
        """GET /v1/usage — current resource usage for the org."""
        return t.from_dict(t.Usage, self._get("/usage"))

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

    def delete(self, cbid: str) -> None:
        self._c.request("DELETE", f"/sites/{_e(cbid)}")

    def get_config(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/config")

    def put_config(self, cbid: str, config: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("PUT", f"/sites/{_e(cbid)}/config", body=dict(config))

    def cookies(self, cbid: str) -> List[t.SiteCookie]:
        return t.from_list(t.SiteCookie, self._c._get(f"/sites/{_e(cbid)}/cookies"))

    def scan(self, cbid: str) -> t.ScanResult:
        return t.from_dict(t.ScanResult, self._c.request("POST", f"/sites/{_e(cbid)}/scan"))

    def scan_status(self, cbid: str) -> t.ScanResult:
        return t.from_dict(t.ScanResult, self._c._get(f"/sites/{_e(cbid)}/scan"))

    def ab(self, cbid: str) -> List[t.AbResult]:
        return t.from_list(t.AbResult, self._c._get(f"/sites/{_e(cbid)}/ab"))

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

    def brand(self, cbid: str) -> _JSONDict:
        return self._c.request("POST", f"/sites/{_e(cbid)}/brand", body={})

    def get_flow(self, cbid: str) -> _JSONDict:
        return self._c._get(f"/sites/{_e(cbid)}/flow")

    def edit_flow(self, cbid: str, operations: List[Mapping[str, Any]]) -> _JSONDict:
        return self._c.request(
            "POST", f"/sites/{_e(cbid)}/flow/ops", body={"operations": list(operations)}
        )

    def set_flow(self, cbid: str, config: Mapping[str, Any]) -> _JSONDict:
        return self._c.request("PUT", f"/sites/{_e(cbid)}/flow", body=dict(config))


class _Consent(_Resource):
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
    ) -> _JSONDict:
        body: _JSONDict = {
            "type": type,
            "subjectEmail": subject_email,
            "regulation": regulation,
        }
        if note is not None:
            body["note"] = note
        return self._c.request("POST", "/dsar", body=body)

    def advance(self, id: str, to_status: str) -> _JSONDict:
        return self._c.request("POST", f"/dsar/{_e(id)}/advance", body={"toStatus": to_status})


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

    def issue(self, *, name: Optional[str] = None) -> t.ApiKey:
        body: _JSONDict = {}
        if name is not None:
            body["name"] = name
        return t.from_dict(t.ApiKey, self._c.request("POST", "/keys", body=body))


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

    def delete(self, id: str) -> None:
        self._c.request("DELETE", f"/webhooks/{_e(id)}")


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


def _e(value: str) -> str:
    """URL-encode a single path segment."""
    return urllib.parse.quote(str(value), safe="")

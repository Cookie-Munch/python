"""Typed entities for the Cookie Munch Developer API.

These mirror ``packages/sdk/src/types.ts`` and the OpenAPI schemas. JSON on the wire
is camelCase (or PascalCase for the per-day consent stats); the dataclasses use
idiomatic ``snake_case`` and are populated by :func:`from_dict`, which converts keys
and ignores any unknown fields so a newer server never breaks an older client.

Open, deeply-nested shapes owned by other packages (``SiteConfig``, banner flows,
signed receipts) are intentionally left as plain ``dict`` values.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, TypeVar

__all__ = [
    "Identity",
    "Site",
    "SiteCookie",
    "ScanResult",
    "AbResult",
    "InstallSnippet",
    "VerifyResult",
    "ConsentDay",
    "ConsentChoices",
    "ConsentLogRow",
    "DsarRequest",
    "ScoredVendor",
    "RopaEntry",
    "Member",
    "ApiKey",
    "Usage",
    "WebhookSubscription",
    "BrandKit",
    "PreferenceItem",
    "BannerSummary",
    "BannerRecord",
    "Org",
    "from_dict",
    "from_list",
]

T = TypeVar("T")

_CAMEL_BOUNDARY_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_BOUNDARY_2 = re.compile(r"([a-z0-9])([A-Z])")


def camel_to_snake(name: str) -> str:
    """Convert a camelCase or PascalCase key to snake_case.

    ``orgId`` -> ``org_id``, ``keyPrefix`` -> ``key_prefix``, ``OptInImplied`` ->
    ``opt_in_implied``, ``Date`` -> ``date``.
    """
    step = _CAMEL_BOUNDARY_1.sub(r"\1_\2", name)
    return _CAMEL_BOUNDARY_2.sub(r"\1_\2", step).lower()


def from_dict(cls: Type[T], data: Any) -> T:
    """Build a dataclass instance from a JSON object, tolerating unknown keys.

    Keys are normalised camel/Pascal -> snake before matching, so the raw API JSON
    maps straight onto the dataclass fields. Unknown keys are dropped; missing keys
    fall back to the field's default. Non-dict input is returned unchanged (lets the
    generic response handling pass through open shapes).
    """
    if not isinstance(data, dict):
        return data  # type: ignore[return-value]
    field_names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    kwargs: Dict[str, Any] = {}
    for key, value in data.items():
        snake = camel_to_snake(key)
        if snake in field_names:
            kwargs[snake] = value
    return cls(**kwargs)  # type: ignore[call-arg]


def from_list(cls: Type[T], data: Any) -> List[T]:
    """Map :func:`from_dict` over a JSON array; returns ``[]`` for non-list input."""
    if not isinstance(data, list):
        return []
    return [from_dict(cls, item) for item in data]


@dataclass
class Identity:
    org_id: Optional[str] = None
    plan: Optional[str] = None
    key_prefix: Optional[str] = None


@dataclass
class SupportedLanguage:
    """A language the banner already has copy for."""

    code: Optional[str] = None
    name: Optional[str] = None
    endonym: Optional[str] = None
    rtl: Optional[bool] = None
    source: Optional[str] = None


@dataclass
class Site:
    cbid: Optional[str] = None
    org_id: Optional[str] = None
    domain: Optional[str] = None


@dataclass
class SiteCookie:
    name: Optional[str] = None
    domain: Optional[str] = None
    category: Optional[str] = None
    provider: Optional[str] = None
    purpose: Optional[str] = None
    expiry: Optional[str] = None
    first_seen: Optional[int] = None


@dataclass
class ScanResult:
    scan_id: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    pages_scanned: Optional[int] = None
    cookies_found: Optional[int] = None


@dataclass
class AbResult:
    variant: Optional[str] = None
    impressions: Optional[int] = None
    opt_in: Optional[int] = None
    opt_out: Optional[int] = None
    opt_in_rate: Optional[float] = None


@dataclass
class InstallSnippet:
    snippet: Optional[str] = None
    src: Optional[str] = None
    api: Optional[str] = None
    cbid: Optional[str] = None
    blocking_mode: Optional[str] = None


@dataclass
class VerifyResult:
    verified: bool = False
    method: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class ConsentDay:
    date: Optional[str] = None
    opt_in: Optional[int] = None
    opt_out: Optional[int] = None
    opt_in_implied: Optional[int] = None
    opt_in_strict: Optional[int] = None
    type_opt_in_pref: Optional[int] = None
    type_opt_in_stat: Optional[int] = None
    type_opt_in_mark: Optional[int] = None
    impressions: Optional[int] = None
    countries: Dict[str, int] = field(default_factory=dict)


@dataclass
class ConsentChoices:
    preferences: bool = False
    statistics: bool = False
    marketing: bool = False

    def to_json(self) -> Dict[str, bool]:
        return {
            "preferences": self.preferences,
            "statistics": self.statistics,
            "marketing": self.marketing,
        }


@dataclass
class ConsentLogRow:
    stamp: Optional[str] = None
    received_at: Optional[int] = None
    region: Optional[str] = None
    method: Optional[str] = None
    choices: Dict[str, bool] = field(default_factory=dict)
    anon_ip: Optional[str] = None
    url: Optional[str] = None


@dataclass
class DsarRequest:
    id: Optional[str] = None
    type: Optional[str] = None
    subject_email: Optional[str] = None
    regulation: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[int] = None
    due_at: Optional[int] = None
    note: Optional[str] = None


@dataclass
class ScoredVendor:
    id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    data_shared: List[str] = field(default_factory=list)
    dpa_signed: bool = False
    subprocessors: Optional[int] = None
    certifications: List[str] = field(default_factory=list)
    region: Optional[str] = None
    # Nested { score, band } left as a plain dict.
    risk: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RopaEntry:
    id: Optional[str] = None
    name: Optional[str] = None
    purpose: Optional[str] = None
    legal_basis: Optional[str] = None
    data_categories: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    retention_days: Optional[int] = None
    cross_border_transfer: bool = False


@dataclass
class Member:
    id: Optional[str] = None
    org_id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    created_at: Optional[int] = None


@dataclass
class ApiKey:
    id: Optional[str] = None
    org_id: Optional[str] = None
    prefix: Optional[str] = None
    name: Optional[str] = None
    created_at: Optional[int] = None
    last_used_at: Optional[int] = None
    # Present only in the response that first issues the key.
    secret: Optional[str] = None


@dataclass
class Usage:
    org_id: Optional[str] = None
    plan: Optional[str] = None
    period: Dict[str, int] = field(default_factory=dict)
    consents: Optional[int] = None
    sites: Optional[int] = None
    limit: Optional[int] = None


@dataclass
class WebhookSubscription:
    id: Optional[str] = None
    org_id: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: List[str] = field(default_factory=list)
    cbid: Optional[str] = None
    active: bool = False
    created_at: Optional[int] = None


@dataclass
class BrandKit:
    id: Optional[str] = None
    org_id: Optional[str] = None
    name: Optional[str] = None
    colors: Dict[str, str] = field(default_factory=dict)
    logo_url: Optional[str] = None
    font: Optional[str] = None
    created_at: Optional[int] = None


@dataclass
class PreferenceItem:
    id: Optional[str] = None
    org_id: Optional[str] = None
    cbid: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


@dataclass
class BannerSummary:
    id: Optional[str] = None
    name: Optional[str] = None
    updated_at: Optional[int] = None
    assigned_cbids: List[str] = field(default_factory=list)


@dataclass
class BannerRecord:
    id: Optional[str] = None
    org_id: Optional[str] = None
    name: Optional[str] = None
    json: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


@dataclass
class Org:
    """The key's organisation. Returned by ``org.get()`` / ``org.update()``."""

    id: Optional[str] = None
    name: Optional[str] = None
    plan: Optional[str] = None
    logo_url: Optional[str] = None

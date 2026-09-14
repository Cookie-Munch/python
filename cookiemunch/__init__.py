"""cookiemunch — a small, typed Python client for the Cookie Munch Developer API.

    from cookiemunch import CookieMunch

    cm = CookieMunch(api_key="fck_...", base_url="https://api.cookiemunch.net")
    identity = cm.me()
    sites = cm.sites.list()
    receipt = cm.consent.receipt("cbid", "stamp")

The client mirrors the reference TypeScript SDK (``@cookiemunch/sdk``); the org is
derived server-side from the API key, so callers never pass an orgId.
"""

from __future__ import annotations

from ._transport import HttpResponse, Transport, urllib_transport
from .client import DEFAULT_BASE_URL, CookieMunch
from .errors import CookieMunchApiError, CookieMunchError
from .types import (
    AbResult,
    ApiKey,
    BannerRecord,
    BannerSummary,
    BrandKit,
    ConsentChoices,
    ConsentDay,
    ConsentLogRow,
    DsarRequest,
    Identity,
    InstallSnippet,
    Member,
    PreferenceItem,
    RopaEntry,
    ScanResult,
    ScoredVendor,
    Site,
    SiteCookie,
    Usage,
    VerifyResult,
    WebhookSubscription,
)

__version__ = "0.1.0"

__all__ = [
    "CookieMunch",
    "CookieMunchApiError",
    "CookieMunchError",
    "DEFAULT_BASE_URL",
    "HttpResponse",
    "Transport",
    "urllib_transport",
    # entities
    "AbResult",
    "ApiKey",
    "BannerRecord",
    "BannerSummary",
    "BrandKit",
    "ConsentChoices",
    "ConsentDay",
    "ConsentLogRow",
    "DsarRequest",
    "Identity",
    "InstallSnippet",
    "Member",
    "PreferenceItem",
    "RopaEntry",
    "ScanResult",
    "ScoredVendor",
    "Site",
    "SiteCookie",
    "Usage",
    "VerifyResult",
    "WebhookSubscription",
    "__version__",
]

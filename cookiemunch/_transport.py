"""HTTP transport for the SDK.

The default transport uses only the Python standard library (``urllib``), so the
package installs with **zero third-party dependencies**. The transport is a plain
callable, which makes it trivial to inject a fake in tests (no network) or to swap
in ``httpx``/``requests`` if a caller prefers.

A transport is any callable with the signature::

    (method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpResponse
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

__all__ = ["HttpResponse", "Transport", "urllib_transport"]


@dataclass
class HttpResponse:
    """A minimal, framework-agnostic HTTP response."""

    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str) -> Optional[str]:
        """Case-insensitive header lookup."""
        lower = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lower:
                return value
        return None


#: The transport callable type.
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], HttpResponse]


def urllib_transport(
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    *,
    timeout: float = 30.0,
) -> HttpResponse:
    """Default stdlib transport. Never raises on non-2xx; returns the response so the
    client can map it to :class:`CookieMunchApiError`. Genuine network failures
    (DNS, connection refused, timeout) still propagate as ``urllib.error.URLError``.
    """
    req = urllib.request.Request(url=url, data=body, method=method.upper())
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - trusted API base
            return HttpResponse(
                status=resp.status,
                headers={k: v for k, v in resp.headers.items()},
                body=resp.read(),
            )
    except urllib.error.HTTPError as err:
        # HTTPError is a valid (non-2xx) response we want to surface, not a crash.
        return HttpResponse(
            status=err.code,
            headers={k: v for k, v in (err.headers or {}).items()},
            body=err.read() if err.fp is not None else b"",
        )

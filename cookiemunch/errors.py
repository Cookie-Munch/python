"""Errors raised by the Cookie Munch SDK."""

from __future__ import annotations

from typing import Optional


class CookieMunchError(Exception):
    """Base class for every error raised by this SDK."""


class CookieMunchApiError(CookieMunchError):
    """Raised for any non-2xx HTTP response from the API.

    Attributes:
        status: The HTTP status code.
        code:   The server's machine-readable ``code`` field, when present.
        body:   The raw response body (decoded text), for debugging.
    """

    def __init__(
        self,
        status: int,
        message: str,
        *,
        code: Optional[str] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body

    def __str__(self) -> str:  # pragma: no cover - trivial
        base = super().__str__()
        return f"[{self.status}] {base}" + (f" (code={self.code})" if self.code else "")

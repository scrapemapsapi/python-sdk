"""Typed exceptions raised by the ScrapeMapsAPI SDK.

Every API error carries the machine-readable ``code`` from the response body
(``{"detail": {"error": code, "message": str}}``), the HTTP ``status_code`` and,
when the server sent one, ``retry_after`` (seconds, from the ``Retry-After`` header).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx


class ScrapeMapsAPIError(Exception):
    """Base class for every error raised by the SDK."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        body: Any = None,
        retry_after: Optional[float] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.body = body
        self.retry_after = retry_after
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"[{self.code}]")
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)


class APIConnectionError(ScrapeMapsAPIError):
    """The server could not be reached (DNS, connection refused, TLS, ...)."""


class APITimeoutError(APIConnectionError):
    """The request timed out."""


class InvalidRequestError(ScrapeMapsAPIError):
    """400/422: invalid place identifier, cursor, location or parameters."""


class AuthenticationError(ScrapeMapsAPIError):
    """401: missing or invalid API key (also raised when no key is configured)."""


class InsufficientCreditsError(ScrapeMapsAPIError):
    """402: not enough credits. ``available`` and ``required`` are set when the API sends them."""

    @property
    def available(self) -> Optional[int]:
        return _detail_int(self.body, "available")

    @property
    def required(self) -> Optional[int]:
        return _detail_int(self.body, "required")


class NotFoundError(ScrapeMapsAPIError):
    """404: the place does not exist."""


PlaceNotFoundError = NotFoundError


class RateLimitError(ScrapeMapsAPIError):
    """429: too many requests. ``retry_after`` tells how many seconds to wait."""


class CreditsCooldownError(RateLimitError, InsufficientCreditsError):
    """429 ``insufficient_credits_retry_later``: the key kept calling with no credits and is in a
    cooldown. Top up credits; retrying sooner than ``retry_after`` will not help."""


class UpstreamError(ScrapeMapsAPIError):
    """502: Google Maps answered with an error. You were not charged."""


class ServiceUnavailableError(UpstreamError):
    """503: Google Maps is temporarily unreachable. You were not charged."""


class InternalServerError(ScrapeMapsAPIError):
    """500 and other unexpected 5xx responses."""


_CODE_MAP: dict[str, type[ScrapeMapsAPIError]] = {
    "invalid_place_id": InvalidRequestError,
    "invalid_cursor": InvalidRequestError,
    "invalid_location": InvalidRequestError,
    "validation_error": InvalidRequestError,
    "missing_api_key": AuthenticationError,
    "invalid_api_key": AuthenticationError,
    "insufficient_credits": InsufficientCreditsError,
    "place_not_found": NotFoundError,
    "rate_limited": RateLimitError,
    "rate_limit_exceeded": RateLimitError,
    "insufficient_credits_retry_later": CreditsCooldownError,
    "upstream_error": UpstreamError,
    "upstream_unavailable": ServiceUnavailableError,
}

_STATUS_MAP: dict[int, type[ScrapeMapsAPIError]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    404: NotFoundError,
    422: InvalidRequestError,
    429: RateLimitError,
    502: UpstreamError,
    503: ServiceUnavailableError,
}


def _detail_int(body: Any, key: str) -> Optional[int]:
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        value = body["detail"].get(key)
        if isinstance(value, int):
            return value
    return None


def parse_retry_after(headers: Mapping[str, str]) -> Optional[float]:
    """Seconds from a ``Retry-After`` header (only the delta-seconds form is used by the API)."""
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def parse_error_body(status_code: int, body: Any, text: str = "") -> tuple[Optional[str], str]:
    """Extract ``(code, message)`` from an error body, whatever its shape."""
    code: Optional[str] = None
    message = text.strip() or f"HTTP {status_code}"
    if isinstance(body, dict):
        detail = body.get("detail", body)
        if isinstance(detail, dict):
            code = detail.get("error") if isinstance(detail.get("error"), str) else None
            if isinstance(detail.get("message"), str):
                message = detail["message"]
        elif isinstance(detail, list):  # FastAPI 422: [{"loc": [...], "msg": "...", ...}]
            code = "validation_error"
            msgs = []
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(p) for p in item.get("loc", []) if p not in ("query", "path"))
                    msg = item.get("msg", "invalid value")
                    msgs.append(f"{loc}: {msg}" if loc else str(msg))
            if msgs:
                message = "; ".join(msgs)
        elif isinstance(detail, str):
            message = detail
    return code, message


def error_class_for(status_code: int, code: Optional[str]) -> type[ScrapeMapsAPIError]:
    # 5xx: the status decides. A 5xx body can carry an upstream code such as "rate_limited"
    # (Google throttled us) that must not turn into a client-side RateLimitError.
    if code and code in _CODE_MAP and status_code < 500:
        return _CODE_MAP[code]
    if status_code in _STATUS_MAP:
        return _STATUS_MAP[status_code]
    if status_code >= 500:
        return InternalServerError
    return ScrapeMapsAPIError


def error_from_response(response: httpx.Response) -> ScrapeMapsAPIError:
    """Build the typed exception for a non-2xx response."""
    try:
        body: Any = response.json()
    except Exception:
        body = None
    code, message = parse_error_body(response.status_code, body, response.text if body is None else "")
    cls = error_class_for(response.status_code, code)
    return cls(
        message,
        status_code=response.status_code,
        code=code,
        body=body,
        retry_after=parse_retry_after(response.headers),
    )

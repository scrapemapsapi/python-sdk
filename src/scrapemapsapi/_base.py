"""Configuration and logic shared by the sync and async clients (no I/O here)."""

from __future__ import annotations

import os
import random
from typing import Any, Mapping, Optional
from urllib.parse import quote

import httpx

from .errors import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    ScrapeMapsAPIError,
    error_from_response,
)
from .models import ResponseInfo

__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://api.scrapemapsapi.com"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 0.5
DEFAULT_MAX_RETRY_WAIT = 30.0
API_KEY_ENV = "SCRAPEMAPSAPI_API_KEY"
BASE_URL_ENV = "SCRAPEMAPSAPI_BASE_URL"
USER_AGENT = f"scrapemapsapi-python/{__version__}"

SEARCH_MAX_LIMIT = 20
REVIEWS_MAX_LIMIT = 100

RETRY_STATUSES = frozenset({429, 502, 503})
# A 429 from the no-credit cooldown lasts minutes and only a top-up lifts it: never retried.
NO_RETRY_CODES = frozenset({"insufficient_credits_retry_later"})


def place_path(place: str, suffix: str = "") -> str:
    """``/v1/places/{place}{suffix}`` with ``place`` URL-encoded (feature IDs contain ``:``)."""
    if not isinstance(place, str) or not place.strip():
        raise ValueError("place must be a non-empty place ID (ChIJ...), CID or feature ID")
    return f"/v1/places/{quote(place.strip(), safe='')}{suffix}"


def clean_params(params: Mapping[str, Any]) -> dict[str, Any]:
    """Drop None values (the API applies its own defaults)."""
    return {k: v for k, v in params.items() if v is not None}


def page_limit(page_size: Optional[int], max_items: Optional[int], seen: int, maximum: int) -> int:
    """Page size for the next auto-pagination request: never fetch (and pay for) more than needed."""
    size = min(page_size or maximum, maximum)
    if max_items is not None:
        size = min(size, max_items - seen)
    return max(1, size)


class BaseClient:
    """Holds configuration, headers and the retry policy."""

    def __init__(
        self,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: float,
        max_retries: int,
        retry_backoff: float,
        max_retry_wait: float,
    ) -> None:
        api_key = api_key or os.environ.get(API_KEY_ENV)
        if not api_key:
            raise AuthenticationError(f"No API key: pass api_key=... or set the {API_KEY_ENV} environment variable.")
        self.api_key = api_key
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff = max(0.0, float(retry_backoff))
        self.max_retry_wait = max(0.0, float(max_retry_wait))
        self.last_response_info: Optional[ResponseInfo] = None
        self._headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    @property
    def credits_remaining(self) -> Optional[int]:
        """Credits left, from the last successful response (None before the first call)."""
        return self.last_response_info.credits_remaining if self.last_response_info else None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _backoff(self, attempt: int) -> float:
        base = self.retry_backoff * (2**attempt)
        return min(base, self.max_retry_wait) * (0.5 + random.random() / 2)

    def _retry_wait(self, response: httpx.Response, attempt: int) -> tuple[Optional[float], ScrapeMapsAPIError]:
        """For an error response: ``(seconds to wait before retrying or None, the error)``."""
        error = error_from_response(response)
        if attempt >= self.max_retries or response.status_code not in RETRY_STATUSES or error.code in NO_RETRY_CODES:
            return None, error
        if error.retry_after is not None:
            if error.retry_after > self.max_retry_wait:
                return None, error
            return error.retry_after, error
        return self._backoff(attempt), error

    def _transport_retry_wait(
        self, exc: httpx.TransportError, attempt: int
    ) -> tuple[Optional[float], ScrapeMapsAPIError]:
        error: ScrapeMapsAPIError
        if isinstance(exc, httpx.TimeoutException):
            error = APITimeoutError(f"Request timed out after {self.timeout}s: {exc}")
        else:
            error = APIConnectionError(f"Could not reach {self.base_url}: {exc}")
        if attempt >= self.max_retries:
            return None, error
        return self._backoff(attempt), error

    def _record(self, response: httpx.Response) -> ResponseInfo:
        info = ResponseInfo.from_headers(response.headers)
        self.last_response_info = info
        return info

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as e:
            raise ScrapeMapsAPIError(
                f"Invalid JSON in response: {response.text[:200]!r}", status_code=response.status_code
            ) from e
        if not isinstance(body, dict):
            raise ScrapeMapsAPIError("Unexpected response shape", status_code=response.status_code, body=body)
        return body

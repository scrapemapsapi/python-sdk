"""Asynchronous ScrapeMapsAPI client."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

import httpx

from ._base import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_RETRY_WAIT,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_TIMEOUT,
    BaseClient,
    clean_params,
)
from .places import AsyncPlaces


class AsyncScrapeMapsAPI(BaseClient):
    """Asynchronous client for the ScrapeMapsAPI API (Google Maps places and reviews).

    Usage::

        from scrapemapsapi import AsyncScrapeMapsAPI

        async with AsyncScrapeMapsAPI() as client:  # reads SCRAPEMAPSAPI_API_KEY
            async for review in client.places.iter_reviews(place_id, max_items=50):
                print(review.rating, review.text)

    Args:
        api_key: API key; defaults to the ``SCRAPEMAPSAPI_API_KEY`` environment variable.
        base_url: API root; defaults to ``SCRAPEMAPSAPI_BASE_URL`` or https://api.scrapemapsapi.com.
        timeout: Seconds per request (reviews of large places can take a while upstream).
        max_retries: Retries on 429/502/503 and connection errors (0 disables them).
        retry_backoff: Base delay in seconds of the exponential backoff (with jitter).
        max_retry_wait: Longest wait accepted between retries; a ``Retry-After`` longer than
            this raises immediately instead of sleeping.
        http_client: Your own ``httpx.AsyncClient`` (proxies, transports, tests). Not closed by us.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
        max_retry_wait: float = DEFAULT_MAX_RETRY_WAIT,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(api_key, base_url, timeout, max_retries, retry_backoff, max_retry_wait)
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self.places = AsyncPlaces(self)

    async def _get(self, path: str, params: Mapping[str, Any]) -> tuple[dict[str, Any], httpx.Headers]:
        attempt = 0
        while True:
            try:
                response = await self._http.get(
                    self._url(path), params=clean_params(params), headers=self._headers, timeout=self.timeout
                )
            except httpx.TransportError as exc:
                wait, error = self._transport_retry_wait(exc, attempt)
                if wait is None:
                    raise error from exc
            else:
                if response.is_success:
                    body = self._json(response)
                    self._record(response)
                    return body, response.headers
                wait, error = self._retry_wait(response, attempt)
                if wait is None:
                    raise error
            attempt += 1
            await asyncio.sleep(wait)

    async def close(self) -> None:
        """Close the underlying HTTP client (only if the SDK created it)."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncScrapeMapsAPI:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

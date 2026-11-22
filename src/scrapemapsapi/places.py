"""The ``places`` resource: search, details, reviews, resolve, plus auto-paginating iterators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator, Optional

from ._base import REVIEWS_MAX_LIMIT, SEARCH_MAX_LIMIT, page_limit, place_path
from .models import (
    PlaceResponse,
    PlaceSummary,
    ResolveResponse,
    Review,
    ReviewSort,
    ReviewsResponse,
    SearchResponse,
)

if TYPE_CHECKING:
    from ._async_client import AsyncScrapeMapsAPI
    from ._client import ScrapeMapsAPI


def _search_params(
    q: str,
    language: Optional[str],
    region: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
    radius_km: Optional[float],
    limit: Optional[int],
    cursor: Optional[str],
) -> dict[str, Any]:
    if (lat is None) != (lng is None):
        raise ValueError("Provide both lat and lng, or neither.")
    return {
        "q": q,
        "language": language,
        "region": region,
        "lat": lat,
        "lng": lng,
        "radius_km": radius_km,
        "limit": limit,
        "cursor": cursor,
    }


def _reviews_params(
    sort: Optional[ReviewSort],
    language: Optional[str],
    original_language: Optional[str],
    limit: Optional[int],
    cursor: Optional[str],
) -> dict[str, Any]:
    return {
        "sort": sort,
        "language": language,
        "original_language": original_language,
        "limit": limit,
        "cursor": cursor,
    }


def _next(cursor: Optional[str], has_more: bool, previous: Optional[str]) -> Optional[str]:
    """Cursor of the next page, or None to stop (also guards against a repeated cursor)."""
    if not has_more or not cursor or cursor == previous:
        return None
    return cursor


class Places:
    """Synchronous ``client.places``."""

    def __init__(self, client: ScrapeMapsAPI) -> None:
        self._client = client

    def search(
        self,
        q: str,
        *,
        language: Optional[str] = None,
        region: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> SearchResponse:
        """Text search, optionally biased to an area (``lat``+``lng``, ``radius_km``).

        ``limit`` is 1-20 places per page (default 20). Billed 1 credit per place returned.
        Pass ``response.next_cursor`` as ``cursor`` for the next page, or use ``iter_search``.
        """
        params = _search_params(q, language, region, lat, lng, radius_km, limit, cursor)
        body, headers = self._client._get("/v1/places/search", params)
        return SearchResponse.from_dict(body, headers)

    def get(self, place: str, *, language: Optional[str] = None, region: Optional[str] = None) -> PlaceResponse:
        """Full details of a place. ``place`` is a place ID (ChIJ...), CID or feature ID (0x...:0x...).
        2 credits."""
        body, headers = self._client._get(place_path(place), {"language": language, "region": region})
        return PlaceResponse.from_dict(body, headers)

    def reviews(
        self,
        place: str,
        *,
        sort: Optional[ReviewSort] = None,
        language: Optional[str] = None,
        original_language: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> ReviewsResponse:
        """One page of reviews. ``sort``: relevant (default), newest, highest, lowest.
        ``language`` is also the translation target; ``original_language`` keeps only reviews
        written in that language. ``limit`` 1-100 (default 20). 1 credit per 2 reviews returned."""
        params = _reviews_params(sort, language, original_language, limit, cursor)
        body, headers = self._client._get(place_path(place, "/reviews"), params)
        return ReviewsResponse.from_dict(body, headers)

    def resolve(self, input: str) -> ResolveResponse:
        """Convert a place ID, CID, feature ID or Google Maps URL (short links too) into every
        identifier. Free when offline, 1 credit when a lookup is needed."""
        body, headers = self._client._get("/v1/places/resolve", {"input": input})
        return ResolveResponse.from_dict(body, headers)

    def iter_search(
        self,
        q: str,
        *,
        language: Optional[str] = None,
        region: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        page_size: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> Iterator[PlaceSummary]:
        """Yield every place of a search, following ``next_cursor`` until the end or ``max_items``."""
        seen = 0
        cursor: Optional[str] = None
        while max_items is None or seen < max_items:
            limit = page_limit(page_size, max_items, seen, SEARCH_MAX_LIMIT)
            page = self.search(
                q,
                language=language,
                region=region,
                lat=lat,
                lng=lng,
                radius_km=radius_km,
                limit=limit,
                cursor=cursor,
            )
            for place in page.data:
                yield place
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = _next(page.next_cursor, page.has_more and bool(page.data), cursor)
            if cursor is None:
                return

    def iter_reviews(
        self,
        place: str,
        *,
        sort: Optional[ReviewSort] = None,
        language: Optional[str] = None,
        original_language: Optional[str] = None,
        page_size: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> Iterator[Review]:
        """Yield every review of a place, following ``next_cursor`` until the end or ``max_items``."""
        seen = 0
        cursor: Optional[str] = None
        while max_items is None or seen < max_items:
            limit = page_limit(page_size, max_items, seen, REVIEWS_MAX_LIMIT)
            page = self.reviews(
                place,
                sort=sort,
                language=language,
                original_language=original_language,
                limit=limit,
                cursor=cursor,
            )
            for review in page.data:
                yield review
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = _next(page.next_cursor, page.has_more and bool(page.data), cursor)
            if cursor is None:
                return


class AsyncPlaces:
    """Asynchronous ``client.places``. Same methods as :class:`Places`, awaitable."""

    def __init__(self, client: AsyncScrapeMapsAPI) -> None:
        self._client = client

    async def search(
        self,
        q: str,
        *,
        language: Optional[str] = None,
        region: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> SearchResponse:
        """See :meth:`Places.search`."""
        params = _search_params(q, language, region, lat, lng, radius_km, limit, cursor)
        body, headers = await self._client._get("/v1/places/search", params)
        return SearchResponse.from_dict(body, headers)

    async def get(self, place: str, *, language: Optional[str] = None, region: Optional[str] = None) -> PlaceResponse:
        """See :meth:`Places.get`."""
        body, headers = await self._client._get(place_path(place), {"language": language, "region": region})
        return PlaceResponse.from_dict(body, headers)

    async def reviews(
        self,
        place: str,
        *,
        sort: Optional[ReviewSort] = None,
        language: Optional[str] = None,
        original_language: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> ReviewsResponse:
        """See :meth:`Places.reviews`."""
        params = _reviews_params(sort, language, original_language, limit, cursor)
        body, headers = await self._client._get(place_path(place, "/reviews"), params)
        return ReviewsResponse.from_dict(body, headers)

    async def resolve(self, input: str) -> ResolveResponse:
        """See :meth:`Places.resolve`."""
        body, headers = await self._client._get("/v1/places/resolve", {"input": input})
        return ResolveResponse.from_dict(body, headers)

    async def iter_search(
        self,
        q: str,
        *,
        language: Optional[str] = None,
        region: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius_km: Optional[float] = None,
        page_size: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> AsyncIterator[PlaceSummary]:
        """See :meth:`Places.iter_search`. Use with ``async for``."""
        seen = 0
        cursor: Optional[str] = None
        while max_items is None or seen < max_items:
            limit = page_limit(page_size, max_items, seen, SEARCH_MAX_LIMIT)
            page = await self.search(
                q,
                language=language,
                region=region,
                lat=lat,
                lng=lng,
                radius_km=radius_km,
                limit=limit,
                cursor=cursor,
            )
            for place in page.data:
                yield place
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = _next(page.next_cursor, page.has_more and bool(page.data), cursor)
            if cursor is None:
                return

    async def iter_reviews(
        self,
        place: str,
        *,
        sort: Optional[ReviewSort] = None,
        language: Optional[str] = None,
        original_language: Optional[str] = None,
        page_size: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> AsyncIterator[Review]:
        """See :meth:`Places.iter_reviews`. Use with ``async for``."""
        seen = 0
        cursor: Optional[str] = None
        while max_items is None or seen < max_items:
            limit = page_limit(page_size, max_items, seen, REVIEWS_MAX_LIMIT)
            page = await self.reviews(
                place,
                sort=sort,
                language=language,
                original_language=original_language,
                limit=limit,
                cursor=cursor,
            )
            for review in page.data:
                yield review
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            cursor = _next(page.next_cursor, page.has_more and bool(page.data), cursor)
            if cursor is None:
                return

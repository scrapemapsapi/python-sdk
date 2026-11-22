"""Async client: same surface as the sync one."""

from __future__ import annotations

import httpx
import pytest
from conftest import (
    API_KEY,
    BASE_URL,
    PLACE,
    PLACE_IDS,
    PLACE_SUMMARY,
    Recorder,
    error_response,
    json_response,
    make_review,
    reviews_body,
    search_body,
)

import scrapemapsapi._async_client as async_mod
from scrapemapsapi import AsyncScrapeMapsAPI, NotFoundError, RateLimitError


@pytest.fixture
async def client(recorder: Recorder):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    async with AsyncScrapeMapsAPI(API_KEY, base_url=BASE_URL, http_client=http, retry_backoff=0) as c:
        yield c
    await http.aclose()


async def test_search_and_get(client, recorder):
    recorder.add(
        json_response(search_body([PLACE_SUMMARY]), headers={"X-Credits-Remaining": "10"}),
        json_response({"data": PLACE, "meta": {"credits_used": 2, "cached": False, "language": "en"}}),
    )
    res = await client.places.search("pizza", limit=1)
    assert res.data[0].name == "Pizzeria Da Michele" and res.credits_remaining == 10
    place = (await client.places.get(res.data[0].ref)).data
    assert place.timezone == "Europe/Rome"
    assert recorder.last.url.path == f"/v1/places/{PLACE_IDS['place_id']}"


async def test_resolve(client, recorder):
    recorder.add(json_response({"data": PLACE_IDS, "meta": {"credits_used": 1, "cached": False}}))
    assert (await client.places.resolve("10281119596374313554")).data.feature_id == PLACE_IDS["feature_id"]


async def test_iter_reviews(client, recorder):
    recorder.add(
        json_response(reviews_body([make_review(1), make_review(2)], "c1")),
        json_response(reviews_body([make_review(3)])),
    )
    ids = [r.id async for r in client.places.iter_reviews("123", sort="newest")]
    assert ids == ["rev1", "rev2", "rev3"]
    assert recorder.requests[1].url.params["cursor"] == "c1"


async def test_iter_search_max_items(client, recorder):
    recorder.add(json_response(search_body([PLACE_SUMMARY] * 2, "c1")))
    places = [p async for p in client.places.iter_search("pizza", max_items=2)]
    assert len(places) == 2 and len(recorder.requests) == 1
    assert recorder.last.url.params["limit"] == "2"


async def test_error(client, recorder):
    recorder.add(error_response(404, "place_not_found", "Place not found"))
    with pytest.raises(NotFoundError, match="Place not found"):
        await client.places.reviews("123")


async def test_retry(client, recorder, monkeypatch):
    waits: list[float] = []

    async def fake_sleep(s: float) -> None:
        waits.append(s)

    monkeypatch.setattr(async_mod.asyncio, "sleep", fake_sleep)
    recorder.add(error_response(429, "rate_limited", headers={"Retry-After": "2"}), json_response(search_body([])))
    await client.places.search("x")
    assert waits == [2.0]

    recorder.add(*[error_response(429, "rate_limited") for _ in range(3)])
    with pytest.raises(RateLimitError):
        await client.places.search("x")

"""Shared fixtures: sample payloads shaped exactly like the API's, and a mock transport."""

from __future__ import annotations

import copy
import json
from typing import Any, Callable

import httpx
import pytest

BASE_URL = "https://api.test.scrapemapsapi"
API_KEY = "test_key_123"

PLACE_IDS = {
    "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "cid": "10281119596374313554",
    "feature_id": "0x6b12ae37b4b75b37:0x8eadf8dc1b32ca52",
    "google_maps_url": "https://www.google.com/maps?cid=10281119596374313554",
}

PLACE_SUMMARY = {
    "id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
    "ids": PLACE_IDS,
    "name": "Pizzeria Da Michele",
    "categories": ["Pizza restaurant"],
    "address": {
        "formatted": "Via Cesare Sersale, 1, 80139 Napoli NA, Italy",
        "street": "Via Cesare Sersale, 1",
        "postal_code": "80139",
        "city": "Napoli",
        "region": "Campania",
        "country_code": "IT",
    },
    "location": {"lat": 40.8497, "lng": 14.2635},
    "rating": 4.6,
    "review_count": 52000,
    "phone": "081 553 9204",
    "website": "https://damichele.net",
    "status": "operational",
}

PLACE = {
    **PLACE_SUMMARY,
    "local_name": "L'Antica Pizzeria da Michele",
    "phone_international": "+39 081 553 9204",
    "plus_code": "RQ2G+V9 Napoli",
    "timezone": "Europe/Rome",
    "description": "Historic pizzeria.",
    "opening_hours": {
        "weekly": [
            {
                "day": "monday",
                "closed": False,
                "open_24h": False,
                "periods": [{"open": "11:00", "close": "23:00"}],
                "text": "11 am-11 pm",
            },
            {"day": "sunday", "closed": True, "open_24h": False, "periods": [], "text": "Closed"},
        ],
        "status_text": "Open · Closes 11 pm",
    },
    "attributes": {"Accessibility": ["Wheelchair-accessible entrance"]},
    "photos": [{"url": "https://lh3.example/p1", "width": 800, "height": 600}],
    "booking_links": [{"url": "https://book.example/x", "domain": "book.example"}],
    "knowledge_graph_id": "/g/11b6",
}


def make_review(i: int) -> dict[str, Any]:
    return {
        "id": f"rev{i}",
        "rating": 5,
        "published_at": "2026-10-01T12:00:00Z",
        "relative_date": "a month ago",
        "language": "it",
        "text": f"Ottima pizza {i}",
        "translated_text": f"Great pizza {i}",
        "author": {"id": f"a{i}"},
        "owner_response": {"text": "Grazie!", "translated_text": "Thanks!", "relative_date": "a month ago"},
        "photos": [],
        "details": {"Food": "5"},
        "source": "Google",
    }


def search_body(places: list[dict], next_cursor: str | None = None) -> dict[str, Any]:
    return {
        "data": places,
        "pagination": {"next_cursor": next_cursor, "has_more": next_cursor is not None},
        "meta": {"credits_used": len(places), "cached": False, "query": "pizza", "language": "en", "region": "us"},
    }


def reviews_body(reviews: list[dict], next_cursor: str | None = None) -> dict[str, Any]:
    return {
        "data": reviews,
        "pagination": {"next_cursor": next_cursor, "has_more": next_cursor is not None},
        "meta": {
            "credits_used": (len(reviews) + 1) // 2,
            "cached": True,
            "place_id": PLACE_IDS["place_id"],
            "cid": PLACE_IDS["cid"],
            "sort": "newest",
            "language": "en",
            "original_language": None,
        },
    }


def json_response(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status, content=json.dumps(body).encode(), headers={"content-type": "application/json", **(headers or {})}
    )


def error_response(
    status: int, code: str, message: str = "boom", headers: dict[str, str] | None = None, **extra: Any
) -> httpx.Response:
    return json_response({"detail": {"error": code, "message": message, **extra}}, status, headers)


class Recorder:
    """A MockTransport handler that replays queued responses and records requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.queue: list[httpx.Response | Exception | Callable[[httpx.Request], httpx.Response]] = []

    def add(self, *items: Any) -> Recorder:
        self.queue.extend(items)
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.queue:
            raise AssertionError(f"unexpected request {request.url}")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            return item(request)
        return copy.copy(item)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCRAPEMAPSAPI_API_KEY", raising=False)
    monkeypatch.delenv("SCRAPEMAPSAPI_BASE_URL", raising=False)

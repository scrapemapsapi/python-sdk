"""Sync client: configuration, requests, parsing, pagination."""

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
    json_response,
    make_review,
    reviews_body,
    search_body,
)

from scrapemapsapi import (
    AuthenticationError,
    Place,
    PlaceSummary,
    Review,
    ScrapeMapsAPI,
    __version__,
)
from scrapemapsapi._base import DEFAULT_BASE_URL


@pytest.fixture
def client(recorder: Recorder):
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    c = ScrapeMapsAPI(API_KEY, base_url=BASE_URL, http_client=http, retry_backoff=0)
    yield c
    http.close()


class TestInit:
    def test_defaults(self):
        c = ScrapeMapsAPI("k")
        assert c.base_url == DEFAULT_BASE_URL == "https://api.scrapemapsapi.com"
        assert c.max_retries == 2
        assert c.credits_remaining is None
        c.close()

    def test_env_vars(self, monkeypatch):
        monkeypatch.setenv("SCRAPEMAPSAPI_API_KEY", "env_key")
        monkeypatch.setenv("SCRAPEMAPSAPI_BASE_URL", "http://localhost:8000/")
        with ScrapeMapsAPI() as c:
            assert c.api_key == "env_key"
            assert c.base_url == "http://localhost:8000"

    def test_argument_beats_env(self, monkeypatch):
        monkeypatch.setenv("SCRAPEMAPSAPI_BASE_URL", "http://env")
        with ScrapeMapsAPI("k", base_url="http://arg/") as c:
            assert c.base_url == "http://arg"

    def test_missing_key(self):
        with pytest.raises(AuthenticationError, match="SCRAPEMAPSAPI_API_KEY"):
            ScrapeMapsAPI()

    def test_repr_hides_key(self):
        with ScrapeMapsAPI("secret_key") as c:
            assert "secret_key" not in repr(c)


class TestSearch:
    def test_params_headers_and_parsing(self, client, recorder):
        recorder.add(
            json_response(
                search_body([PLACE_SUMMARY], "cur1"),
                headers={
                    "X-Credits-Used": "1",
                    "X-Credits-Remaining": "199",
                    "X-Cache": "MISS",
                    "X-Processing-Time": "321",
                },
            )
        )
        res = client.places.search("pizza", language="it", region="it", lat=40.85, lng=14.26, radius_km=2, limit=5)
        req = recorder.last
        assert req.url.path == "/v1/places/search"
        assert dict(req.url.params) == {
            "q": "pizza",
            "language": "it",
            "region": "it",
            "lat": "40.85",
            "lng": "14.26",
            "radius_km": "2",
            "limit": "5",
        }
        assert req.headers["X-API-Key"] == API_KEY
        assert req.headers["User-Agent"] == f"scrapemapsapi-python/{__version__}"

        assert isinstance(res.data[0], PlaceSummary)
        p = res.data[0]
        assert p.name == "Pizzeria Da Michele"
        assert p.ids.feature_id == PLACE_IDS["feature_id"]
        assert p.address.city == "Napoli" and p.location.lat == 40.8497
        assert p.status == "operational" and p.ref == PLACE_IDS["place_id"]
        assert res.next_cursor == "cur1" and res.has_more
        assert res.meta.query == "pizza" and res.meta.credits_used == 1
        assert res.credits_used == 1 and res.credits_remaining == 199
        assert res.info.cache == "MISS" and res.info.processing_time_ms == 321
        assert client.credits_remaining == 199

    def test_omits_unset_params(self, client, recorder):
        recorder.add(json_response(search_body([])))
        res = client.places.search("pizza")
        assert dict(recorder.last.url.params) == {"q": "pizza"}
        assert res.data == [] and not res.has_more
        assert res.credits_used == 0 and res.credits_remaining is None

    def test_lat_without_lng(self, client):
        with pytest.raises(ValueError):
            client.places.search("pizza", lat=1.0)

    def test_place_without_place_id(self, client, recorder):
        summary = {**PLACE_SUMMARY, "id": None, "ids": {**PLACE_IDS, "place_id": None}, "status": None}
        recorder.add(json_response(search_body([summary])))
        p = client.places.search("x").data[0]
        assert p.id is None and p.ref == PLACE_IDS["cid"]


class TestGet:
    def test_details(self, client, recorder):
        recorder.add(
            json_response(
                {"data": PLACE, "meta": {"credits_used": 2, "cached": True, "language": "it"}},
                headers={"X-Credits-Used": "2", "X-Credits-Remaining": "50"},
            )
        )
        res = client.places.get(PLACE_IDS["place_id"], language="it")
        assert recorder.last.url.path == f"/v1/places/{PLACE_IDS['place_id']}"
        assert dict(recorder.last.url.params) == {"language": "it"}
        place = res.data
        assert isinstance(place, Place)
        assert place.local_name == "L'Antica Pizzeria da Michele"
        assert place.opening_hours is not None
        assert place.opening_hours.weekly[0].periods[0].open == "11:00"
        assert place.opening_hours.weekly[1].closed is True
        assert place.attributes["Accessibility"] == ["Wheelchair-accessible entrance"]
        assert place.photos[0].width == 800 and place.booking_links[0].domain == "book.example"
        assert res.meta.cached and res.meta.language == "it"
        assert res.credits_used == 2 and res.credits_remaining == 50

    def test_feature_id_is_url_encoded(self, client, recorder):
        recorder.add(json_response({"data": PLACE, "meta": {"credits_used": 2, "cached": False, "language": "en"}}))
        client.places.get(PLACE_IDS["feature_id"])
        assert recorder.last.url.raw_path == b"/v1/places/0x6b12ae37b4b75b37%3A0x8eadf8dc1b32ca52"

    def test_unknown_fields_are_ignored(self, client, recorder):
        recorder.add(
            json_response(
                {
                    "data": {**PLACE, "brand_new_field": 1, "opening_hours": None},
                    "meta": {"credits_used": 2, "cached": False, "language": "en", "extra": True},
                }
            )
        )
        assert client.places.get("123").data.opening_hours is None

    def test_empty_place_rejected(self, client):
        with pytest.raises(ValueError):
            client.places.get("  ")


class TestReviews:
    def test_page(self, client, recorder):
        recorder.add(json_response(reviews_body([make_review(1), make_review(2)], "c2")))
        res = client.places.reviews("123", sort="newest", original_language="it", limit=2)
        assert recorder.last.url.path == "/v1/places/123/reviews"
        assert dict(recorder.last.url.params) == {"sort": "newest", "original_language": "it", "limit": "2"}
        r = res.data[0]
        assert isinstance(r, Review)
        assert r.translated_text == "Great pizza 1" and r.author.id == "a1"
        assert r.owner_response is not None and r.owner_response.translated_text == "Thanks!"
        assert r.details == {"Food": "5"} and r.source == "Google"
        assert res.meta.cid == PLACE_IDS["cid"] and res.meta.sort == "newest"
        assert res.next_cursor == "c2"


class TestResolve:
    def test_resolve(self, client, recorder):
        recorder.add(json_response({"data": PLACE_IDS, "meta": {"credits_used": 0, "cached": False}}))
        res = client.places.resolve("https://maps.app.goo.gl/abc")
        assert recorder.last.url.path == "/v1/places/resolve"
        assert recorder.last.url.params["input"] == "https://maps.app.goo.gl/abc"
        assert res.data.cid == PLACE_IDS["cid"] and res.data.place_id == PLACE_IDS["place_id"]
        assert res.credits_used == 0


class TestPagination:
    def test_iter_search_follows_cursor(self, client, recorder):
        recorder.add(
            json_response(search_body([PLACE_SUMMARY, PLACE_SUMMARY], "c1")),
            json_response(search_body([PLACE_SUMMARY], None)),
        )
        places = list(client.places.iter_search("pizza", region="it"))
        assert len(places) == 3
        assert "cursor" not in recorder.requests[0].url.params
        assert recorder.requests[0].url.params["limit"] == "20"
        assert recorder.requests[1].url.params["cursor"] == "c1"
        assert recorder.requests[1].url.params["region"] == "it"

    def test_iter_reviews_max_items_caps_page_size(self, client, recorder):
        recorder.add(
            json_response(reviews_body([make_review(i) for i in range(3)], "c1")),
            json_response(reviews_body([make_review(i) for i in range(3, 5)], "c2")),
        )
        reviews = list(client.places.iter_reviews("123", page_size=3, max_items=5, sort="newest"))
        assert [r.id for r in reviews] == ["rev0", "rev1", "rev2", "rev3", "rev4"]
        assert recorder.requests[0].url.params["limit"] == "3"
        assert recorder.requests[1].url.params["limit"] == "2"  # only what is still needed
        assert recorder.requests[1].url.params["cursor"] == "c1"
        assert len(recorder.requests) == 2

    def test_iter_reviews_default_page_size(self, client, recorder):
        recorder.add(json_response(reviews_body([make_review(1)])))
        assert len(list(client.places.iter_reviews("123"))) == 1
        assert recorder.last.url.params["limit"] == "100"

    def test_stops_on_repeated_cursor(self, client, recorder):
        recorder.add(
            json_response(reviews_body([make_review(1)], "same")),
            json_response(reviews_body([make_review(2)], "same")),
        )
        assert len(list(client.places.iter_reviews("123"))) == 2
        assert len(recorder.requests) == 2

    def test_stops_on_empty_page(self, client, recorder):
        recorder.add(json_response(reviews_body([], "c1")))
        assert list(client.places.iter_reviews("123")) == []
        assert len(recorder.requests) == 1

    def test_lazy(self, client, recorder):
        recorder.add(json_response(search_body([PLACE_SUMMARY], "c1")))
        it = client.places.iter_search("pizza")
        assert recorder.requests == []
        next(it)
        assert len(recorder.requests) == 1

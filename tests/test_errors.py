"""Error mapping and retry policy."""

from __future__ import annotations

import httpx
import pytest
from conftest import API_KEY, BASE_URL, PLACE_IDS, Recorder, error_response, json_response

import scrapemapsapi._client as client_mod
from scrapemapsapi import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    CreditsCooldownError,
    InsufficientCreditsError,
    InternalServerError,
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    ScrapeMapsAPI,
    ScrapeMapsAPIError,
    ServiceUnavailableError,
    UpstreamError,
)

RESOLVE_OK = {"data": PLACE_IDS, "meta": {"credits_used": 0, "cached": False}}


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", calls.append)
    return calls


def make_client(recorder: Recorder, **kwargs) -> ScrapeMapsAPI:
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    return ScrapeMapsAPI(API_KEY, base_url=BASE_URL, http_client=http, **kwargs)


@pytest.mark.parametrize(
    "status,code,cls",
    [
        (400, "invalid_place_id", InvalidRequestError),
        (400, "invalid_cursor", InvalidRequestError),
        (400, "invalid_location", InvalidRequestError),
        (401, "missing_api_key", AuthenticationError),
        (401, "invalid_api_key", AuthenticationError),
        (402, "insufficient_credits", InsufficientCreditsError),
        (404, "place_not_found", NotFoundError),
        (429, "rate_limit_exceeded", RateLimitError),
        (429, "insufficient_credits_retry_later", CreditsCooldownError),
        (502, "upstream_error", UpstreamError),
        (502, "proxy_error", UpstreamError),
        (502, "rate_limited", UpstreamError),
        (503, "upstream_unavailable", ServiceUnavailableError),
        (500, "internal_server_error", InternalServerError),
        (500, "something_else", InternalServerError),
        (418, "teapot", ScrapeMapsAPIError),
    ],
)
def test_error_codes(recorder, sleeps, status, code, cls):
    recorder.add(error_response(status, code, "explained"))
    c = make_client(recorder, max_retries=0)
    with pytest.raises(cls) as ei:
        c.places.resolve("x")
    assert type(ei.value) is cls
    assert ei.value.code == code and ei.value.status_code == status
    assert ei.value.message == "explained"
    assert "explained" in str(ei.value) and code in str(ei.value)


def test_hierarchy():
    assert issubclass(ServiceUnavailableError, UpstreamError)
    assert issubclass(CreditsCooldownError, RateLimitError)
    assert issubclass(CreditsCooldownError, InsufficientCreditsError)
    assert issubclass(APITimeoutError, APIConnectionError)


def test_status_fallback_without_code(recorder):
    recorder.add(httpx.Response(404, text="not here"))
    with pytest.raises(NotFoundError, match="not here"):
        make_client(recorder).places.get("1")


def test_validation_422(recorder):
    recorder.add(
        json_response(
            {"detail": [{"loc": ["query", "limit"], "msg": "Input should be <= 20", "type": "less_than_equal"}]}, 422
        )
    )
    with pytest.raises(InvalidRequestError, match="limit: Input should be <= 20") as ei:
        make_client(recorder).places.search("x", limit=50)
    assert ei.value.code == "validation_error"


def test_validation_422_real_fastapi_body(recorder):
    # The body FastAPI really sends (input and ctx included)
    recorder.add(
        json_response(
            {
                "detail": [
                    {
                        "type": "less_than_equal",
                        "loc": ["query", "limit"],
                        "msg": "Input should be less than or equal to 20",
                        "input": "50",
                        "ctx": {"le": 20},
                    }
                ]
            },
            422,
        )
    )
    with pytest.raises(InvalidRequestError, match="limit: Input should be less than or equal to 20") as ei:
        make_client(recorder).places.search("x", limit=50)
    assert ei.value.code == "validation_error" and ei.value.status_code == 422


def test_plain_text_429_from_the_edge(recorder):
    # The edge proxy answers bursts with a text body and no error code
    recorder.add(httpx.Response(429, text="Too Many Requests", headers={"Retry-After": "1"}))
    with pytest.raises(RateLimitError, match="Too Many Requests") as ei:
        make_client(recorder, max_retries=0).places.get("1")
    assert ei.value.code is None and ei.value.retry_after == 1


def test_insufficient_credits_details(recorder):
    recorder.add(error_response(402, "insufficient_credits", available=1, required=2))
    with pytest.raises(InsufficientCreditsError) as ei:
        make_client(recorder).places.get("1")
    assert ei.value.available == 1 and ei.value.required == 2


class TestRetries:
    def test_retries_503_then_succeeds(self, recorder, sleeps):
        recorder.add(
            error_response(503, "upstream_unavailable"),
            error_response(502, "upstream_error"),
            json_response(RESOLVE_OK),
        )
        res = make_client(recorder).places.resolve("x")
        assert res.data.cid == PLACE_IDS["cid"]
        assert len(recorder.requests) == 3 and len(sleeps) == 2

    def test_gives_up_after_max_retries(self, recorder, sleeps):
        recorder.add(*[error_response(503, "upstream_unavailable") for _ in range(4)])
        with pytest.raises(ServiceUnavailableError):
            make_client(recorder, max_retries=3).places.resolve("x")
        assert len(recorder.requests) == 4 and len(sleeps) == 3

    def test_backoff_grows(self, recorder, sleeps):
        recorder.add(*[error_response(502, "upstream_error") for _ in range(3)])
        with pytest.raises(UpstreamError):
            make_client(recorder, retry_backoff=1.0).places.resolve("x")
        assert 0.5 <= sleeps[0] <= 1.0 and 1.0 <= sleeps[1] <= 2.0

    def test_honours_retry_after(self, recorder, sleeps):
        recorder.add(error_response(429, "rate_limited", headers={"Retry-After": "3"}), json_response(RESOLVE_OK))
        make_client(recorder).places.resolve("x")
        assert sleeps == [3.0]

    def test_retry_after_too_long_raises(self, recorder, sleeps):
        recorder.add(error_response(429, "rate_limited", headers={"Retry-After": "120"}))
        with pytest.raises(RateLimitError) as ei:
            make_client(recorder, max_retry_wait=30).places.resolve("x")
        assert ei.value.retry_after == 120.0 and sleeps == []

    def test_credit_cooldown_not_retried(self, recorder, sleeps):
        recorder.add(error_response(429, "insufficient_credits_retry_later", headers={"Retry-After": "5"}))
        with pytest.raises(CreditsCooldownError) as ei:
            make_client(recorder).places.resolve("x")
        assert ei.value.retry_after == 5.0 and sleeps == [] and len(recorder.requests) == 1

    @pytest.mark.parametrize(
        "status,code",
        [(404, "place_not_found"), (402, "insufficient_credits"), (400, "invalid_place_id"), (500, "internal")],
    )
    def test_not_retried(self, recorder, sleeps, status, code):
        recorder.add(error_response(status, code))
        with pytest.raises(ScrapeMapsAPIError):
            make_client(recorder).places.resolve("x")
        assert len(recorder.requests) == 1 and sleeps == []

    def test_disabled(self, recorder, sleeps):
        recorder.add(error_response(503, "upstream_unavailable"))
        with pytest.raises(ServiceUnavailableError):
            make_client(recorder, max_retries=0).places.resolve("x")
        assert sleeps == []

    def test_connection_error_retried(self, recorder, sleeps):
        recorder.add(httpx.ConnectError("refused"), json_response(RESOLVE_OK))
        make_client(recorder).places.resolve("x")
        assert len(recorder.requests) == 2

    def test_connection_error_raised(self, recorder, sleeps):
        recorder.add(httpx.ConnectError("refused"))
        with pytest.raises(APIConnectionError, match="Could not reach"):
            make_client(recorder, max_retries=0).places.resolve("x")

    def test_timeout_raised(self, recorder, sleeps):
        recorder.add(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"))
        with pytest.raises(APITimeoutError):
            make_client(recorder, max_retries=1).places.resolve("x")


def test_invalid_json_body(recorder):
    recorder.add(httpx.Response(200, text="<html>"))
    with pytest.raises(ScrapeMapsAPIError, match="Invalid JSON"):
        make_client(recorder).places.resolve("x")

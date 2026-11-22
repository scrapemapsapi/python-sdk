# ScrapeMapsAPI Python SDK

Official Python SDK for the [ScrapeMapsAPI](https://scrapemapsapi.com) API: search Google Maps places, get full place details and page through **all** the reviews of a place.

- Sync (`ScrapeMapsAPI`) and async (`AsyncScrapeMapsAPI`) clients
- Typed models (dataclasses) that match the API's JSON field by field
- Auto-paginating iterators: `iter_search` and `iter_reviews`
- Typed exceptions per error code, automatic retries on 429/502/503
- Credits used/remaining on every result

## Installation

```bash
pip install scrapemapsapi
```

Python 3.9+. The only dependency is `httpx`.

## Quick start

```python
from scrapemapsapi import ScrapeMapsAPI

client = ScrapeMapsAPI(api_key="your_api_key")  # or set SCRAPEMAPSAPI_API_KEY

# Search
page = client.places.search("pizzeria in Naples", language="it", region="it", limit=5)
for place in page.data:
    print(place.name, place.rating, place.review_count, place.address.formatted)

# Details (2 credits)
place = client.places.get(page.data[0].ref).data
print(place.phone_international, place.website, place.timezone)
if place.opening_hours:
    for day in place.opening_hours.weekly:
        print(day.day, "closed" if day.closed else day.text)

# One page of reviews
reviews = client.places.reviews(place.ref, sort="newest", limit=20)
for review in reviews.data:
    print(review.rating, review.published_at, review.translated_text or review.text)

print("credits used:", reviews.credits_used, "remaining:", reviews.credits_remaining)
```

`place` can be a place ID (`ChIJ...`), a CID (`10281119596374313554`) or a feature ID (`0x...:0x...`). `PlaceSummary.ref` gives the best one for a result (`id`, else `ids.cid`).

## Auto-pagination

The iterators follow `next_cursor` for you and stop at the end or at `max_items`. They request only what is still needed, so `max_items` also caps what you pay.

```python
# Every review written in Italian, newest first, translated to English
for review in client.places.iter_reviews(place_id, sort="newest", original_language="it", language="en"):
    print(review.rating, review.text)

# At most 50 places for a query in an area
for place in client.places.iter_search("coffee", lat=45.4642, lng=9.19, radius_km=2, max_items=50):
    print(place.name)
```

Optional `page_size` sets the page size (search 1–20, reviews 1–100).

Manual paging is available too:

```python
page = client.places.reviews(place_id, limit=100)
while page.has_more:
    page = client.places.reviews(place_id, limit=100, cursor=page.next_cursor)
```

## Resolve identifiers and Google Maps URLs

```python
ids = client.places.resolve("https://maps.app.goo.gl/xxxx").data
print(ids.place_id, ids.cid, ids.feature_id, ids.google_maps_url)
```

Free when the conversion is offline, 1 credit when a lookup is needed (short links, CID only).

## Async

```python
import asyncio
from scrapemapsapi import AsyncScrapeMapsAPI


async def main():
    async with AsyncScrapeMapsAPI() as client:
        page = await client.places.search("ramen in Tokyo", language="ja", region="jp")
        async for review in client.places.iter_reviews(page.data[0].ref, max_items=200):
            print(review.rating, review.text)


asyncio.run(main())
```

## Configuration

```python
client = ScrapeMapsAPI(
    api_key="...",  # default: SCRAPEMAPSAPI_API_KEY
    base_url="http://localhost:8000",  # default: SCRAPEMAPSAPI_BASE_URL or https://api.scrapemapsapi.com
    timeout=60.0,  # seconds per request
    max_retries=2,  # retries on 429/502/503 and connection errors; 0 disables
    retry_backoff=0.5,  # base of the exponential backoff (with jitter)
    max_retry_wait=30.0,  # never sleep longer than this; a longer Retry-After raises
    http_client=None,  # your own httpx.Client (proxies, custom transports)
)
```

Retries honour the `Retry-After` header. A `429 insufficient_credits_retry_later` (key in a no-credit cooldown) is never retried: top up instead.

## Credits

Every result exposes the billing headers:

| Attribute | Source |
|---|---|
| `result.credits_used` | `X-Credits-Used` (falls back to `meta.credits_used`) |
| `result.credits_remaining` | `X-Credits-Remaining` |
| `result.info.cache` | `X-Cache` (`HIT` / `MISS`) |
| `client.credits_remaining` | from the last successful call (handy with iterators) |

Costs: search 1 credit per place returned, details 2, reviews 1 per 2 reviews returned (rounded up), resolve 0–1. Errors and empty pages are free.

## Errors

```python
from scrapemapsapi import (
    ScrapeMapsAPIError,
    NotFoundError,
    InsufficientCreditsError,
    RateLimitError,
    InvalidRequestError,
    AuthenticationError,
    UpstreamError,
    ServiceUnavailableError,
)

try:
    client.places.get("ChIJ...")
except NotFoundError:
    ...
except RateLimitError as e:
    print("retry in", e.retry_after, "s")
except ScrapeMapsAPIError as e:
    print(e.status_code, e.code, e.message)
```

| Exception | HTTP | Codes |
|---|---|---|
| `InvalidRequestError` | 400, 422 | `invalid_place_id`, `invalid_cursor`, `invalid_location`, `validation_error` |
| `AuthenticationError` | 401 | `missing_api_key`, `invalid_api_key` (also raised when no key is configured) |
| `InsufficientCreditsError` | 402 | `insufficient_credits` (`.available`, `.required`) |
| `NotFoundError` (alias `PlaceNotFoundError`) | 404 | `place_not_found` |
| `RateLimitError` | 429 | `rate_limit_exceeded`, or no code on a plain-text 429 from the edge proxy (`.retry_after`) |
| `CreditsCooldownError` (both `RateLimitError` and `InsufficientCreditsError`) | 429 | `insufficient_credits_retry_later` |
| `UpstreamError` | 502 | `upstream_error`, `proxy_error` (short link could not be followed) |
| `ServiceUnavailableError` (subclass of `UpstreamError`) | 503 | `upstream_unavailable` |
| `InternalServerError` | 500, other 5xx | `internal_server_error` |
| `APIConnectionError` / `APITimeoutError` | none | network failure / timeout |

All inherit from `ScrapeMapsAPIError`.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .

# Against a real server (spends a few credits; skipped when the key is unset)
SCRAPEMAPSAPI_API_KEY=... SCRAPEMAPSAPI_BASE_URL=http://localhost:8000 .venv/bin/python examples/live_check.py
```

## License

MIT

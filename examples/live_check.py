"""Smoke test against a real ScrapeMapsAPI server. Spends a few credits.

Usage:
    SCRAPEMAPSAPI_API_KEY=... [SCRAPEMAPSAPI_BASE_URL=http://localhost:8000] python examples/live_check.py

Does nothing (exit 0) when SCRAPEMAPSAPI_API_KEY is not set.
Cost: ~1 search credit + 2 (details) + ~3 (6 reviews) + 0-1 (resolve).
"""

from __future__ import annotations

import os
import sys

from scrapemapsapi import NotFoundError, ScrapeMapsAPI, ScrapeMapsAPIError


def main() -> int:
    if not os.environ.get("SCRAPEMAPSAPI_API_KEY"):
        print("SCRAPEMAPSAPI_API_KEY not set: skipping live check.")
        return 0

    query = sys.argv[1] if len(sys.argv) > 1 else "pizzeria in Naples"
    with ScrapeMapsAPI(max_retries=1) as client:
        print(f"Server: {client.base_url}")
        try:
            search = client.places.search(query, limit=1)
            print(
                f"search: {len(search.data)} place(s), credits used {search.credits_used}, "
                f"remaining {search.credits_remaining}"
            )
            if not search.data:
                print("No places found; stopping.")
                return 1
            first = search.data[0]
            print(f"  -> {first.name} | {first.address.formatted} | rating {first.rating}")

            place = client.places.get(first.ref).data
            print(f"get: {place.name}, timezone {place.timezone}, {len(place.photos)} photo(s)")
            if place.opening_hours:
                print(f"  hours: {place.opening_hours.status_text}")

            reviews = list(client.places.iter_reviews(first.ref, sort="newest", page_size=3, max_items=6))
            print(f"iter_reviews: {len(reviews)} review(s)")
            for r in reviews[:3]:
                text = (r.translated_text or r.text or "").replace("\n", " ")[:80]
                print(f"  {r.rating}* {r.relative_date}: {text}")

            resolved = client.places.resolve(first.ids.cid).data
            print(f"resolve: cid {resolved.cid} -> place_id {resolved.place_id}")

            try:
                client.places.get("0x0:0x1")
            except NotFoundError as e:
                print(f"expected not found: {e}")
            except ScrapeMapsAPIError as e:
                print(f"(unknown place raised {type(e).__name__}: {e})")
        except ScrapeMapsAPIError as e:
            print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        print(f"OK. Credits remaining: {client.credits_remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

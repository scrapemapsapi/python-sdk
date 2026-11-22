"""Typed response models. Field names match the API's JSON exactly.

Every model has a ``from_dict`` constructor that ignores unknown keys, so a newer API
that adds fields never breaks an older SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional

PlaceStatus = Literal["operational", "temporarily_closed", "permanently_closed"]
ReviewSort = Literal["relevant", "newest", "highest", "lowest"]
Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Location:
    lat: float
    lng: float

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Location:
        return cls(lat=d["lat"], lng=d["lng"])


@dataclass
class Address:
    formatted: Optional[str] = None
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country_code: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Address:
        return cls(
            formatted=d.get("formatted"),
            street=d.get("street"),
            postal_code=d.get("postal_code"),
            city=d.get("city"),
            region=d.get("region"),
            country_code=d.get("country_code"),
        )


@dataclass
class PlaceIds:
    """Every identifier of a place. ``place_id`` (ChIJ...) can be null for some places."""

    cid: str
    feature_id: str
    google_maps_url: str
    place_id: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PlaceIds:
        return cls(
            place_id=d.get("place_id"),
            cid=d["cid"],
            feature_id=d["feature_id"],
            google_maps_url=d["google_maps_url"],
        )


#: ``places.resolve()`` returns the same shape as ``PlaceIds``.
ResolvedIds = PlaceIds


@dataclass
class TimePeriod:
    open: str
    """HH:MM, 24h, local time."""
    close: str
    """HH:MM, 24h; may be lower than ``open`` when past midnight."""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TimePeriod:
        return cls(open=d["open"], close=d["close"])


@dataclass
class DayHours:
    day: Weekday
    closed: bool
    open_24h: bool = False
    periods: List[TimePeriod] = field(default_factory=list)
    text: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> DayHours:
        return cls(
            day=d["day"],
            closed=bool(d.get("closed", False)),
            open_24h=bool(d.get("open_24h", False)),
            periods=[TimePeriod.from_dict(p) for p in _list(d.get("periods"))],
            text=d.get("text"),
        )


@dataclass
class OpeningHours:
    weekly: List[DayHours] = field(default_factory=list)
    status_text: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> OpeningHours:
        return cls(
            weekly=[DayHours.from_dict(x) for x in _list(d.get("weekly"))],
            status_text=d.get("status_text"),
        )


@dataclass
class Photo:
    url: str
    width: Optional[int] = None
    height: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Photo:
        return cls(url=d["url"], width=d.get("width"), height=d.get("height"))


@dataclass
class Link:
    url: str
    domain: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Link:
        return cls(url=d["url"], domain=d.get("domain"))


def _summary_kwargs(d: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": d.get("id"),
        "ids": PlaceIds.from_dict(d["ids"]),
        "name": d["name"],
        "categories": list(_list(d.get("categories"))),
        "address": Address.from_dict(_dict(d.get("address"))),
        "location": Location.from_dict(d["location"]),
        "rating": d.get("rating"),
        "review_count": d.get("review_count"),
        "phone": d.get("phone"),
        "website": d.get("website"),
        "status": d.get("status"),
    }


@dataclass
class PlaceSummary:
    """A place as returned by search."""

    ids: PlaceIds
    name: str
    address: Address
    location: Location
    id: Optional[str] = None
    """Place ID (ChIJ...), the primary identifier. Null for the rare places without one: use ``ids.cid``."""
    categories: List[str] = field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    status: Optional[PlaceStatus] = None

    @property
    def ref(self) -> str:
        """The best identifier to pass to ``places.get()`` / ``places.reviews()``."""
        return self.id or self.ids.place_id or self.ids.cid

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PlaceSummary:
        return cls(**_summary_kwargs(d))


@dataclass
class Place(PlaceSummary):
    """A place with full details."""

    local_name: Optional[str] = None
    phone_international: Optional[str] = None
    plus_code: Optional[str] = None
    timezone: Optional[str] = None
    description: Optional[str] = None
    opening_hours: Optional[OpeningHours] = None
    attributes: Dict[str, List[str]] = field(default_factory=dict)
    photos: List[Photo] = field(default_factory=list)
    booking_links: List[Link] = field(default_factory=list)
    knowledge_graph_id: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Place:
        hours = d.get("opening_hours")
        return cls(
            **_summary_kwargs(d),
            local_name=d.get("local_name"),
            phone_international=d.get("phone_international"),
            plus_code=d.get("plus_code"),
            timezone=d.get("timezone"),
            description=d.get("description"),
            opening_hours=OpeningHours.from_dict(hours) if isinstance(hours, dict) else None,
            attributes={k: list(v) for k, v in _dict(d.get("attributes")).items()},
            photos=[Photo.from_dict(p) for p in _list(d.get("photos"))],
            booking_links=[Link.from_dict(x) for x in _list(d.get("booking_links"))],
            knowledge_graph_id=d.get("knowledge_graph_id"),
        )


@dataclass
class ReviewAuthor:
    id: Optional[str] = None
    """Pseudonymous, stable author ID. Names, photos and profile links are never returned."""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ReviewAuthor:
        return cls(id=d.get("id"))


@dataclass
class OwnerResponse:
    text: str
    translated_text: Optional[str] = None
    relative_date: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> OwnerResponse:
        return cls(
            text=d.get("text") or "",
            translated_text=d.get("translated_text"),
            relative_date=d.get("relative_date"),
        )


@dataclass
class Review:
    id: str
    author: ReviewAuthor = field(default_factory=ReviewAuthor)
    rating: Optional[int] = None
    published_at: Optional[str] = None
    """ISO 8601, UTC."""
    relative_date: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None
    translated_text: Optional[str] = None
    """Google's translation into the requested language, when different from the original."""
    owner_response: Optional[OwnerResponse] = None
    photos: List[Photo] = field(default_factory=list)
    details: Dict[str, str] = field(default_factory=dict)
    """Structured answers, e.g. ``{"Price per person": "€20–30", "Food": "5"}``."""
    source: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Review:
        owner = d.get("owner_response")
        return cls(
            id=d["id"],
            author=ReviewAuthor.from_dict(_dict(d.get("author"))),
            rating=d.get("rating"),
            published_at=d.get("published_at"),
            relative_date=d.get("relative_date"),
            language=d.get("language"),
            text=d.get("text"),
            translated_text=d.get("translated_text"),
            owner_response=OwnerResponse.from_dict(owner) if isinstance(owner, dict) else None,
            photos=[Photo.from_dict(p) for p in _list(d.get("photos"))],
            details=dict(_dict(d.get("details"))),
            source=d.get("source"),
        )


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------


@dataclass
class Pagination:
    has_more: bool
    next_cursor: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Pagination:
        return cls(has_more=bool(d.get("has_more")), next_cursor=d.get("next_cursor"))


@dataclass
class Meta:
    credits_used: int
    cached: bool

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Meta:
        return cls(credits_used=int(d.get("credits_used", 0)), cached=bool(d.get("cached")))


@dataclass
class SearchMeta(Meta):
    query: str = ""
    language: str = ""
    region: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> SearchMeta:
        return cls(
            credits_used=int(d.get("credits_used", 0)),
            cached=bool(d.get("cached")),
            query=d.get("query", ""),
            language=d.get("language", ""),
            region=d.get("region", ""),
        )


@dataclass
class PlaceMeta(Meta):
    language: str = ""

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PlaceMeta:
        return cls(
            credits_used=int(d.get("credits_used", 0)),
            cached=bool(d.get("cached")),
            language=d.get("language", ""),
        )


@dataclass
class ReviewsMeta(Meta):
    cid: str = ""
    sort: ReviewSort = "relevant"
    language: str = ""
    place_id: Optional[str] = None
    original_language: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ReviewsMeta:
        return cls(
            credits_used=int(d.get("credits_used", 0)),
            cached=bool(d.get("cached")),
            place_id=d.get("place_id"),
            cid=d.get("cid", ""),
            sort=d.get("sort", "relevant"),
            language=d.get("language", ""),
            original_language=d.get("original_language"),
        )


def _header_int(headers: Mapping[str, str], name: str) -> Optional[int]:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@dataclass
class ResponseInfo:
    """Billing and cache information read from the response headers."""

    credits_used: Optional[int] = None
    """``X-Credits-Used``: credits charged for this call."""
    credits_remaining: Optional[int] = None
    """``X-Credits-Remaining``: credits left on the account after this call."""
    cache: Optional[str] = None
    """``X-Cache``: ``HIT`` or ``MISS``."""
    processing_time_ms: Optional[int] = None

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> ResponseInfo:
        return cls(
            credits_used=_header_int(headers, "x-credits-used"),
            credits_remaining=_header_int(headers, "x-credits-remaining"),
            cache=headers.get("x-cache"),
            processing_time_ms=_header_int(headers, "x-processing-time"),
        )


class _WithInfo:
    info: ResponseInfo
    meta: Meta

    @property
    def credits_used(self) -> int:
        """Credits charged for this call (header, falling back to ``meta.credits_used``)."""
        if self.info.credits_used is not None:
            return self.info.credits_used
        return self.meta.credits_used

    @property
    def credits_remaining(self) -> Optional[int]:
        """Credits left after this call, or None if the server did not say."""
        return self.info.credits_remaining


@dataclass
class SearchResponse(_WithInfo):
    data: List[PlaceSummary]
    pagination: Pagination
    meta: SearchMeta
    info: ResponseInfo = field(default_factory=ResponseInfo)

    @property
    def next_cursor(self) -> Optional[str]:
        return self.pagination.next_cursor

    @property
    def has_more(self) -> bool:
        return self.pagination.has_more

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None) -> SearchResponse:
        return cls(
            data=[PlaceSummary.from_dict(x) for x in _list(d.get("data"))],
            pagination=Pagination.from_dict(_dict(d.get("pagination"))),
            meta=SearchMeta.from_dict(_dict(d.get("meta"))),
            info=ResponseInfo.from_headers(headers or {}),
        )


@dataclass
class PlaceResponse(_WithInfo):
    data: Place
    meta: PlaceMeta
    info: ResponseInfo = field(default_factory=ResponseInfo)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None) -> PlaceResponse:
        return cls(
            data=Place.from_dict(d["data"]),
            meta=PlaceMeta.from_dict(_dict(d.get("meta"))),
            info=ResponseInfo.from_headers(headers or {}),
        )


@dataclass
class ReviewsResponse(_WithInfo):
    data: List[Review]
    pagination: Pagination
    meta: ReviewsMeta
    info: ResponseInfo = field(default_factory=ResponseInfo)

    @property
    def next_cursor(self) -> Optional[str]:
        return self.pagination.next_cursor

    @property
    def has_more(self) -> bool:
        return self.pagination.has_more

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None) -> ReviewsResponse:
        return cls(
            data=[Review.from_dict(x) for x in _list(d.get("data"))],
            pagination=Pagination.from_dict(_dict(d.get("pagination"))),
            meta=ReviewsMeta.from_dict(_dict(d.get("meta"))),
            info=ResponseInfo.from_headers(headers or {}),
        )


@dataclass
class ResolveResponse(_WithInfo):
    data: ResolvedIds
    meta: Meta
    info: ResponseInfo = field(default_factory=ResponseInfo)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None) -> ResolveResponse:
        return cls(
            data=PlaceIds.from_dict(d["data"]),
            meta=Meta.from_dict(_dict(d.get("meta"))),
            info=ResponseInfo.from_headers(headers or {}),
        )

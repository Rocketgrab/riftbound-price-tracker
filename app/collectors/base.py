from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FoundListing:
    marketplace: str
    external_id: str
    title: str
    price_native: float
    currency: str
    listing_type: str  # sold | active | wtb
    url: str
    observed_at: datetime | None = None


@dataclass
class CollectResult:
    marketplace: str
    listings: list[FoundListing] = field(default_factory=list)
    error: str | None = None
    seen_ids: list[str] = field(default_factory=list)


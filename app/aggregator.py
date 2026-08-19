from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.classify import LANG_EN, LANG_KO, LANG_ZH, SKU_PLAYER, SKU_SIGNATURE
from app.db import DailyAggregate, RawListing
from app.stats import iqr_keep, median

SKUS = (SKU_SIGNATURE, SKU_PLAYER)
LANGS = (LANG_EN, LANG_KO, LANG_ZH)
MARKETPLACES = ("ebay", "ebay_au", "ebay_us", "bunjang_kr", "bunjang_global", "karrot", "xianyu")


def rebuild_aggregates(session: Session, day: date | None = None) -> int:
    query = select(RawListing).where(
        RawListing.kept.is_(True),
        RawListing.listing_type.in_(("active", "presale")),
    )
    if day:
        query = query.where(RawListing.observed_on == day)
    rows = session.scalars(query).all()

    buckets: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        if row.language not in LANGS or row.sku not in SKUS:
            continue
        keys = [
            (row.observed_on, "ALL", row.sku, row.language),
            (row.observed_on, row.marketplace, row.sku, row.language),
        ]
        for key in keys:
            buckets[key].append(row.price_usd)

    written = 0
    if day:
        session.execute(delete(DailyAggregate).where(DailyAggregate.date == day))
    else:
        session.execute(delete(DailyAggregate))

    for (agg_date, marketplace, sku, language), prices in buckets.items():
        clean = iqr_keep(prices)
        if not clean:
            continue
        session.add(
            DailyAggregate(
                date=agg_date,
                marketplace=marketplace,
                sku=sku,
                language=language,
                high_usd=round(max(clean), 2),
                low_usd=round(min(clean), 2),
                median_usd=round(median(clean), 2),
                volume=len(prices),
                sample_count=len(clean),
            )
        )
        written += 1
    session.commit()
    return written

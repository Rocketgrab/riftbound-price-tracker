from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.classify import LANG_EN, LANG_KO, LANG_ZH, SKU_PLAYER, SKU_SIGNATURE
from app.db import DailyAggregate, RawListing
from app.markets import HOME_MARKETS
from app.stats import iqr_keep, median

SKUS = (SKU_SIGNATURE, SKU_PLAYER)
LANGS = (LANG_EN, LANG_KO, LANG_ZH)
MARKETPLACES = ("ebay", "ebay_au", "ebay_us", "bunjang_kr", "bunjang_global", "karrot", "xianyu", "taobao", "dewu", "zhuanzhuan", "jd", "weidian")


def rebuild_aggregates(session: Session, day: date | None = None) -> int:
    query = select(RawListing).where(
        RawListing.kept.is_(True),
        RawListing.listing_type.in_(("active", "presale", "sold")),
    )
    if day:
        query = query.where(RawListing.observed_on == day)
    rows = session.scalars(query).all()

    ask_buckets: dict[tuple, list[float]] = defaultdict(list)
    sold_buckets: dict[tuple, int] = defaultdict(int)
    for row in rows:
        if row.language not in LANGS or row.sku not in SKUS:
            continue
        keys = [(row.observed_on, row.marketplace, row.sku, row.language)]
        # Language series for "ALL" is the home market only, so eBay asks for
        # Korean/Chinese copies cannot pull those medians up.
        if row.marketplace in HOME_MARKETS.get(row.language, ()):
            keys.append((row.observed_on, "ALL", row.sku, row.language))
        for key in keys:
            if row.listing_type == "sold":
                sold_buckets[key] += 1
            else:
                ask_buckets[key].append(row.price_usd)

    written = 0
    if day:
        session.execute(delete(DailyAggregate).where(DailyAggregate.date == day))
    else:
        session.execute(delete(DailyAggregate))

    keys = set(ask_buckets) | set(sold_buckets)
    for key in keys:
        agg_date, marketplace, sku, language = key
        prices = ask_buckets.get(key) or []
        clean = iqr_keep(prices) if prices else []
        session.add(
            DailyAggregate(
                date=agg_date,
                marketplace=marketplace,
                sku=sku,
                language=language,
                high_usd=round(max(clean), 2) if clean else 0,
                low_usd=round(min(clean), 2) if clean else 0,
                median_usd=round(median(clean), 2) if clean else 0,
                volume=len(prices),
                sample_count=len(clean),
                sold_volume=sold_buckets.get(key, 0),
            )
        )
        written += 1
    session.commit()
    return written

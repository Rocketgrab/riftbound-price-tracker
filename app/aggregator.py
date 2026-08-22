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

# Recovered from the 20 Aug 2026 17:26 UTC snapshot before leftover solds
# overwrote that day's ask book (median 0, volume 0). Values are USD.
WIPED_ASK_DAYS = (
    {
        "date": date(2026, 8, 20),
        "marketplace": "ALL",
        "sku": SKU_SIGNATURE,
        "language": LANG_KO,
        "median_usd": 1149.85,
        "high_usd": 1437.32,
        "low_usd": 862.39,
        "volume": 65,
        "sample_count": 65,
        "sold_volume": 6,
    },
    {
        "date": date(2026, 8, 20),
        "marketplace": "bunjang_kr",
        "sku": SKU_SIGNATURE,
        "language": LANG_KO,
        "median_usd": 1149.85,
        "high_usd": 1437.32,
        "low_usd": 862.39,
        "volume": 65,
        "sample_count": 65,
        "sold_volume": 6,
    },
    {
        "date": date(2026, 8, 20),
        "marketplace": "ALL",
        "sku": SKU_SIGNATURE,
        "language": LANG_ZH,
        "median_usd": 892.38,
        "high_usd": 966.74,
        "low_usd": 847.76,
        "volume": 5,
        "sample_count": 5,
        "sold_volume": 0,
    },
    {
        "date": date(2026, 8, 20),
        "marketplace": "xianyu",
        "sku": SKU_SIGNATURE,
        "language": LANG_ZH,
        "median_usd": 892.38,
        "high_usd": 966.74,
        "low_usd": 847.76,
        "volume": 5,
        "sample_count": 5,
        "sold_volume": 0,
    },
)


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
        # Live asks belong on the last-seen day so re-scrapes do not empty "today".
        if row.listing_type != "sold":
            ask_day = row.last_seen_on or row.observed_on
            keys = [(ask_day, row.marketplace, row.sku, row.language)]
        # Language series for "ALL" is the home market only, so eBay asks for
        # Korean/Chinese copies cannot pull those medians up.
        if row.marketplace in HOME_MARKETS.get(row.language, ()):
            keys.append((keys[0][0], "ALL", row.sku, row.language))
        for key in keys:
            if row.listing_type == "sold":
                sold_buckets[key] += 1
            else:
                ask_buckets[key].append(row.price_usd)

    keys = set(ask_buckets) | set(sold_buckets)
    ask_dates = {key[0] for key in ask_buckets}
    today = date.today()
    existing_dates = set(session.scalars(select(DailyAggregate.date).distinct()).all())

    # Re-scrapes used to move active listings onto "today". Do not rebuild a
    # past day from leftover solds only — that writes median 0 / volume 0.
    if day:
        dates_to_write = {day}
    elif not existing_dates:
        dates_to_write = ask_dates or {today}
    else:
        dates_to_write = {today} | (ask_dates - existing_dates)

    if dates_to_write:
        session.execute(delete(DailyAggregate).where(DailyAggregate.date.in_(dates_to_write)))

    written = 0
    for key in keys:
        agg_date, marketplace, sku, language = key
        if agg_date not in dates_to_write:
            continue
        prices = ask_buckets.get(key) or []
        clean = iqr_keep(prices) if prices else []
        sold_volume = sold_buckets.get(key, 0)
        if not clean and not sold_volume:
            continue
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
                sold_volume=sold_volume,
            )
        )
        written += 1
    written += _restore_wiped_ask_days(session)
    session.commit()
    return written


def _restore_wiped_ask_days(session: Session) -> int:
    written = 0
    for spec in WIPED_ASK_DAYS:
        existing = session.scalar(
            select(DailyAggregate).where(
                DailyAggregate.date == spec["date"],
                DailyAggregate.marketplace == spec["marketplace"],
                DailyAggregate.sku == spec["sku"],
                DailyAggregate.language == spec["language"],
            )
        )
        if existing and existing.sample_count:
            continue
        if existing:
            session.delete(existing)
            session.flush()
        session.add(DailyAggregate(**spec))
        written += 1
    return written

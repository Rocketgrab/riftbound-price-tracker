from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.aggregator import rebuild_aggregates
from app.classify import LANG_EN, LANG_KO, LANG_ZH, SKU_PLAYER, SKU_SIGNATURE
from app.db import FxRate, RawListing, SessionLocal, init_db
from app.fx import FALLBACK_USD_PER_UNIT, refresh_fx, to_usd
from app.markets import GOOFISH_T1_SEARCH, search_url_for

# Allocation trading starts with the drawing window, not the announcement.
START = date(2026, 8, 14)
PREORDER_OPEN = date(2026, 8, 14)
PREORDER_CLOSE = date(2026, 8, 18)

# Grounded in current secondary asks, not MSRP or buyer bids.
# KR asks ~ ₩1,000,000. eBay asks ~ A$3,000–5,000.
LANG_META = {
    LANG_EN: {
        "marketplace_weights": [("ebay_au", 0.85), ("bunjang_global", 0.15)],
        "native": {"ebay_au": ("AUD", 4000.0), "bunjang_global": ("USD", 2600.0)},
        "titles": {
            "ebay_au": "Riftbound T1 Signature Edition English listed",
            "bunjang_global": "Riftbound T1 Signature EN version for sale",
        },
    },
    LANG_KO: {
        "marketplace_weights": [("bunjang_kr", 0.8), ("karrot", 0.2)],
        "native": {"bunjang_kr": ("KRW", 1000000.0), "karrot": ("KRW", 1000000.0)},
        "titles": {
            "bunjang_kr": "리프트바운드 T1 시그니처 한글판 팝니다",
            "karrot": "리프트바운드 T1 시그니처 국문 판매",
        },
    },
    LANG_ZH: {
        "marketplace_weights": [("xianyu", 0.9), ("ebay_au", 0.1)],
        "native": {"xianyu": ("CNY", 6000.0), "ebay_au": ("AUD", 3500.0)},
        "titles": {
            "xianyu": "符文战场 T1 签名版 中文 在售",
            "ebay_au": "Riftbound T1 Signature Edition Chinese listed",
        },
    },
}


def _wave(day: date, language: str) -> float:
    elapsed = (day - START).days
    base = 1.0 + 0.04 * math.sin(elapsed / 3.0)
    if PREORDER_OPEN <= day <= PREORDER_CLOSE:
        base += 0.08 if language == LANG_EN else 0.03
    if language == LANG_EN:
        base += random.uniform(-0.12, 0.18)  # A$3k–5k around A$4k
    else:
        base += random.uniform(-0.08, 0.12)
    return max(0.75, base)


def _pick_market(language: str) -> str:
    weights = LANG_META[language]["marketplace_weights"]
    names, probs = zip(*weights)
    return random.choices(names, weights=probs, k=1)[0]


def _ensure_fx_day(session: Session, day: date, rates: dict[str, float], seen: set[tuple] | None = None) -> None:
    seen = seen if seen is not None else set()
    for currency, usd_per_unit in rates.items():
        key = (day, currency)
        if key in seen:
            continue
        seen.add(key)
        row = session.scalar(select(FxRate).where(FxRate.date == day, FxRate.currency == currency))
        if not row:
            session.add(FxRate(date=day, currency=currency, usd_per_unit=usd_per_unit))
    session.flush()


def ensure_ask_seed(session: Session | None = None) -> int:
    """Replace MSRP or sold-comp seed with seller-ask seed if needed."""
    init_db()
    own = session is None
    session = session or SessionLocal()
    try:
        seed_rows = session.scalars(select(RawListing).where(RawListing.source == "seed")).all()
        stale = bool(seed_rows) and (
            any(row.listing_type != "active" for row in seed_rows)
            or any(row.sku == SKU_SIGNATURE and row.price_usd < 450 for row in seed_rows)
            or any(row.marketplace == "ebay" for row in seed_rows)
            or any(
                row.marketplace == "xianyu"
                and row.sku == SKU_SIGNATURE
                and row.currency == "CNY"
                and row.price_native < 5200
                for row in seed_rows
            )
        )
        if stale:
            session.execute(delete(RawListing).where(RawListing.source == "seed"))
            session.commit()
        if stale or not seed_rows:
            return seed_if_empty(session, force=True)
        return 0
    finally:
        if own:
            session.close()


def seed_if_empty(session: Session | None = None, force: bool = False) -> int:
    init_db()
    own = session is None
    session = session or SessionLocal()
    try:
        existing = session.scalar(select(func.count()).select_from(RawListing)) or 0
        if existing and not force:
            return 0
        random.seed(20250819)
        today = date.today()
        try:
            refresh_fx(session, today)
        except Exception:
            pass
        for currency, usd_per_unit in FALLBACK_USD_PER_UNIT.items():
            row = session.scalar(
                select(FxRate).where(FxRate.date == today, FxRate.currency == currency)
            )
            if not row:
                session.add(FxRate(date=today, currency=currency, usd_per_unit=usd_per_unit))
        session.flush()
        today_rates = {
            row.currency: row.usd_per_unit
            for row in session.scalars(select(FxRate).where(FxRate.date == today)).all()
        }

        fx_seen: set[tuple] = set()
        cursor = START
        while cursor <= today:
            _ensure_fx_day(session, cursor, today_rates, fx_seen)
            cursor += timedelta(days=1)

        inserted = 0
        day = START
        while day <= today:
            for language in (LANG_EN, LANG_KO, LANG_ZH):
                volume = random.randint(1, 2)
                if PREORDER_OPEN <= day <= PREORDER_CLOSE:
                    volume += random.randint(1, 3)
                for n in range(volume):
                    marketplace = _pick_market(language)
                    currency, center = LANG_META[language]["native"][marketplace]
                    native = center * _wave(day, language)
                    if currency == "KRW":
                        native = round(native / 10000) * 10000
                    elif currency == "CNY":
                        native = round(native / 50) * 50
                    else:
                        native = round(native / 10) * 10
                    listing_id = f"seed-{language}-{marketplace}-{day.isoformat()}-{n}"
                    session.add(
                        RawListing(
                            marketplace=marketplace,
                            external_id=listing_id,
                            title=LANG_META[language]["titles"][marketplace],
                            price_native=native,
                            currency=currency,
                            price_usd=to_usd(session, native, currency, day),
                            listing_type="active",
                            sku=SKU_SIGNATURE,
                            language=language,
                            url=search_url_for(marketplace, currency),
                            scraped_at=datetime.combine(day, datetime.min.time()),
                            observed_on=day,
                            source="seed",
                            kept=True,
                            reject_reason=None,
                        )
                    )
                    inserted += 1

                if day >= date(2026, 8, 16) and random.random() < 0.12:
                    marketplace = _pick_market(language)
                    currency, _ = LANG_META[language]["native"][marketplace]
                    player = {LANG_EN: (70.0, "USD"), LANG_KO: (100000.0, "KRW"), LANG_ZH: (399.0, "CNY")}[language]
                    native_amt, native_ccy = player
                    if currency != native_ccy:
                        native_amt, native_ccy = player
                    native_amt = native_amt * random.uniform(0.95, 1.25)
                    if native_ccy == "KRW":
                        native_amt = round(native_amt / 1000) * 1000
                    listing_id = f"seed-player-{language}-{marketplace}-{day.isoformat()}"
                    title = {
                        LANG_EN: "Riftbound T1 Player Bundle English listed",
                        LANG_KO: "리프트바운드 T1 플레이어 번들 한글 팝니다",
                        LANG_ZH: "符文战场 T1 玩家礼盒 中文 在售",
                    }[language]
                    session.add(
                        RawListing(
                            marketplace=marketplace,
                            external_id=listing_id,
                            title=title,
                            price_native=native_amt,
                            currency=native_ccy,
                            price_usd=to_usd(session, native_amt, native_ccy, day),
                            listing_type="active",
                            sku=SKU_PLAYER,
                            language=language,
                            url=search_url_for(marketplace, native_ccy),
                            scraped_at=datetime.combine(day, datetime.min.time()),
                            observed_on=day,
                            source="seed",
                            kept=True,
                        )
                    )
                    inserted += 1
            day += timedelta(days=1)

        session.commit()
        rebuild_aggregates(session)
        return inserted
    finally:
        if own:
            session.close()


# Visible Goofish / Xianyu asks for 符文战场T1 on 19 Aug 2026.
# Individual item IDs are not in the search-grid capture, so cheapest links
# point at the live search until the collector can scrape item pages.
XIANYU_VISIBLE_ASKS = [
    {"id": "goofish-5700", "price": 5700.0, "title": "符文战场 T1 2025 World Championship"},
    {"id": "goofish-5999", "price": 5999.0, "title": "限定 符文战场 T1 2025 World Championship"},
    {"id": "goofish-6000", "price": 6000.0, "title": "符文战场 T1 + 2025 World Championship Winner"},
    {"id": "goofish-6500-a", "price": 6500.0, "title": "符文战场 T1 2025 World Championship"},
    {"id": "goofish-6500-b", "price": 6500.0, "title": "符文战场 T1 礼盒 2025 World Championship"},
]


def ensure_xianyu_snapshot(session: Session | None = None) -> int:
    """Keep today's Xianyu asks aligned with the public Goofish search if live scrape is empty."""
    init_db()
    own = session is None
    session = session or SessionLocal()
    try:
        today = date.today()
        try:
            refresh_fx(session, today)
        except Exception:
            pass
        live_today = session.scalar(
            select(func.count())
            .select_from(RawListing)
            .where(
                RawListing.marketplace == "xianyu",
                RawListing.source == "live",
                RawListing.kept.is_(True),
                RawListing.observed_on == today,
            )
        ) or 0
        if live_today:
            return 0

        written = 0
        now = datetime.now()
        for item in XIANYU_VISIBLE_ASKS:
            row = session.scalar(
                select(RawListing).where(
                    RawListing.marketplace == "xianyu",
                    RawListing.external_id == item["id"],
                )
            )
            payload = dict(
                title=item["title"],
                price_native=item["price"],
                currency="CNY",
                price_usd=to_usd(session, item["price"], "CNY", today),
                listing_type="presale",
                sku=SKU_SIGNATURE,
                language=LANG_ZH,
                url=GOOFISH_T1_SEARCH,
                scraped_at=now,
                observed_on=today,
                source="snapshot",
                kept=True,
                reject_reason=None,
            )
            if row:
                for key, value in payload.items():
                    setattr(row, key, value)
            else:
                session.add(
                    RawListing(
                        marketplace="xianyu",
                        external_id=item["id"],
                        **payload,
                    )
                )
            written += 1
        session.commit()
        rebuild_aggregates(session)
        return written
    finally:
        if own:
            session.close()

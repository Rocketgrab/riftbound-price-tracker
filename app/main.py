from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, select

from app.aggregator import rebuild_aggregates
from app.classify import LANG_EN, LANG_KO, LANG_ZH, MSRP, SKU_PLAYER, SKU_SIGNATURE, is_wtb
from app.config import ROOT, settings
from app.db import CollectRun, DailyAggregate, RawListing, SessionLocal, init_db
from app.fx import aud_per_usd, convert_amount, to_aud, to_usd
from app.markets import HOME_MARKETS, MARKETPLACES, expand_marketplaces, search_catalog
from app.pipeline import reclassify_editions, run_collection, scrub_buyer_posts
from app.scheduler import next_run_iso, start_scheduler
from app.seed import ensure_ask_seed, ensure_xianyu_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

FRONTEND = ROOT / "frontend"

app = FastAPI(title="Riftbound T1 Price Tracker", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    inserted = ensure_ask_seed()
    if inserted:
        log.info("Seeded %s seller-ask listings so the chart is usable before live scrapes", inserted)
    dropped = scrub_buyer_posts()
    if dropped:
        log.info("Dropped %s want-to-buy posts that were stored as asks", dropped)
    relabeled = reclassify_editions()
    if relabeled:
        log.info("Relabeled %s listings to product edition language", relabeled)
    snap = ensure_xianyu_snapshot()
    if snap:
        log.info("Applied %s Xianyu / Goofish snapshot asks", snap)
    session = SessionLocal()
    try:
        rebuild_aggregates(session)
    finally:
        session.close()
    start_scheduler()
    if settings.collect_on_startup:
        run_collection()


def _session():
    return SessionLocal()


@app.get("/api/health")
def health():
    return {"ok": True, "phase": "presale", "shipped": False}


@app.get("/api/series")
def series(
    sku: str = Query(default=SKU_SIGNATURE),
    days: int = Query(default=60, ge=7, le=180),
    marketplaces: str = Query(default="ALL"),
):
    if sku not in {SKU_SIGNATURE, SKU_PLAYER}:
        raise HTTPException(400, "sku must be signature or player_bundle")
    session = _session()
    try:
        end = date.today()
        start = end - timedelta(days=days - 1)
        marketplace = marketplaces if marketplaces != "all" else "ALL"
        marketplace = "ALL" if marketplaces.upper() == "ALL" else marketplaces
        selected = [m.strip() for m in marketplace.split(",") if m.strip()]
        if selected == ["ALL"]:
            mp_filter = ["ALL"]
        else:
            mp_filter = expand_marketplaces(selected)

        rows = session.scalars(
            select(DailyAggregate)
            .where(
                DailyAggregate.sku == sku,
                DailyAggregate.date >= start,
                DailyAggregate.date <= end,
                DailyAggregate.marketplace.in_(mp_filter if mp_filter != ["ALL"] else ["ALL"]),
            )
            .order_by(DailyAggregate.date)
        ).all()

        # If a subset of marketplaces is requested, sum/recompute from listings.
        if mp_filter != ["ALL"]:
            payload = _series_from_listings(session, sku, start, end, mp_filter)
        else:
            payload = _series_from_aggregates(rows, start, end)

        payload["sku"] = sku
        payload["phase"] = "presale"
        payload["note"] = (
            "Seller asks in AUD. Buyer bids / want-to-buy posts (삽니다, 구매, WTB) are excluded. "
            "These products have not shipped yet."
        )
        payload = _apply_aud(session, payload, sku, end)
        cheapest = _cheapest_by_language(session, sku, mp_filter)
        payload["cheapest"] = {
            lang: _listing_payload(session, row, end) if row else None
            for lang, row in cheapest.items()
        }
        return payload
    finally:
        session.close()


def _series_from_aggregates(rows, start: date, end: date) -> dict:
    by_lang = {LANG_EN: {}, LANG_KO: {}, LANG_ZH: {}}
    for row in rows:
        by_lang.setdefault(row.language, {})[row.date.isoformat()] = {
            "median": row.median_usd if row.sample_count else None,
            "high": row.high_usd if row.sample_count else None,
            "low": row.low_usd if row.sample_count else None,
            "volume": row.volume,
            "sold_volume": row.sold_volume or 0,
            "sample_count": row.sample_count,
        }
    return _fill_days(by_lang, start, end)


def _series_from_listings(session, sku: str, start: date, end: date, marketplaces: list[str]) -> dict:
    from collections import defaultdict

    from app.stats import iqr_keep, median

    rows = session.scalars(
        select(RawListing).where(
            RawListing.kept.is_(True),
            RawListing.sku == sku,
            RawListing.listing_type.in_(("active", "presale", "sold")),
            RawListing.observed_on >= start,
            RawListing.observed_on <= end,
            RawListing.marketplace.in_(marketplaces),
            RawListing.language.in_([LANG_EN, LANG_KO, LANG_ZH]),
        )
    ).all()
    ask_buckets: dict[tuple, list[float]] = defaultdict(list)
    sold_buckets: dict[tuple, int] = defaultdict(int)
    for row in rows:
        key = (row.observed_on, row.language)
        if row.listing_type == "sold":
            sold_buckets[key] += 1
        else:
            ask_buckets[key].append(row.price_usd)
    by_lang = {LANG_EN: {}, LANG_KO: {}, LANG_ZH: {}}
    keys = set(ask_buckets) | set(sold_buckets)
    for day, language in keys:
        prices = ask_buckets.get((day, language)) or []
        clean = iqr_keep(prices) if prices else []
        by_lang[language][day.isoformat()] = {
            "median": round(median(clean), 2) if clean else None,
            "high": round(max(clean), 2) if clean else None,
            "low": round(min(clean), 2) if clean else None,
            "volume": len(prices),
            "sold_volume": sold_buckets.get((day, language), 0),
            "sample_count": len(clean),
        }
    return _fill_days(by_lang, start, end)


def _fill_days(by_lang: dict, start: date, end: date) -> dict:
    dates: list[str] = []
    cursor = start
    while cursor <= end:
        dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    languages = {}
    for lang in (LANG_EN, LANG_KO, LANG_ZH):
        languages[lang] = {
            "median": [by_lang.get(lang, {}).get(d, {}).get("median") for d in dates],
            "high": [by_lang.get(lang, {}).get(d, {}).get("high") for d in dates],
            "low": [by_lang.get(lang, {}).get(d, {}).get("low") for d in dates],
            "volume": [by_lang.get(lang, {}).get(d, {}).get("volume") or 0 for d in dates],
            "sold_volume": [by_lang.get(lang, {}).get(d, {}).get("sold_volume") or 0 for d in dates],
        }
    return {"dates": dates, "languages": languages}


def _apply_aud(session, payload: dict, sku: str, day: date) -> dict:
    factor = aud_per_usd(session, day)
    for lang in payload["languages"].values():
        for key in ("median", "high", "low"):
            lang[key] = [convert_amount(v, factor) for v in lang[key]]
    payload["currency"] = "AUD"
    payload["fx_aud_per_usd"] = factor
    payload["msrp"] = {}
    for lang, (amount, currency) in MSRP[sku].items():
        usd = to_usd(session, amount, currency, day)
        payload["msrp"][lang] = {
            "native": amount,
            "currency": currency,
            "aud": to_aud(session, usd, day),
        }
    payload["msrp_usd"] = payload["msrp"]
    return payload


def _listing_payload(session, row: RawListing, day: date) -> dict:
    return {
        "marketplace": row.marketplace,
        "title": row.title,
        "price_native": row.price_native,
        "currency": row.currency,
        "price_usd": row.price_usd,
        "price_aud": to_aud(session, row.price_usd, day),
        "listing_type": row.listing_type,
        "language": row.language,
        "url": row.url,
        "source": row.source,
        "observed_on": row.observed_on.isoformat() if row.observed_on else None,
    }


@app.get("/api/listings")
def listings(
    day: date = Query(...),
    sku: str = Query(default=SKU_SIGNATURE),
    language: str | None = None,
    marketplaces: str = Query(default="ALL"),
    limit: int = Query(default=40, ge=1, le=200),
):
    session = _session()
    try:
        stmt = select(RawListing).where(
            RawListing.kept.is_(True),
            RawListing.sku == sku,
            RawListing.observed_on == day,
            RawListing.listing_type.in_(("active", "presale", "sold")),
        )
        if language:
            stmt = stmt.where(RawListing.language == language)
        if marketplaces.upper() != "ALL":
            selected = expand_marketplaces(
                [m.strip() for m in marketplaces.split(",") if m.strip()]
            )
            stmt = stmt.where(RawListing.marketplace.in_(selected))
        rows = session.scalars(stmt.order_by(desc(RawListing.price_usd)).limit(limit)).all()
        return [_listing_payload(session, row, day) for row in rows]
    finally:
        session.close()


@app.get("/api/markets")
def markets(sku: str = Query(default=SKU_SIGNATURE)):
    if sku not in {SKU_SIGNATURE, SKU_PLAYER}:
        raise HTTPException(400, "sku must be signature or player_bundle")
    session = _session()
    try:
        day = date.today()
        cards = []
        for market in MARKETPLACES:
            cheapest_row = _cheapest_for(
                session, sku, market["key"], currency=market.get("currency")
            )
            if cheapest_row is None and market["id"] != market["key"]:
                cheapest_row = _cheapest_for(
                    session, sku, market["id"], currency=market.get("currency")
                )
            cards.append(
                {
                    "key": market["key"],
                    "label": market["label"],
                    "search_url": market["search_url"],
                    "sort": market["sort"],
                    "cheapest": _listing_payload(session, cheapest_row, day) if cheapest_row else None,
                }
            )
        return {
            "currency": "AUD",
            "updated_at": date.today().isoformat(),
            "refresh": "hourly",
            "next_run": next_run_iso(),
            "markets": cards,
            "searches": search_catalog(sku),
        }
    finally:
        session.close()


def _cheapest_by_language(session, sku: str, mp_filter: list[str]) -> dict:
    out = {}
    for lang in (LANG_EN, LANG_KO, LANG_ZH):
        if mp_filter == ["ALL"]:
            row = _cheapest_row(session, sku, language=lang, marketplaces=list(HOME_MARKETS[lang]))
            if row is None:
                row = _cheapest_row(session, sku, language=lang, marketplaces=None)
        else:
            row = _cheapest_row(session, sku, language=lang, marketplaces=mp_filter)
        out[lang] = row
    return out


def _cheapest_row(
    session,
    sku: str,
    *,
    language: str | None = None,
    marketplaces: list[str] | None = None,
    currency: str | None = None,
) -> RawListing | None:
    filters = [
        RawListing.kept.is_(True),
        RawListing.sku == sku,
        RawListing.listing_type.in_(("active", "presale")),
    ]
    if language:
        filters.append(RawListing.language == language)
    if marketplaces:
        filters.append(RawListing.marketplace.in_(marketplaces))
    if currency:
        filters.append(RawListing.currency == currency)
    rows = session.scalars(
        select(RawListing)
        .where(*filters, RawListing.observed_on >= date.today() - timedelta(days=2))
        .order_by(RawListing.price_usd.asc())
    ).all()
    if not rows:
        rows = session.scalars(select(RawListing).where(*filters).order_by(RawListing.price_usd.asc())).all()
    best = None
    best_key = None
    rank = {"live": 0, "snapshot": 1, "seed": 2}
    for row in rows:
        if is_wtb(row.title):
            continue
        key = (rank.get(row.source, 9), row.price_usd)
        if best is None or key < best_key:
            best = row
            best_key = key
    return best


def _cheapest_for(
    session, sku: str, marketplace: str, currency: str | None = None
) -> RawListing | None:
    return _cheapest_row(session, sku, marketplaces=[marketplace], currency=currency)


@app.get("/api/status")
def status():
    session = _session()
    try:
        runs = session.scalars(select(CollectRun).order_by(desc(CollectRun.started_at)).limit(20)).all()
        counts = {}
        for sku in (SKU_SIGNATURE, SKU_PLAYER):
            counts[sku] = session.scalar(
                select(func.count(RawListing.id)).where(
                    RawListing.kept.is_(True),
                    RawListing.sku == sku,
                    RawListing.listing_type.in_(("active", "presale")),
                )
            )
        return {
            "shipped": False,
            "phase": "presale",
            "currency": "AUD",
            "refresh": "hourly",
            "next_run": next_run_iso(),
            "kept_listings": counts,
            "runs": [
                {
                    "marketplace": run.marketplace,
                    "status": run.status,
                    "items_kept": run.items_kept,
                    "error": run.error,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                }
                for run in runs
            ],
        }
    finally:
        session.close()


@app.post("/api/collect")
def collect_now():
    reports = run_collection()
    return {"ok": True, "reports": reports}


@app.post("/api/rebuild")
def rebuild():
    session = _session()
    try:
        written = rebuild_aggregates(session)
        return {"ok": True, "rows": written}
    finally:
        session.close()


if FRONTEND.exists():
    @app.get("/styles.css")
    def styles():
        return FileResponse(FRONTEND / "styles.css")

    @app.get("/app.js")
    def app_js():
        return FileResponse(FRONTEND / "app.js")

    @app.get("/data/{name}")
    def static_data(name: str):
        path = (FRONTEND / "data" / name).resolve()
        if path.parent != (FRONTEND / "data").resolve() or not path.is_file():
            raise HTTPException(404, "not found")
        return FileResponse(path)

    app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator import rebuild_aggregates
from app.classify import ASK_TYPES, WTB, classify, is_wtb
from app.collectors import COLLECTORS
from app.collectors.base import CollectResult
from app.db import CollectRun, RawListing, SessionLocal, init_db
from app.fx import refresh_fx, to_usd
from app.stats import in_sku_band

log = logging.getLogger(__name__)


def run_collection(session: Session | None = None) -> list[dict]:
    init_db()
    own_session = session is None
    session = session or SessionLocal()
    reports: list[dict] = []
    try:
        today = datetime.now(timezone.utc).date()
        refresh_fx(session, today)
        for collector in COLLECTORS:
            started = datetime.now(timezone.utc)
            result = collector()
            report = _ingest(session, result, started)
            reports.append(report)
        rebuild_aggregates(session)
        return reports
    finally:
        if own_session:
            session.close()


def scrub_buyer_posts(session: Session | None = None) -> int:
    """Drop already-stored want-to-buy posts that slipped in as asks."""
    init_db()
    own = session is None
    session = session or SessionLocal()
    try:
        rows = session.scalars(select(RawListing).where(RawListing.kept.is_(True))).all()
        dropped = 0
        for row in rows:
            if not is_wtb(row.title):
                continue
            row.kept = False
            row.listing_type = WTB
            row.reject_reason = "bid"
            dropped += 1
        if dropped:
            session.commit()
            rebuild_aggregates(session)
        return dropped
    finally:
        if own:
            session.close()


def reclassify_editions(session: Session | None = None) -> int:
    """Re-run product filters on stored rows (T1 set vs singles, edition language)."""
    init_db()
    own = session is None
    session = session or SessionLocal()
    try:
        rows = session.scalars(select(RawListing)).all()
        changed = 0
        for row in rows:
            verdict = classify(row.title, row.marketplace, row.price_usd)
            listing_type = WTB if verdict.is_wtb else row.listing_type
            kept = False
            reason = verdict.reject_reason
            if verdict.is_wtb:
                listing_type = WTB
                reason = "bid"
            elif not verdict.kept:
                reason = verdict.reject_reason
            elif listing_type == "sold" and in_sku_band(verdict.sku, row.price_usd):
                kept = True
                reason = None
            elif listing_type in ASK_TYPES and in_sku_band(verdict.sku, row.price_usd):
                kept = True
                reason = None
            else:
                reason = reason or "not_ask"
            if (
                row.language != verdict.language
                or row.sku != verdict.sku
                or row.kept != kept
                or row.listing_type != listing_type
                or row.reject_reason != reason
            ):
                row.language = verdict.language
                row.sku = verdict.sku
                row.kept = kept
                row.listing_type = listing_type
                row.reject_reason = reason
                changed += 1
        if changed:
            session.commit()
            rebuild_aggregates(session)
        return changed
    finally:
        if own:
            session.close()


def _ingest(session: Session, result: CollectResult, started: datetime) -> dict:
    kept = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day = datetime.now(timezone.utc).date()
    for found in result.listings:
        observed_day = found.observed_at.date() if found.observed_at else day
        price_usd = to_usd(session, found.price_native, found.currency, observed_day)
        verdict = classify(found.title, found.marketplace, price_usd)
        listing_type = WTB if verdict.is_wtb else found.listing_type
        kept_flag = False
        reason = verdict.reject_reason
        if listing_type == WTB or verdict.is_wtb:
            reason = "bid"
        elif not verdict.kept:
            reason = verdict.reject_reason
        elif listing_type == "sold":
            if in_sku_band(verdict.sku, price_usd):
                kept_flag = True
                reason = None
            else:
                reason = "price_band"
        elif listing_type not in ASK_TYPES:
            reason = "not_ask"
        elif not in_sku_band(verdict.sku, price_usd):
            reason = "price_band"
        else:
            kept_flag = True
            reason = None

        existing = session.scalar(
            select(RawListing).where(
                RawListing.marketplace == found.marketplace,
                RawListing.external_id == found.external_id,
            )
        )
        payload = dict(
            title=found.title,
            price_native=found.price_native,
            currency=found.currency.upper(),
            price_usd=price_usd,
            listing_type=listing_type,
            sku=verdict.sku,
            language=verdict.language,
            url=found.url,
            scraped_at=now,
            observed_on=observed_day,
            source="live",
            kept=kept_flag,
            reject_reason=reason,
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            session.add(
                RawListing(
                    marketplace=found.marketplace,
                    external_id=found.external_id,
                    **payload,
                )
            )
        if kept_flag:
            kept += 1

    status = "ok" if result.error is None else ("partial" if result.listings else "error")
    session.add(
        CollectRun(
            started_at=started.replace(tzinfo=None),
            finished_at=now,
            marketplace=result.marketplace,
            status=status,
            items_kept=kept,
            error=result.error,
        )
    )
    session.commit()
    log.info(
        "%s: asks_kept=%s fetched=%s status=%s error=%s",
        result.marketplace,
        kept,
        len(result.listings),
        status,
        result.error,
    )
    return {
        "marketplace": result.marketplace,
        "fetched": len(result.listings),
        "kept": kept,
        "status": status,
        "error": result.error,
    }

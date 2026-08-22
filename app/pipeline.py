from __future__ import annotations

import logging
import threading
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
_collect_lock = threading.Lock()


class CollectBusy(RuntimeError):
    """Another collection is already running."""


def run_collection(session: Session | None = None, *, block: bool = True) -> list[dict]:
    init_db()
    if not _collect_lock.acquire(blocking=block):
        raise CollectBusy("collection already running")
    own_session = session is None
    session = session or SessionLocal()
    reports: list[dict] = []
    try:
        today = datetime.now(timezone.utc).date()
        try:
            refresh_fx(session, today)
        except Exception:
            log.exception("FX refresh failed; continuing with stored rates")
        for collector in COLLECTORS:
            started = datetime.now(timezone.utc)
            try:
                result = collector()
            except Exception as exc:  # noqa: BLE001
                log.exception("Collector crashed: %s", collector.__name__)
                name = collector.__name__.replace("collect_", "")
                result = CollectResult(name, listings=[], error=str(exc))
            try:
                report = _ingest(session, result, started)
            except Exception as exc:  # noqa: BLE001
                log.exception("Ingest crashed: %s", result.marketplace)
                session.rollback()
                report = {
                    "marketplace": result.marketplace,
                    "fetched": len(result.listings),
                    "kept": 0,
                    "status": "error",
                    "error": str(exc),
                }
            reports.append(report)
        try:
            rebuild_aggregates(session)
        except Exception:
            log.exception("Aggregate rebuild failed after collect")
        return reports
    finally:
        if own_session:
            session.close()
        _collect_lock.release()


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
        try:
            observed_day = found.observed_at.date() if found.observed_at else day
            if found.price_native is None or found.price_native <= 0:
                continue
            price_usd = to_usd(session, found.price_native, found.currency or "USD", observed_day)
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
                    RawListing.external_id == str(found.external_id)[:128],
                )
            )
            payload = dict(
                title=(found.title or "")[:2000],
                price_native=found.price_native,
                currency=(found.currency or "USD").upper()[:8],
                price_usd=price_usd,
                listing_type=listing_type,
                sku=verdict.sku,
                language=verdict.language,
                url=found.url or "",
                scraped_at=now,
                last_seen_on=day,
                source="live",
                kept=kept_flag,
                reject_reason=reason,
            )
            if existing:
                # Never move the original observed day; last_seen_on tracks the book.
                if listing_type == "sold" and found.observed_at is not None and not existing.observed_on:
                    payload["observed_on"] = observed_day
                for key, value in payload.items():
                    setattr(existing, key, value)
            else:
                session.add(
                    RawListing(
                        marketplace=found.marketplace,
                        external_id=str(found.external_id)[:128],
                        observed_on=observed_day,
                        **payload,
                    )
                )
            if kept_flag:
                kept += 1
        except Exception:
            log.exception(
                "Skipped listing %s/%s",
                found.marketplace,
                getattr(found, "external_id", "?"),
            )
            continue

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

from __future__ import annotations

import logging

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.pipeline import run_collection

log = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _job,
        IntervalTrigger(hours=1, start_date=datetime.now() + timedelta(hours=1)),
        id="hourly-collect",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("Collectors scheduled every hour")
    return scheduler


def next_run_iso() -> str | None:
    if not _scheduler:
        return None
    job = _scheduler.get_job("hourly-collect")
    if not job or not job.next_run_time:
        return None
    return job.next_run_time.isoformat()


def _job() -> None:
    log.info("Starting hourly collection")
    try:
        from app.seed import ensure_xianyu_snapshot

        run_collection()
        ensure_xianyu_snapshot()
    except Exception:
        log.exception("Hourly collection failed")

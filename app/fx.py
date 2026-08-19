from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import FxRate

log = logging.getLogger(__name__)

FALLBACK_USD_PER_UNIT = {
    "USD": 1.0,
    "KRW": 1 / 1390.0,
    "CNY": 1 / 7.20,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 1 / 148.0,
    "HKD": 1 / 7.80,
    "TWD": 1 / 32.0,
    "AUD": 0.65,
    "NZD": 0.58,
}


def _upsert_rate(session: Session, day: date, currency: str, usd_per_unit: float) -> None:
    row = session.scalar(
        select(FxRate).where(FxRate.date == day, FxRate.currency == currency)
    )
    if row:
        row.usd_per_unit = usd_per_unit
    else:
        session.add(FxRate(date=day, currency=currency, usd_per_unit=usd_per_unit))


def refresh_fx(session: Session, day: date | None = None) -> dict[str, float]:
    day = day or date.today()
    rates = {"USD": 1.0}
    try:
        url = f"{settings.fx_api_url.rstrip('/')}/{day.isoformat()}"
        with httpx.Client(timeout=20.0) as client:
            res = client.get(url, params={"base": "USD", "symbols": "KRW,CNY,EUR,GBP,JPY,HKD,TWD,AUD,NZD"})
            res.raise_for_status()
            payload = res.json()
        fx = payload.get("rates") or {}
        # Frankfurter returns units of quote per 1 USD.
        for currency, per_usd in fx.items():
            if per_usd:
                rates[currency] = 1.0 / float(per_usd)
        log.info("FX refresh %s: %s", day, {k: round(v, 6) for k, v in rates.items()})
    except Exception as exc:
        log.warning("FX API failed (%s); using last stored / fallback rates", exc)
        stored = session.scalars(select(FxRate).where(FxRate.date == day)).all()
        if stored:
            rates.update({row.currency: row.usd_per_unit for row in stored})
        else:
            rates.update(FALLBACK_USD_PER_UNIT)

    for currency, usd_per_unit in rates.items():
        _upsert_rate(session, day, currency, usd_per_unit)
    session.commit()
    return rates


def usd_per_unit(session: Session, currency: str, day: date) -> float:
    currency = currency.upper()
    if currency == "USD":
        return 1.0
    row = session.scalar(
        select(FxRate).where(FxRate.date == day, FxRate.currency == currency)
    )
    if row:
        return row.usd_per_unit
    # Walk backwards a few days, then fallback.
    for delta in range(1, 8):
        prev = session.scalar(
            select(FxRate).where(
                FxRate.date == day - timedelta(days=delta),
                FxRate.currency == currency,
            )
        )
        if prev:
            return prev.usd_per_unit
    return FALLBACK_USD_PER_UNIT.get(currency, 1.0)


def to_usd(session: Session, amount: float, currency: str, day: date) -> float:
    return round(amount * usd_per_unit(session, currency, day), 2)


def aud_per_usd(session: Session, day: date) -> float:
    per_aud = usd_per_unit(session, "AUD", day)
    if not per_aud:
        return round(1 / FALLBACK_USD_PER_UNIT["AUD"], 4)
    return round(1.0 / per_aud, 4)


def to_aud(session: Session, amount_usd: float, day: date) -> float:
    return round(amount_usd * aud_per_usd(session, day), 2)


def convert_amount(value: float | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(float(value) * factor, 2)

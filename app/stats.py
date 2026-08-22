from __future__ import annotations

import statistics

from app.config import settings
from app.classify import SKU_PLAYER, SKU_SIGNATURE


def iqr_keep(values: list[float]) -> list[float]:
    if len(values) < 8:
        return values
    ordered = sorted(values)
    q1 = statistics.quantiles(ordered, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(ordered, n=4, method="inclusive")[2]
    iqr = q3 - q1
    if iqr <= 0:
        return values
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    filtered = [v for v in values if lo <= v <= hi]
    return filtered or values


def in_sku_band(sku: str, price_usd: float) -> bool:
    if sku == SKU_SIGNATURE:
        return settings.signature_usd_min <= price_usd <= settings.signature_usd_max
    if sku == SKU_PLAYER:
        return settings.player_usd_min <= price_usd <= settings.player_usd_max
    return 20 <= price_usd <= 8000


def median(values: list[float]) -> float:
    return float(statistics.median(values))

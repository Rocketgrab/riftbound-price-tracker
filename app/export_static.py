from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import ROOT
from app.db import init_db
from app.main import listings, markets, series, status
from app.pipeline import reclassify_editions, scrub_buyer_posts
from app.seed import ensure_ask_seed, ensure_xianyu_snapshot

OUT = ROOT / "frontend" / "data"
SKUS = ("signature", "player_bundle")
DAYS = (14, 30, 60)
MPS = ("ALL", "ebay", "bunjang_kr", "bunjang_global", "karrot", "xianyu")


def export_snapshot() -> Path:
    init_db()
    ensure_ask_seed()
    scrub_buyer_posts()
    reclassify_editions()
    ensure_xianyu_snapshot()
    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "AUD",
        "refresh": "hourly",
        "series": {},
        "markets": {},
        "listings": {},
        "status": status(),
    }
    for sku in SKUS:
        snapshot["series"][sku] = {}
        snapshot["listings"][sku] = {}
        snapshot["markets"][sku] = markets(sku=sku)
        for days in DAYS:
            snapshot["series"][sku][str(days)] = {}
            for mp in MPS:
                snapshot["series"][sku][str(days)][mp] = series(
                    sku=sku, days=days, marketplaces=mp
                )
        end = date.today()
        cursor = end - timedelta(days=59)
        while cursor <= end:
            snapshot["listings"][sku][cursor.isoformat()] = listings(
                day=cursor, sku=sku, marketplaces="ALL", limit=200
            )
            cursor += timedelta(days=1)
    path = OUT / "snapshot.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    written = export_snapshot()
    print(written)

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.http_util import get_with_retry, json_client, sleep_jitter

log = logging.getLogger(__name__)

QUERIES = [
    "리프트바운드 T1 시그니처",
    "리프트바운드 T1 영문",
    "리프트바운드 T1 중문",
    "리프트바운드 T1 한글",
    "Riftbound T1 Signature",
]

ENDPOINTS = [
    "https://api.bunjang.co.kr/api/1/find_v2.json",
    "https://m.bunjang.co.kr/api/1/find_v2.json",
]


def collect_bunjang_kr() -> CollectResult:
    listings: list[FoundListing] = []
    seen_ids: list[str] = []
    last_error: str | None = None
    try:
        with json_client() as client:
            for query in QUERIES:
                for page in range(4):
                    page_rows, ids, err = _search(client, query, page)
                    last_error = err or last_error
                    listings.extend(page_rows)
                    seen_ids.extend(ids)
                    sleep_jitter(1.2, 2.8)
                    if len(ids) < 10:
                        break
        listings = _dedupe(listings)
        if not listings and last_error:
            return CollectResult("bunjang_kr", error=last_error, seen_ids=seen_ids)
        return CollectResult(
            "bunjang_kr",
            listings=listings,
            error=last_error,
            seen_ids=seen_ids,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Bunjang KR collector failed")
        return CollectResult("bunjang_kr", listings=_dedupe(listings), error=str(exc), seen_ids=seen_ids)


def _search(client, query: str, page: int) -> tuple[list[FoundListing], list[str], str | None]:
    params = {
        "q": query,
        "order": "date",
        "page": page,
        "n": 50,
        "stat_device": "web",
        "req_ref": "search",
        "version": "4",
    }
    last_err = None
    for url in ENDPOINTS:
        try:
            res = get_with_retry(
                client,
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "Referer": f"https://m.bunjang.co.kr/search/products?q={quote(query)}",
                },
            )
            payload = res.json()
            rows, ids = _parse(payload)
            return rows, ids, None
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue
    return [], [], last_err


def _parse(payload: dict) -> tuple[list[FoundListing], list[str]]:
    rows = payload.get("list") or payload.get("data") or payload.get("products") or []
    out: list[FoundListing] = []
    ids: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("pid") or item.get("id") or item.get("productId") or "")
        title = str(item.get("name") or item.get("title") or item.get("subject") or "")
        price = item.get("price") or item.get("price_origin") or 0
        try:
            amount = float(str(price).replace(",", ""))
        except ValueError:
            continue
        if not pid or not title or amount <= 0:
            continue
        ids.append(pid)
        status = str(item.get("status") or item.get("saleStatus") or item.get("sale_status") or "")
        # 0 = on sale, 1 = reserved. 3 / SOLD = completed. Buy posts still have status 0.
        if status.upper() in {"SOLD", "COMPLETE", "CLOSED", "3"}:
            listing_type = "sold"
        else:
            listing_type = "active"
        if is_wtb(title):
            listing_type = "wtb"
        ext_id = f"sold-{pid}" if listing_type == "sold" else pid
        observed_at = datetime.now(timezone.utc)
        if listing_type == "sold":
            observed_at = _parse_bunjang_time(item) or observed_at
        out.append(
            FoundListing(
                marketplace="bunjang_kr",
                external_id=ext_id,
                title=title,
                price_native=amount,
                currency="KRW",
                listing_type=listing_type,
                url=f"https://m.bunjang.co.kr/products/{pid}",
                observed_at=observed_at,
            )
        )
    return out, ids


def _parse_bunjang_time(item: dict) -> datetime | None:
    raw = (
        item.get("update_time")
        or item.get("updateTime")
        or item.get("sold_time")
        or item.get("datetime")
        or item.get("upd_dt")
    )
    if raw is None:
        return None
    try:
        ts = float(raw)
        if ts > 10_000_000_000:
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _dedupe(rows: list[FoundListing]) -> list[FoundListing]:
    seen: set[str] = set()
    unique: list[FoundListing] = []
    for row in rows:
        if row.external_id in seen:
            continue
        seen.add(row.external_id)
        unique.append(row)
    return unique

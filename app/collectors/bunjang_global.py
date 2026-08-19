from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.http_util import get_with_retry, json_client, sleep_jitter

log = logging.getLogger(__name__)

QUERIES = [
    "Riftbound T1 Signature",
    "Riftbound T1 bundle Korean",
    "Riftbound T1 Chinese",
]


def collect_bunjang_global() -> CollectResult:
    listings: list[FoundListing] = []
    try:
        with json_client() as client:
            for query in QUERIES:
                listings.extend(_search(client, query))
                sleep_jitter()
        return CollectResult("bunjang_global", listings=_dedupe(listings))
    except Exception as exc:  # noqa: BLE001
        log.exception("Bunjang Global collector failed")
        return CollectResult("bunjang_global", listings=_dedupe(listings), error=str(exc))


def _search(client, query: str) -> list[FoundListing]:
    # Global storefront search; JSON first, HTML fallback.
    json_urls = [
        f"https://globalbunjang.com/api/search?keyword={query}",
        f"https://www.globalbunjang.com/api/search?q={query}",
    ]
    for url in json_urls:
        try:
            res = get_with_retry(client, url, headers={"Accept": "application/json"})
            payload = res.json()
            parsed = _parse_json(payload)
            if parsed:
                return parsed
        except Exception:
            continue

    html_url = f"https://globalbunjang.com/search?keyword={query}"
    res = get_with_retry(client, html_url, headers={"Accept": "text/html"})
    return _parse_html(res.text)


def _parse_json(payload) -> list[FoundListing]:
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("list") or payload.get("items") or payload.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("list") or rows.get("items") or []
    out: list[FoundListing] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or item.get("pid") or "")
        title = str(item.get("title") or item.get("name") or "")
        price = item.get("price") or item.get("salePrice") or 0
        currency = str(item.get("currency") or "USD")
        try:
            amount = float(price)
        except (TypeError, ValueError):
            continue
        if not pid or not title or amount <= 0:
            continue
        listing_type = "wtb" if is_wtb(title) else "presale"
        out.append(
            FoundListing(
                marketplace="bunjang_global",
                external_id=pid,
                title=title,
                price_native=amount,
                currency=currency,
                listing_type=listing_type,
                url=item.get("url") or f"https://globalbunjang.com/products/{pid}",
            )
        )
    return out


def _parse_html(html: str) -> list[FoundListing]:
    soup = BeautifulSoup(html, "lxml")
    out: list[FoundListing] = []
    for card in soup.select("a[href*='/product'], a[href*='/products']"):
        title = card.get_text(" ", strip=True)
        if "riftbound" not in title.lower() and "t1" not in title.lower():
            continue
        href = card.get("href") or ""
        pid = re.search(r"/products?/(\d+)", href)
        price_text = re.search(r"([\d,.]+)\s*(USD|KRW|CNY|₩|\$)", title)
        if not pid or not price_text:
            continue
        amount = float(price_text.group(1).replace(",", ""))
        currency = "USD"
        token = price_text.group(2)
        if token in {"KRW", "₩"}:
            currency = "KRW"
        elif token == "CNY":
            currency = "CNY"
        listing_type = "wtb" if is_wtb(title) else "presale"
        out.append(
            FoundListing(
                marketplace="bunjang_global",
                external_id=pid.group(1),
                title=title[:240],
                price_native=amount,
                currency=currency,
                listing_type=listing_type,
                url=href if href.startswith("http") else f"https://globalbunjang.com{href}",
            )
        )
    return out


def _dedupe(rows: list[FoundListing]) -> list[FoundListing]:
    seen: set[str] = set()
    unique: list[FoundListing] = []
    for row in rows:
        if row.external_id in seen:
            continue
        seen.add(row.external_id)
        unique.append(row)
    return unique

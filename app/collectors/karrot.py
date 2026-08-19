from __future__ import annotations

import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.http_util import get_with_retry, json_client, sleep_jitter

log = logging.getLogger(__name__)

QUERIES = [
    "리프트바운드 T1",
    "리프트바운드 시그니처",
    "Riftbound T1",
]


def collect_karrot() -> CollectResult:
    listings: list[FoundListing] = []
    try:
        with json_client() as client:
            for query in QUERIES:
                listings.extend(_search(client, query))
                sleep_jitter()
        return CollectResult("karrot", listings=_dedupe(listings))
    except Exception as exc:  # noqa: BLE001
        log.exception("Karrot collector failed")
        return CollectResult("karrot", listings=_dedupe(listings), error=str(exc))


def _search(client, query: str) -> list[FoundListing]:
    urls = [
        f"https://www.daangn.com/search/{quote(query)}",
        f"https://www.daangn.com/kr/buy-sell/?in=kr&search={quote(query)}",
    ]
    html = ""
    for url in urls:
        try:
            res = get_with_retry(client, url, headers={"Accept": "text/html"})
            html = res.text
            parsed = _parse(html)
            if parsed:
                return parsed
        except Exception as exc:
            log.info("Karrot URL failed %s: %s", url, exc)
            continue
    return _parse(html)


def _parse(html: str) -> list[FoundListing]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[FoundListing] = []
    cards = soup.select("article, a[href*='/articles/'], a[href*='/kr/buy-sell/']")
    for card in cards:
        title_el = card.select_one("span, h2, h1, p") or card
        title = title_el.get_text(" ", strip=True)
        if not title or len(title) < 8:
            continue
        blob = card.get_text(" ", strip=True)
        if not re.search(r"리프트바운드|riftbound|t1", blob, re.I):
            continue
        price_match = re.search(r"([\d,]+)\s*원", blob)
        if not price_match:
            continue
        href = card.get("href") or (card.select_one("a") or {}).get("href") or ""
        listing_id = None
        id_match = re.search(r"/articles/(\d+)|buy-sell/([a-z0-9-]+)", href)
        if id_match:
            listing_id = id_match.group(1) or id_match.group(2)
        listing_id = listing_id or re.sub(r"\s+", "-", title)[:48]
        listing_type = "presale" if re.search(r"예약|프리오더|pre", title, re.I) else "active"
        if is_wtb(title) or is_wtb(blob):
            listing_type = "wtb"
        out.append(
            FoundListing(
                marketplace="karrot",
                external_id=str(listing_id),
                title=title[:240],
                price_native=float(price_match.group(1).replace(",", "")),
                currency="KRW",
                listing_type=listing_type,
                url=href if str(href).startswith("http") else f"https://www.daangn.com{href}",
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

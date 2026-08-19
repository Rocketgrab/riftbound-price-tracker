from __future__ import annotations

import logging
import re

from urllib.parse import quote

from bs4 import BeautifulSoup

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.config import settings
from app.http_util import get_with_retry, json_client, sleep_jitter

log = logging.getLogger(__name__)

# 符文战场 is the official Simplified Chinese name.
QUERIES = [
    "符文战场T1",
    "符文战场 T1 签名",
    "符文战场 T1",
    "Riftbound T1",
]


def collect_xianyu() -> CollectResult:
    listings: list[FoundListing] = []
    try:
        headers = {"Accept": "text/html,application/json"}
        if settings.xianyu_cookie:
            headers["Cookie"] = settings.xianyu_cookie
        with json_client() as client:
            for query in QUERIES:
                listings.extend(_search(client, query, headers))
                sleep_jitter(2.0, 4.5)
        error = None if listings else "Xianyu blocked or returned no public results"
        return CollectResult("xianyu", listings=_dedupe(listings), error=error)
    except Exception as exc:  # noqa: BLE001
        log.exception("Xianyu collector failed")
        return CollectResult("xianyu", listings=_dedupe(listings), error=str(exc))


def _search(client, query: str, headers: dict[str, str]) -> list[FoundListing]:
    encoded = quote(query)
    urls = [
        f"https://www.goofish.com/search?q={encoded}",
        f"https://s.2.taobao.com/list/list.htm?q={encoded}",
    ]
    for url in urls:
        try:
            res = get_with_retry(client, url, headers=headers)
            parsed = _parse(res.text)
            if parsed:
                return parsed
        except Exception as exc:
            log.info("Xianyu URL failed %s: %s", url, exc)
            continue
    return []


def _parse(html: str) -> list[FoundListing]:
    soup = BeautifulSoup(html, "lxml")
    out: list[FoundListing] = []
    for card in soup.select("a[href*='item'], a[href*='idle']"):
        title = card.get_text(" ", strip=True)
        if not re.search(r"符文|riftbound|t1", title, re.I):
            continue
        price_match = re.search(r"¥\s*([\d.]+)|([\d.]+)\s*元", title)
        if not price_match:
            continue
        href = card.get("href") or ""
        listing_id = re.search(r"id=(\d+)", href)
        ext = listing_id.group(1) if listing_id else title[:40]
        amount = float((price_match.group(1) or price_match.group(2)).replace(",", ""))
        listing_type = "wtb" if is_wtb(title) else "presale"
        out.append(
            FoundListing(
                marketplace="xianyu",
                external_id=str(ext),
                title=title[:240],
                price_native=amount,
                currency="CNY",
                listing_type=listing_type,
                url=href if href.startswith("http") else f"https://www.goofish.com{href}",
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

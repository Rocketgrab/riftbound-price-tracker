from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.http_util import get_with_retry, json_client, sleep_jitter
from app.markets import CN_PRIMARY, dewu_search, jd_search, taobao_search, zhuanzhuan_search

log = logging.getLogger(__name__)

TITLE_RE = re.compile(r"符文战场|符文戰場|riftbound|\bt1\b", re.I)
PRICE_RE = re.compile(r"(?:¥|￥)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*元")


def collect_taobao() -> CollectResult:
    return _collect("taobao", [taobao_search(CN_PRIMARY)])


def collect_dewu() -> CollectResult:
    return _collect("dewu", [dewu_search(CN_PRIMARY)])


def collect_zhuanzhuan() -> CollectResult:
    return _collect("zhuanzhuan", [zhuanzhuan_search(CN_PRIMARY)])


def collect_jd() -> CollectResult:
    return _collect("jd", [jd_search(CN_PRIMARY)])


def _collect(marketplace: str, urls: list[str]) -> CollectResult:
    listings: list[FoundListing] = []
    last_error: str | None = None
    try:
        with json_client() as client:
            for url in urls:
                try:
                    res = get_with_retry(client, url, attempts=2)
                    listings.extend(_parse(res.text, marketplace, url))
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    log.info("%s URL failed %s: %s", marketplace, url, exc)
                sleep_jitter(0.4, 1.0)
        listings = _dedupe(listings)
        error = None if listings else (last_error or f"{marketplace} blocked or returned no public results")
        return CollectResult(marketplace, listings=listings, error=error)
    except Exception as exc:  # noqa: BLE001
        log.exception("%s collector failed", marketplace)
        return CollectResult(marketplace, listings=_dedupe(listings), error=str(exc))


def _parse(html: str, marketplace: str, page_url: str) -> list[FoundListing]:
    soup = BeautifulSoup(html or "", "lxml")
    out: list[FoundListing] = []
    for card in soup.select("a[href]"):
        title = card.get_text(" ", strip=True)
        if len(title) < 8 or not TITLE_RE.search(title):
            continue
        price_match = PRICE_RE.search(title) or PRICE_RE.search(card.parent.get_text(" ", strip=True) if card.parent else "")
        if not price_match:
            continue
        amount = float((price_match.group(1) or price_match.group(2)).replace(",", ""))
        href = card.get("href") or page_url
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = page_url.split("/", 3)[0] + "//" + page_url.split("/", 3)[2] + href
        listing_id = re.search(r"id=(\d+)|item/(\d+)|product/(\d+)", href)
        ext = next((g for g in listing_id.groups() if g), None) if listing_id else title[:40]
        out.append(
            FoundListing(
                marketplace=marketplace,
                external_id=str(ext),
                title=title[:240],
                price_native=amount,
                currency="CNY",
                listing_type="wtb" if is_wtb(title) else "presale",
                url=href if href.startswith("http") else page_url,
            )
        )
    if not out:
        out.extend(_from_embedded_json(html, marketplace, page_url))
    return out


def _from_embedded_json(html: str, marketplace: str, page_url: str) -> list[FoundListing]:
    out: list[FoundListing] = []
    for match in re.finditer(
        r'"title"\s*:\s*"([^"]{6,160})".{0,500}?"price"\s*:\s*"?(\d+(?:\.\d+)?)',
        html,
        re.S,
    ):
        title = match.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
        if not TITLE_RE.search(title):
            continue
        out.append(
            FoundListing(
                marketplace=marketplace,
                external_id=title[:40],
                title=title[:240],
                price_native=float(match.group(2)),
                currency="CNY",
                listing_type="wtb" if is_wtb(title) else "presale",
                url=page_url,
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

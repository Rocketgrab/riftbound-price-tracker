from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.classify import is_wtb
from app.collectors.base import CollectResult, FoundListing
from app.config import settings
from app.http_util import get_with_retry, json_client, sleep_jitter

log = logging.getLogger(__name__)

QUERIES = [
    "Riftbound T1 Signature",
    "Riftbound T1 Signature English",
    "Riftbound T1 Signature Korean",
    "Riftbound T1 Signature Chinese",
    "Riftbound T1 Worlds Champion",
]

ASK_HOSTS = [
    "https://www.ebay.com.au/sch/i.html",
    "https://www.ebay.com/sch/i.html",
]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def collect_ebay_au() -> CollectResult:
    return _collect_ebay("ebay_au", "https://www.ebay.com.au/sch/i.html", "AUD", "EBAY-AU")


def collect_ebay_us() -> CollectResult:
    return _collect_ebay("ebay_us", "https://www.ebay.com/sch/i.html", "USD", "EBAY-US")


def collect_ebay() -> CollectResult:
    """Back-compat wrapper used by older scripts."""
    au = collect_ebay_au()
    us = collect_ebay_us()
    return CollectResult(
        "ebay",
        listings=_dedupe(au.listings + us.listings),
        error=au.error or us.error,
        seen_ids=(au.seen_ids or []) + (us.seen_ids or []),
    )


def _collect_ebay(marketplace: str, host: str, currency: str, global_id: str) -> CollectResult:
    listings: list[FoundListing] = []
    try:
        if settings.ebay_app_id:
            listings.extend(_via_finding_api(marketplace, currency, global_id, sold=False))
            listings.extend(_via_finding_api(marketplace, currency, global_id, sold=True))
        else:
            listings.extend(_via_html(marketplace, host, currency, sold=False))
            listings.extend(_via_html(marketplace, host, currency, sold=True))
        listings = [row for row in listings if row.listing_type in {"active", "wtb", "sold"}]
        error = None if listings else f"{marketplace} returned no public results"
        return CollectResult(
            marketplace,
            listings=_dedupe(listings),
            error=error,
            seen_ids=[r.external_id for r in listings],
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("%s collector failed", marketplace)
        return CollectResult(marketplace, listings=_dedupe(listings), error=str(exc))


def _via_finding_api(
    marketplace: str, default_ccy: str, global_id: str, sold: bool = False
) -> list[FoundListing]:
    out: list[FoundListing] = []
    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    operation = "findCompletedItems" if sold else "findItemsAdvanced"
    response_key = "findCompletedItemsResponse" if sold else "findItemsAdvancedResponse"
    for query in QUERIES:
        params = {
            "OPERATION-NAME": operation,
            "SERVICE-VERSION": "1.13.0",
            "SECURITY-APPNAME": settings.ebay_app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "true",
            "GLOBAL-ID": global_id,
            "keywords": query,
            "itemFilter(0).name": "ListingType",
            "itemFilter(0).value": "FixedPrice",
            "paginationInput.entriesPerPage": "50",
        }
        if sold:
            params["itemFilter(1).name"] = "SoldItemsOnly"
            params["itemFilter(1).value"] = "true"
        with json_client() as client:
            res = get_with_retry(client, url, params=params)
        payload = res.json()
        search = (payload.get(response_key) or [{}])[0]
        items = search.get("searchResult", [{}])[0].get("item") or []
        for item in items:
            try:
                selling = (item.get("sellingStatus") or [{}])[0]
                price = (selling.get("currentPrice") or [{}])[0]
                listing_id = str((item.get("itemId") or ["?"])[0])
                title = (item.get("title") or [""])[0]
                currency = price.get("@currencyId") or default_ccy
                amount = float(price.get("__value__", 0))
                listing_url = (item.get("viewItemURL") or [""])[0]
                if amount <= 0:
                    continue
                listing_type = "wtb" if is_wtb(title) else ("sold" if sold else "active")
                end_time = ((item.get("listingInfo") or [{}])[0].get("endTime") or [None])[0]
                out.append(
                    FoundListing(
                        marketplace=marketplace,
                        external_id=f"sold-{listing_id}" if listing_type == "sold" else listing_id,
                        title=title,
                        price_native=amount,
                        currency=currency,
                        listing_type=listing_type,
                        url=listing_url,
                        observed_at=_parse_iso_datetime(end_time) if sold else None,
                    )
                )
            except (TypeError, ValueError, KeyError):
                continue
        sleep_jitter(1.2, 2.5)
    return out


def _via_html(marketplace: str, host: str, default_ccy: str, sold: bool = False) -> list[FoundListing]:
    out: list[FoundListing] = []
    extra = "LH_Complete=1&LH_Sold=1&_sop=13&_ipg=60" if sold else "LH_BIN=1&_sop=15&_ipg=60"
    headers = {
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Referer": host.replace("/sch/i.html", "/"),
    }
    kind = "sold" if sold else "ask"
    hosts = [host]
    if sold and "ebay.com.au" in host:
        hosts.append("https://www.ebay.com/sch/i.html")
    with json_client() as client:
        for search_host in hosts:
            for query in QUERIES:
                url = f"{search_host}?_nkw={quote_plus(query)}&{extra}"
                try:
                    res = get_with_retry(client, url, headers=headers, attempts=2)
                except Exception as exc:
                    log.info("eBay HTML %s search failed %s %s: %s", kind, search_host, query, exc)
                    continue
                soup = BeautifulSoup(res.text, "lxml")
                cards = soup.select("li.s-card, .s-item, li[id^='item']")
                page_rows = []
                for item in cards:
                    page_rows.extend(_parse_card(item, marketplace, default_ccy, sold=sold))
                if not page_rows:
                    page_rows = _from_embedded_json(res.text, marketplace, default_ccy, sold=sold)
                out.extend(page_rows)
                sleep_jitter(1.0, 2.2)
    return out


def _parse_card(item, marketplace: str, default_ccy: str, sold: bool = False) -> list[FoundListing]:
    title_el = item.select_one(".s-item__title, .s-card__title, [role='heading']")
    price_el = item.select_one(".s-item__price, .s-card__price, .su-styled-text.positive")
    link_el = item.select_one("a.s-item__link, a.s-card__link, a[href*='/itm/']")
    if not title_el or not price_el or not link_el:
        return []
    title = title_el.get_text(" ", strip=True)
    title = re.sub(r"\s*Opens in a new window or tab\s*", " ", title, flags=re.I).strip()
    if title.lower().startswith("shop on ebay"):
        return []
    blob = item.get_text(" ", strip=True)
    amount, currency = _parse_price(price_el.get_text(" ", strip=True), default_ccy)
    if amount is None:
        return []
    href = link_el.get("href") or ""
    listing_id = _id_from_url(href) or title[:40]
    sold_at = _parse_sold_date(blob)
    qty_match = re.search(r"\b(\d+)\s+sold\b", blob, re.I)
    qty = int(qty_match.group(1)) if qty_match else 0
    if is_wtb(title):
        listing_type = "wtb"
    elif sold or sold_at:
        listing_type = "sold"
    else:
        listing_type = "active"
    rows = [
        FoundListing(
            marketplace=marketplace,
            external_id=f"sold-{listing_id}" if listing_type == "sold" else listing_id,
            title=title,
            price_native=amount,
            currency=currency,
            listing_type=listing_type,
            url=href,
            observed_at=sold_at,
        )
    ]
    # Sold-item search redirects to login. Unit-sold counts on live BIN cards
    # are the public completed-sale signal we can still read.
    if listing_type == "active" and qty >= 1:
        rows.append(
            FoundListing(
                marketplace=marketplace,
                external_id=f"soldqty-{listing_id}",
                title=title,
                price_native=amount,
                currency=currency,
                listing_type="sold",
                url=href,
                observed_at=datetime.utcnow(),
            )
        )
    return rows


def _from_embedded_json(
    html: str, marketplace: str, default_ccy: str, sold: bool = False
) -> list[FoundListing]:
    out: list[FoundListing] = []
    for match in re.finditer(r'"itemId"\s*:\s*"(\d+)".{0,400}?"title"\s*:\s*"([^"]+)"', html):
        listing_id, title = match.group(1), match.group(2)
        title = title.encode("utf-8").decode("unicode_escape", errors="ignore")
        price_match = re.search(
            rf"itemId\"\s*:\s*\"{listing_id}\".{{0,800}}?\"price\"\s*:\s*(\d+(?:\.\d+)?)",
            html,
        )
        if not price_match:
            continue
        listing_type = "wtb" if is_wtb(title) else ("sold" if sold else "active")
        out.append(
            FoundListing(
                marketplace=marketplace,
                external_id=f"sold-{listing_id}" if listing_type == "sold" else listing_id,
                title=title,
                price_native=float(price_match.group(1)),
                currency=default_ccy,
                listing_type=listing_type,
                url=f"https://www.ebay.com/itm/{listing_id}"
                if marketplace == "ebay_us"
                else f"https://www.ebay.com.au/itm/{listing_id}",
            )
        )
    return out


def _parse_price(text: str, default_ccy: str) -> tuple[float | None, str]:
    if re.search(r"\bto\b", text, re.I):
        return None, default_ccy
    currency = default_ccy
    upper = text.upper()
    if "AUD" in upper or "AU $" in upper or "A$" in text:
        currency = "AUD"
    elif "USD" in upper or "US $" in upper:
        currency = "USD"
    elif "₩" in text or "KRW" in upper:
        currency = "KRW"
    elif "CNY" in upper:
        currency = "CNY"
    elif "£" in text:
        currency = "GBP"
    elif "€" in text:
        currency = "EUR"
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned), currency
    except ValueError:
        return None, currency


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_sold_date(text: str) -> datetime | None:
    now = datetime.utcnow()
    rel = re.search(
        r"(?:sold|ended)?\s*(\d+)\s*(minutes?|mins?|hours?|hrs?|h|days?)\s+ago",
        text,
        re.I,
    )
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            return now - timedelta(minutes=n)
        if unit.startswith("h"):
            return now - timedelta(hours=n)
        if unit.startswith("day"):
            return now - timedelta(days=n)

    match = re.search(
        r"(?:sold|ended)\s+(\d{1,2})\s+([A-Za-z]{3,9})\s*,?\s*(\d{4})?"
        r"|(?:sold|ended)\s+([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})?",
        text,
        re.I,
    )
    if not match:
        return None
    try:
        if match.group(1):
            day, month_s, year_s = int(match.group(1)), match.group(2), match.group(3)
        else:
            month_s, day, year_s = match.group(4), int(match.group(5)), match.group(6)
        month = MONTHS.get(month_s[:3].lower())
        if not month:
            return None
        year = int(year_s) if year_s else now.year
        parsed = datetime(year, month, day)
        if parsed > now + timedelta(days=1):
            parsed = datetime(year - 1, month, day)
        return parsed
    except (TypeError, ValueError):
        return None


def _id_from_url(url: str) -> str | None:
    match = re.search(r"/itm/(\d+)", url)
    return match.group(1) if match else None


def _dedupe(rows: list[FoundListing]) -> list[FoundListing]:
    seen: set[str] = set()
    unique: list[FoundListing] = []
    for row in rows:
        if row.external_id in seen:
            continue
        seen.add(row.external_id)
        unique.append(row)
    return unique

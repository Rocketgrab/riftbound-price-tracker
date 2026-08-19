from __future__ import annotations

from urllib.parse import quote

GOOFISH_T1_SEARCH = "https://www.goofish.com/search?q=%E7%AC%A6%E6%96%87%E6%88%98%E5%9C%BAT1"

# Search URLs sorted toward cheapest asks where the site supports it.
MARKETPLACES = [
    {
        "key": "ebay_au",
        "id": "ebay",
        "label": "eBay Australia",
        "search_url": (
            "https://www.ebay.com.au/sch/i.html?_nkw=Riftbound+T1+Signature"
            "&LH_BIN=1&_sop=15&_ipg=60"
        ),
        "sort": "Price + shipping: lowest",
        "currency": "AUD",
    },
    {
        "key": "ebay_us",
        "id": "ebay",
        "label": "eBay United States",
        "search_url": (
            "https://www.ebay.com/sch/i.html?_nkw=Riftbound+T1+Signature"
            "&LH_BIN=1&_sop=15&_ipg=60"
        ),
        "sort": "Price + shipping: lowest",
        "currency": "USD",
    },
    {
        "key": "bunjang_kr",
        "id": "bunjang_kr",
        "label": "Bunjang KR",
        "search_url": "https://m.bunjang.co.kr/search/products?q=%EB%A6%AC%ED%94%84%ED%8A%B8%EB%B0%94%EC%9A%B4%EB%93%9C%20T1%20%EC%8B%9C%EA%B7%B8%EB%8B%88%EC%B2%98&order=price",
        "sort": "Lowest price",
        "currency": "KRW",
    },
    {
        "key": "bunjang_global",
        "id": "bunjang_global",
        "label": "Bunjang Global",
        "search_url": "https://globalbunjang.com/search?keyword=Riftbound%20T1%20Signature",
        "sort": "Search results",
        "currency": None,
    },
    {
        "key": "karrot",
        "id": "karrot",
        "label": "Karrot",
        "search_url": "https://www.daangn.com/search/" + quote("리프트바운드 T1"),
        "sort": "Search results",
        "currency": "KRW",
    },
    {
        "key": "xianyu",
        "id": "xianyu",
        "label": "Xianyu (Goofish)",
        "search_url": GOOFISH_T1_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
]


MARKET_ALIASES = {
    "ebay": ["ebay", "ebay_au", "ebay_us"],
    "goofish": ["xianyu"],
    "xianyu": ["xianyu"],
}


def expand_marketplaces(selected: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in selected:
        key = name.strip()
        aliases = MARKET_ALIASES.get(key.lower(), [key])
        for alias in aliases:
            if alias and alias not in seen:
                seen.add(alias)
                out.append(alias)
    return out


def search_url_for(marketplace: str, currency: str | None = None) -> str:
    if marketplace in {"ebay", "ebay_au"} and (currency == "AUD" or marketplace == "ebay_au"):
        return next(m["search_url"] for m in MARKETPLACES if m["key"] == "ebay_au")
    if marketplace in {"ebay", "ebay_us"}:
        return next(m["search_url"] for m in MARKETPLACES if m["key"] == "ebay_us")
    for market in MARKETPLACES:
        if market["id"] == marketplace or market["key"] == marketplace:
            return market["search_url"]
    return GOOFISH_T1_SEARCH

from __future__ import annotations

from urllib.parse import quote, quote_plus

from app.classify import LANG_EN, LANG_KO, LANG_ZH, SKU_PLAYER, SKU_SIGNATURE

GOOFISH_T1_SEARCH = "https://www.goofish.com/search?q=%E7%AC%A6%E6%96%87%E6%88%98%E5%9C%BAT1"
CN_PRIMARY = "符文战场T1"
CN_QUERY = quote(CN_PRIMARY)
DEWU_SEARCH = f"https://www.dewu.com/searchs?keyword={CN_QUERY}"
TAOBAO_SEARCH = f"https://s.taobao.com/search?q={CN_QUERY}"
ZHUANZHUAN_SEARCH = f"https://m.zhuanzhuan.com/u/search?kw={CN_QUERY}"
JD_SEARCH = f"https://search.jd.com/Search?keyword={CN_QUERY}&enc=utf-8"
WEIDIAN_SEARCH = f"https://weidian.com/search.html?keyword={CN_QUERY}"


def ebay_search(host: str, term: str) -> str:
    return f"{host}?_nkw={quote_plus(term)}&LH_BIN=1&_sop=15&_ipg=60"


def bunjang_kr_search(term: str) -> str:
    return f"https://m.bunjang.co.kr/search/products?q={quote(term)}&order=price"


def bunjang_global_search(term: str) -> str:
    return f"https://globalbunjang.com/search?keyword={quote(term)}"


def karrot_search(term: str) -> str:
    return f"https://www.daangn.com/search/{quote(term)}"


def goofish_search(term: str) -> str:
    return f"https://www.goofish.com/search?q={quote(term)}"


def taobao_search(term: str) -> str:
    return f"https://s.taobao.com/search?q={quote(term)}"


def dewu_search(term: str) -> str:
    return f"https://www.dewu.com/searchs?keyword={quote(term)}"


def poizon_search(term: str) -> str:
    return f"https://www.poizon.com/search?keyword={quote(term)}"


def zhuanzhuan_search(term: str) -> str:
    return f"https://m.zhuanzhuan.com/u/search?kw={quote(term)}"


def jd_search(term: str) -> str:
    return f"https://search.jd.com/Search?keyword={quote(term)}&enc=utf-8"


def weidian_search(term: str) -> str:
    return f"https://weidian.com/search.html?keyword={quote(term)}"


# Search URLs sorted toward cheapest asks where the site supports it.
MARKETPLACES = [
    {
        "key": "ebay_au",
        "id": "ebay",
        "label": "eBay Australia",
        "search_url": ebay_search("https://www.ebay.com.au/sch/i.html", "Riftbound T1 Signature"),
        "sort": "Price + shipping: lowest",
        "currency": "AUD",
    },
    {
        "key": "ebay_us",
        "id": "ebay",
        "label": "eBay United States",
        "search_url": ebay_search("https://www.ebay.com/sch/i.html", "Riftbound T1 Signature"),
        "sort": "Price + shipping: lowest",
        "currency": "USD",
    },
    {
        "key": "bunjang_kr",
        "id": "bunjang_kr",
        "label": "Bunjang KR",
        "search_url": bunjang_kr_search("리프트바운드 T1 시그니처"),
        "sort": "Lowest price",
        "currency": "KRW",
    },
    {
        "key": "bunjang_global",
        "id": "bunjang_global",
        "label": "Bunjang Global",
        "search_url": bunjang_global_search("리프트바운드 T1 시그니처"),
        "sort": "Search results",
        "currency": "KRW",
    },
    {
        "key": "karrot",
        "id": "karrot",
        "label": "Karrot",
        "search_url": karrot_search("리프트바운드 T1"),
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
    {
        "key": "taobao",
        "id": "taobao",
        "label": "Taobao",
        "search_url": TAOBAO_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
    {
        "key": "dewu",
        "id": "dewu",
        "label": "Dewu / Poizon",
        "search_url": DEWU_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
    {
        "key": "zhuanzhuan",
        "id": "zhuanzhuan",
        "label": "Zhuanzhuan",
        "search_url": ZHUANZHUAN_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
    {
        "key": "jd",
        "id": "jd",
        "label": "JD.com",
        "search_url": JD_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
    {
        "key": "weidian",
        "id": "weidian",
        "label": "Weidian",
        "search_url": WEIDIAN_SEARCH,
        "sort": "Search 符文战场T1",
        "currency": "CNY",
    },
]


# Headline cards use the cheapest ask on the edition's home marketplaces.
HOME_MARKETS = {
    LANG_EN: ("ebay_au", "ebay_us", "ebay"),
    LANG_KO: ("bunjang_kr", "bunjang_global", "karrot"),
    LANG_ZH: ("xianyu", "taobao", "dewu", "zhuanzhuan", "jd", "weidian"),
}


MARKET_ALIASES = {
    "ebay": ["ebay", "ebay_au", "ebay_us"],
    "goofish": ["xianyu"],
    "xianyu": ["xianyu"],
    "china": ["xianyu", "taobao", "dewu", "zhuanzhuan", "jd", "weidian"],
    "poizon": ["dewu"],
}

SIG_EN = ["Riftbound T1 Signature", "Riftbound T1 Signature English", "Riftbound T1 Signature Korean", "Riftbound T1 Signature Chinese"]
SIG_KO = ["리프트바운드 T1 시그니처", "리프트바운드 T1 한글", "리프트바운드 T1 영문", "리프트바운드 T1 중문"]
SIG_CN = ["符文战场T1", "符文战场 T1 签名", "符文战场 T1 2025"]
PLAYER_EN = ["Riftbound T1 Player Bundle", "Riftbound T1 Player Bundle Korean", "Riftbound T1 Player Bundle Chinese"]
PLAYER_KO = ["리프트바운드 T1 플레이어 번들", "리프트바운드 T1 번들"]
PLAYER_CN = ["符文战场 T1 玩家礼盒", "符文战场T1 玩家"]


def _queries(build, terms: list[str], site: str | None = None) -> list[dict]:
    rows = []
    for term in terms:
        row = {"term": term, "url": build(term)}
        if site:
            row["site"] = site
        rows.append(row)
    return rows


def search_catalog(sku: str = SKU_SIGNATURE) -> list[dict]:
    """One card per website, with tracker queries already filled in the search bar."""
    player = sku == SKU_PLAYER
    en = PLAYER_EN if player else SIG_EN
    ko = PLAYER_KO if player else SIG_KO
    cn = PLAYER_CN if player else SIG_CN
    return [
        {
            "key": "ebay_au",
            "label": "eBay Australia",
            "queries": _queries(lambda t: ebay_search("https://www.ebay.com.au/sch/i.html", t), en),
        },
        {
            "key": "ebay_us",
            "label": "eBay United States",
            "queries": _queries(lambda t: ebay_search("https://www.ebay.com/sch/i.html", t), en),
        },
        {
            "key": "bunjang_kr",
            "label": "Bunjang KR",
            "queries": _queries(bunjang_kr_search, ko),
        },
        {
            "key": "bunjang_global",
            "label": "Bunjang Global",
            "queries": _queries(bunjang_global_search, ko),
        },
        {
            "key": "karrot",
            "label": "Karrot",
            "queries": _queries(karrot_search, ko if not player else PLAYER_KO),
        },
        {
            "key": "xianyu",
            "label": "Xianyu (Goofish)",
            "queries": _queries(goofish_search, cn),
        },
        {
            "key": "taobao",
            "label": "Taobao",
            "queries": _queries(taobao_search, cn),
        },
        {
            "key": "dewu",
            "label": "Dewu / Poizon",
            "queries": _queries(dewu_search, cn, site="Dewu")
            + _queries(poizon_search, cn[:1], site="Poizon"),
        },
        {
            "key": "zhuanzhuan",
            "label": "Zhuanzhuan",
            "queries": _queries(zhuanzhuan_search, cn),
        },
        {
            "key": "jd",
            "label": "JD.com",
            "queries": _queries(jd_search, cn),
        },
        {
            "key": "weidian",
            "label": "Weidian",
            "queries": _queries(weidian_search, cn),
        },
    ]


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

from __future__ import annotations

import re
from dataclasses import dataclass

SKU_SIGNATURE = "signature"
SKU_PLAYER = "player_bundle"
SKU_UNKNOWN = "unknown"

LANG_EN = "en"
LANG_KO = "ko"
LANG_ZH = "zh"
LANG_UNKNOWN = "unknown"

SOLD = "sold"
ACTIVE = "active"
WTB = "wtb"
ASK_TYPES = frozenset({ACTIVE, "presale"})

# Official retail. Secondary asks are currently far above these.
MSRP = {
    SKU_SIGNATURE: {LANG_EN: (360.0, "USD"), LANG_KO: (500000.0, "KRW"), LANG_ZH: (2025.0, "CNY")},
    SKU_PLAYER: {LANG_EN: (70.0, "USD"), LANG_KO: (100000.0, "KRW"), LANG_ZH: (399.0, "CNY")},
}

PRODUCT_RE = re.compile(
    r"(riftbound|리프트\s*바운드|라이프트바운드|符文战场|符文戰場)",
    re.I,
)
T1_RE = re.compile(r"(\bt1\b|티원|t1\s*(시그니처|번들|bundle)|签名|簽名)", re.I)
WORLDS_RE = re.compile(r"(worlds?\s*champion|월드\s*챔피언)", re.I)
# Single cards and other Riftbound SKUs must not enter the T1 collection series.
SINGLE_RE = re.compile(
    r"("
    r"rengar|pridestalker|overnumbered|over\s*numbered|"
    r"\bunl-\d|\balt\s*art\b|single\s*card|booster|"
    r"단품|단카|싱글|单卡|單卡|卡牌(?!套)"
    r")",
    re.I,
)

# Language of the *product edition*, not the language the ad is written in.
# "Selling Korean version" on eBay is Korean, even though the title is English.
EN_EDITION_RE = re.compile(
    r"("
    r"\benglish\b|"
    r"eng(?:lish)?\s*(edition|version|ver\.?|copy)|"
    r"\ben\s*(edition|version|ver\.?)\b|"
    r"영문\s*(판|버전|ver)?|"
    r"영어\s*판|"
    r"英文|"
    r"英版"
    r")",
    re.I,
)
KO_EDITION_RE = re.compile(
    r"("
    r"\bkorean\b|"
    r"\bkr\s*(edition|version|ver\.?|copy)|"
    r"한글\s*(판|버전)?|"
    r"국문\s*(판)?|"
    r"한국어\s*판|"
    r"한판|"
    r"韩文|"
    r"韓文|"
    r"韩版|"
    r"韓版"
    r")",
    re.I,
)
ZH_EDITION_RE = re.compile(
    r"("
    r"\bchinese\b|"
    r"\bcn\s*(edition|version|ver\.?|copy)|"
    r"simplified\s*chinese|"
    r"중문\s*(판|버전)?|"
    r"중국어\s*판|"
    r"중판|"
    r"中文|"
    r"中版|"
    r"简体|"
    r"簡體|"
    r"简中|"
    r"簡中|"
    r"国服|"
    r"國服"
    r")",
    re.I,
)

SIG_RE = re.compile(
    r"(signature|시그니처|签名版|簽名版|签版|簽名|serialized|serial\s*#|각인)",
    re.I,
)
PLAYER_RE = re.compile(
    r"(player\s*bundle|플레이어\s*번들|玩家(礼盒|禮盒|捆绑|套装|套裝)|player\s*set)",
    re.I,
)

# Buyer bids / want-to-buy posts. Same search keywords as asks, not seller listings.
# Live Bunjang mixes "구매) ...", "구매글)", "[매입]", "삽니다" next to 판매 posts.
WTB_RE = re.compile(
    "|".join(
        [
            r"\bwtb\b",
            r"want\s*to\s*buy",
            r"looking\s*to\s*buy",
            r"looking\s+for\s+(a|an|one|this|riftbound|t1)",
            r"\biso\b",
            r"in\s*search\s*of",
            r"\bbuying\b(?!\s*it\s*now)",
            r"pay(?:ing)?\s+(?:up\s+to|for)\b",
            r"삽니다",
            r"사요\b",
            r"사봅니다",
            r"구합니다",
            r"구매합니다",
            r"구매함",
            r"구매글",
            r"구매의사",
            r"구매\s*원",
            r"구해요",
            r"구해봅니다",
            r"구해용",
            r"급구",
            r"구함",
            r"^[\[(]?\s*구매",
            r"\(구매\)",
            r"\[구매",
            r"매입",
            r"수원합니다",
            r"구입합니다",
            r"구입\s*원",
            r"求购",
            r"求購",
            r"收购",
            r"收購",
            r"只收",
            r"高价收",
            r"高價收",
            r"长期收",
            r"長期收",
            r"想买",
            r"想買",
            r"求收",
            r"收一个",
            r"收個",
            r"收个",
            r"^收[^售卖賣]",
        ]
    ),
    re.I,
)

# If a title is clearly a seller ask, keep it even if it mentions a past purchase.
ASK_RE = re.compile(
    r"(팝니다|판매|급처|처분|for\s*sale|\bselling\b|buy\s*it\s*now|\bbin\b|出闲|出閒|出个|出個|转卖|轉賣|在售)",
    re.I,
)

NEGATIVE_RE = re.compile(
    "|".join(
        [
            r"\bempty\s*box\b",
            r"\bcase\s*only\b",
            r"\bbox\s*only\b",
            r"\bproxy\s*card",
            r"\bdamaged\b",
            r"공박스",
            r"빈박스",
            r"분할\s*판매",
            r"단품",
            r"슬리브\s*만",
            r"空盒",
            r"单卡",
            r"單卡",
        ]
    ),
    re.I,
)

# Only local-language marketplaces default an unlabeled listing to that edition.
# eBay / Bunjang Global ads are often written in English while selling KR/CN copies.
MARKET_EDITION_PRIOR = {
    "bunjang_kr": LANG_KO,
    "bunjang_global": LANG_KO,
    "karrot": LANG_KO,
    "xianyu": LANG_ZH,
    "taobao": LANG_ZH,
    "dewu": LANG_ZH,
    "zhuanzhuan": LANG_ZH,
    "jd": LANG_ZH,
    "weidian": LANG_ZH,
}


@dataclass
class Classification:
    sku: str
    language: str
    kept: bool
    reject_reason: str | None = None
    is_wtb: bool = False


def edition_language(title: str, marketplace: str) -> str:
    """Return EN/KO/ZH for the product edition, not the listing's written language."""
    text = title or ""
    has_en = bool(EN_EDITION_RE.search(text))
    has_ko = bool(KO_EDITION_RE.search(text))
    has_zh = bool(ZH_EDITION_RE.search(text))
    if has_ko and has_zh:
        return LANG_UNKNOWN
    if has_ko:
        return LANG_KO
    if has_zh:
        return LANG_ZH
    if has_en:
        return LANG_EN
    return MARKET_EDITION_PRIOR.get(marketplace, LANG_UNKNOWN)


def is_wtb(title: str) -> bool:
    text = (title or "").strip()
    if not text or not WTB_RE.search(text):
        return False
    # "정가 구매 후 판매" is still a seller ask. Prefix buy-posts are not.
    if ASK_RE.search(text) and not re.search(
        r"^[\[(]?\s*(구매|매입|삽니다|구입|求购|求購|wtb|iso)",
        text,
        re.I,
    ):
        return False
    return True


def is_t1_collection(title: str) -> bool:
    """True for the T1 Worlds Champion collection, not random Riftbound singles."""
    text = title or ""
    if SINGLE_RE.search(text):
        return False
    if not PRODUCT_RE.search(text):
        return False
    return bool(T1_RE.search(text) or WORLDS_RE.search(text))


def classify(title: str, marketplace: str, price_usd: float | None = None) -> Classification:
    text = title or ""
    if is_wtb(text):
        return Classification(SKU_UNKNOWN, LANG_UNKNOWN, False, "wtb", is_wtb=True)
    if NEGATIVE_RE.search(text) or SINGLE_RE.search(text):
        return Classification(SKU_UNKNOWN, LANG_UNKNOWN, False, "negative_keyword")
    if not is_t1_collection(text):
        return Classification(SKU_UNKNOWN, LANG_UNKNOWN, False, "unrelated")

    sku = SKU_UNKNOWN
    if SIG_RE.search(text):
        sku = SKU_SIGNATURE
    elif PLAYER_RE.search(text):
        sku = SKU_PLAYER
    elif price_usd is not None:
        if 400 <= price_usd <= 8000:
            sku = SKU_SIGNATURE
        elif 35 <= price_usd <= 180:
            sku = SKU_PLAYER

    if sku == SKU_UNKNOWN:
        sku = SKU_SIGNATURE

    language = edition_language(text, marketplace)
    return Classification(sku=sku, language=language, kept=True)

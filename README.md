# Riftbound T1 language-edition price tracker

Hourly tracker for the **Riftbound × T1 2025 Worlds Champion Collection** across eBay, Bunjang KR, Bunjang Global, Karrot, and Xianyu (Goofish).

This is a **presale** market. The dashboard tracks **seller asks**, not buyer bids. English, Korean, and Chinese editions are three separate **AUD** median lines.

This version:

- Charts **asks** (팝니다 / BIN listings). Drops **bids** (삽니다, 구매, 매입, WTB).
- Splits **Signature Edition** vs **Player Bundle** (different MSRPs: $360 vs $70).
- Splits **EN / KR / CN** language editions as three colored median lines.
- Displays market prices in **AUD** (native currency is kept on listings).
- Price band allows current secondary asks (~₩1,000,000 KR, ~A$3,000–5,000 eBay, ~¥4,000–6,000 Xianyu).
- Converts KRW/CNY/USD with a **daily FX snapshot**, then to AUD.
- Shows marketplace search links and the **cheapest kept ask**, refreshed hourly.
- Lets each marketplace collector fail on its own. The rest of the job still writes.
- Seeds realistic presale history so the chart works on day one, then live collectors fill forward.
- Defaults the SKU to Signature Edition, which is the set currently in presale.

MSRP used for the dashed guides (converted to AUD in the UI):

| Edition | English | Korean | Chinese |
| --- | --- | --- | --- |
| Signature | $360 | ₩500,000 | ¥2,025 |
| Player Bundle | $70 | ₩100,000 | ¥399 |

Chinese product name used in search: **符文战场**. Korean: **리프트바운드**.

Xianyu search used for Chinese asks: [Goofish 符文战场T1](https://www.goofish.com/search?q=%E7%AC%A6%E6%96%87%E6%88%98%E5%9C%BAT1).

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app
```

Open http://127.0.0.1:8000

- Dashboard loads immediately from seed data.
- **Run collectors** attempts live fetches. Bunjang/eBay sometimes work; Karrot and Xianyu often block anonymous requests. That is expected.
- Collectors run **every hour** while the server is up (`APScheduler`). The public site is published by `.github/workflows/hourly-publish.yml`, which also persists `data/tracker.db` and refreshes the dashboard snapshot every hour.

Optional `.env` (see `.env.example`):

- `EBAY_APP_ID` — use eBay Finding API instead of HTML search
- `XIANYU_COOKIE` — only if you already have a logged-in Xianyu session cookie
- `COLLECT_ON_STARTUP=true`

Manual collect without the UI:

```bash
python -m app.collect
```

## Data model

- `raw_listings` — one row per marketplace listing, with `sku`, `language`, native price, USD, AUD via FX, and keep/reject reason
- `daily_aggregates` — median / high / low / volume per date × marketplace × sku × language
- `fx_rates` — USD per unit of KRW/CNY/AUD for that calendar day (historical rows are not recomputed with today's FX)

## Legal / practical limits

Collectors hit **public search pages or public JSON search endpoints** with retries and delays. They do not log in, bypass CAPTCHAs, or automate purchases. Xianyu in particular is hostile to anonymous collection; the adapter fails soft and the dashboard keeps the latest Goofish snapshot so cheapest-offer links still work.

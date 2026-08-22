from __future__ import annotations

import unittest
from datetime import date

from app.classify import classify, is_wtb
from app.main import _carry_price_gaps
from app.stats import iqr_keep, in_sku_band, median


class ClassifyTests(unittest.TestCase):
    def test_drops_korean_buy_posts(self):
        self.assertTrue(is_wtb("삽니다 리프트바운드 T1 시그니처"))
        self.assertFalse(is_wtb("리프트바운드 T1 시그니처 팝니다"))

    def test_edition_language_from_title(self):
        ko = classify("Riftbound T1 Signature Korean edition", "ebay_us", 1200)
        zh = classify("Presale Chinese Riftbound T1 Signature Box", "ebay_au", 1200)
        en = classify("Riftbound T1 Signature Edition English", "ebay_au", 2500)
        self.assertEqual(ko.language, "ko")
        self.assertEqual(zh.language, "zh")
        self.assertEqual(en.language, "en")
        self.assertTrue(ko.kept and zh.kept and en.kept)

    def test_negative_photo_print(self):
        verdict = classify("English Riftbound T1 Signature Photo print", "ebay_us", 1500)
        self.assertFalse(verdict.kept)


class StatsTests(unittest.TestCase):
    def test_iqr_keeps_small_goofish_book(self):
        prices = [595.0, 684.0, 727.0, 744.0, 876.0]
        self.assertEqual(iqr_keep(prices), prices)
        self.assertEqual(median(prices), 727.0)

    def test_signature_band(self):
        self.assertTrue(in_sku_band("signature", 555))
        self.assertFalse(in_sku_band("signature", 50))


class CarryGapTests(unittest.TestCase):
    def test_fills_interior_nulls_when_that_day_had_volume(self):
        row = _carry_price_gaps(
            {
                "median": [100.0, None, 110.0],
                "high": [120.0, None, 130.0],
                "low": [90.0, None, 100.0],
                "volume": [2, 4, 2],
            }
        )
        self.assertEqual(row["median"], [100.0, 100.0, 110.0])
        self.assertEqual(row["high"], [120.0, 100.0, 130.0])
        self.assertEqual(row["low"], [90.0, 100.0, 100.0])

    def test_does_not_invent_ohlc_on_zero_volume_days(self):
        row = _carry_price_gaps(
            {
                "median": [100.0, None, 110.0],
                "high": [120.0, None, 130.0],
                "low": [90.0, None, 100.0],
                "volume": [2, 0, 2],
            }
        )
        self.assertEqual(row["median"], [100.0, None, 110.0])

    def test_leaves_leading_nulls(self):
        row = _carry_price_gaps(
            {
                "median": [None, 50.0],
                "high": [None, 60.0],
                "low": [None, 40.0],
                "volume": [0, 2],
            }
        )
        self.assertIsNone(row["median"][0])
        self.assertEqual(row["median"][1], 50.0)


class IngestDateTests(unittest.TestCase):
    def test_existing_rows_keep_first_observed_day(self):
        from app.collectors.base import CollectResult, FoundListing
        from app.db import RawListing, SessionLocal, init_db
        from app.pipeline import _ingest
        from datetime import datetime, timezone
        from sqlalchemy import delete, select

        init_db()
        session = SessionLocal()
        try:
            session.execute(delete(RawListing).where(RawListing.external_id == "audit-keep-day"))
            session.commit()
            session.add(
                RawListing(
                    marketplace="ebay_us",
                    external_id="audit-keep-day",
                    title="Riftbound T1 Signature English listed",
                    price_native=2000,
                    currency="USD",
                    price_usd=2000,
                    listing_type="active",
                    sku="signature",
                    language="en",
                    url="https://ebay.com/itm/audit-keep-day",
                    scraped_at=datetime(2026, 8, 21),
                    observed_on=date(2026, 8, 21),
                    last_seen_on=date(2026, 8, 21),
                    source="live",
                    kept=True,
                )
            )
            session.commit()
            result = CollectResult(
                "ebay_us",
                listings=[
                    FoundListing(
                        marketplace="ebay_us",
                        external_id="audit-keep-day",
                        title="Riftbound T1 Signature English listed",
                        price_native=2100,
                        currency="USD",
                        listing_type="active",
                        url="https://ebay.com/itm/audit-keep-day",
                    )
                ],
            )
            _ingest(session, result, datetime.now(timezone.utc))
            row = session.scalars(select(RawListing).where(RawListing.external_id == "audit-keep-day")).one()
            self.assertEqual(row.observed_on, date(2026, 8, 21))
            self.assertEqual(row.last_seen_on, date.today())
            self.assertEqual(row.price_native, 2100)
        finally:
            session.execute(delete(RawListing).where(RawListing.external_id == "audit-keep-day"))
            session.commit()
            session.close()


if __name__ == "__main__":
    unittest.main()

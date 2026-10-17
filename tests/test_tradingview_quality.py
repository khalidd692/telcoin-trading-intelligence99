import unittest
from datetime import datetime, timezone

from src.tradingview_quality import (
    diagnose_identical_cross_venue_data,
    preserve_native_verdict,
    validate_order_book,
    validate_timestamp,
)


class IdenticalVenuePayloadTests(unittest.TestCase):
    def test_exactly_identical_technical_fields_are_flagged_diagnostically(self):
        left = {"price": "0.0016567", "volume": 888539, "rsi": 21.0, "rating": "SELL"}
        right = {"price": 0.0016567, "volume": "888539", "rsi": 21, "rating": "SELL"}
        result = diagnose_identical_cross_venue_data(
            "MEXC:TELUSDT", left, "KUCOIN:TELUSDT", right,
            ["price", "volume", "rsi", "rating"],
        )
        self.assertEqual(result["status"], "SUSPECT_IDENTIQUE")
        self.assertEqual(len(result["matching_fields"]), 4)
        self.assertIn("ne prouvent pas", result["note"])

    def test_different_payload_is_not_flagged(self):
        result = diagnose_identical_cross_venue_data(
            "MEXC:TELUSDT", {"price": 1, "volume": 2, "rsi": 3},
            "KUCOIN:TELUSDT", {"price": 1, "volume": 2, "rsi": 4},
            ["price", "volume", "rsi"],
        )
        self.assertEqual(result["status"], "NON_SIGNALÉ")

    def test_same_symbol_is_not_cross_venue_alert(self):
        result = diagnose_identical_cross_venue_data(
            "MEXC:TELUSDT", {"price": 1, "volume": 2, "rsi": 3},
            "MEXC:TELUSDT", {"price": 1, "volume": 2, "rsi": 3},
            ["price", "volume", "rsi"],
        )
        self.assertEqual(result["status"], "NON_SIGNALÉ")


class OrderBookQualityTests(unittest.TestCase):
    def test_valid_book_passes(self):
        result = validate_order_book([[0.0016, 100], [0.0015, 200]], [[0.0017, 100], [0.0018, 200]], observed_age_seconds=10)
        self.assertEqual(result["status"], "VERIFIED")

    def test_empty_or_incomplete_book_fails(self):
        self.assertEqual(validate_order_book([], [[0.0017, 100]])["status"], "NON_VÉRIFIÉ")
        self.assertEqual(validate_order_book([[0.0016]], [[0.0017, 100]])["status"], "NON_VÉRIFIÉ")

    def test_crossed_book_fails(self):
        result = validate_order_book([[0.0018, 100]], [[0.0017, 100]])
        self.assertIn("BOOK_CROSSED_OR_LOCKED", result["problems"])

    def test_stale_or_future_age_fails(self):
        self.assertIn("BOOK_STALE", validate_order_book([[1, 1]], [[2, 1]], observed_age_seconds=121)["problems"])
        self.assertIn("BOOK_AGE_INVALID_OR_FUTURE", validate_order_book([[1, 1]], [[2, 1]], observed_age_seconds=-10)["problems"])


class TimestampTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 17, 20, 0, tzinfo=timezone.utc)

    def test_fresh_timestamp_passes(self):
        result = validate_timestamp("2026-10-17T19:59:00Z", now=self.now, max_age_seconds=120)
        self.assertEqual(result["status"], "VERIFIED")

    def test_stale_timestamp_fails(self):
        result = validate_timestamp("2026-10-17T19:00:00Z", now=self.now, max_age_seconds=120)
        self.assertEqual(result["reason"], "DATA_STALE")

    def test_future_timestamp_fails(self):
        result = validate_timestamp("2026-10-17T20:01:00Z", now=self.now)
        self.assertEqual(result["reason"], "TIMESTAMP_IN_FUTURE")

    def test_invalid_timestamp_fails(self):
        self.assertEqual(validate_timestamp("not-a-date", now=self.now)["status"], "NON_VÉRIFIÉ")


class NativeVerdictSafetyTests(unittest.TestCase):
    def test_suspect_tradingview_never_changes_native_verdict(self):
        for native in ("ATTENDRE", "SURVEILLER"):
            result = preserve_native_verdict(native, "SUSPECT_IDENTIQUE")
            self.assertEqual(result["status"], native)
            self.assertEqual(result["effect"], "IGNORÉ_PAR_DÉFAUT")

    def test_verified_tradingview_is_only_cross_check(self):
        result = preserve_native_verdict("ATTENDRE", "VERIFIED")
        self.assertEqual(result["status"], "ATTENDRE")
        self.assertEqual(result["effect"], "CONTRÔLE_CROISÉ_SEULEMENT")


if __name__ == "__main__":
    unittest.main()

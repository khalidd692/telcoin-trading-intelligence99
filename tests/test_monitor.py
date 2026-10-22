import unittest
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import monitor

REAL_MEXC_TICKER = monitor.mexc_ticker


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 15, 45, tzinfo=timezone.utc)
        self.now_epoch = self.now.timestamp()
        self.ticker = {
            "last": 0.00178, "bid": 0.001779, "ask": 0.001781,
            "spread_pct": 0.1124, "quote_volume_24h": 12345.0,
            "change_pct_24h": 0.7, "source": "MEXC public ticker",
            "observed_at": self.now.isoformat(),
        }
        self.kucoin = {"last": 0.001781, "bid": 0.001780, "ask": 0.001782}
        start = int((self.now_epoch - 1200 - 59 * 900) * 1000)
        self.candles = [
            [start + i * 900_000, 0.0017 + i * 1e-7,
             0.0018 + i * 1e-7, 0.0016 + i * 1e-7,
             0.00171 + i * 1e-7, 1000.0 + i]
            for i in range(60)
        ]
        self.patches = [
            patch.object(monitor, "utc_now", return_value=self.now),
            patch.object(monitor.time, "time", return_value=self.now_epoch),
            patch.object(monitor, "mexc_ticker", return_value=self.ticker),
            patch.object(monitor, "candles_15m", return_value=self.candles),
            patch.object(monitor, "kucoin_price", return_value=self.kucoin),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_valid_report_contains_real_source_fields_and_indicators(self):
        report = monitor.build_report()
        self.assertEqual(report["status"], "SURVEILLER")
        self.assertEqual(report["sources"]["mexc_ticker"]["last"], self.ticker["last"])
        self.assertEqual(report["sources"]["kucoin_level1"]["last"], self.kucoin["last"])
        self.assertIsNotNone(report["indicators"]["ema50"])
        self.assertEqual(len(report["indicators"]["close_series"]), 48)

    def test_api_unavailable_fails_closed(self):
        with patch.object(monitor, "mexc_ticker", side_effect=monitor.DataUnavailable("offline")):
            report = monitor.build_report()
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertNotIn("last", report["sources"].get("mexc_ticker", {}))

    def test_stale_candles_fail_closed(self):
        stale = [row.copy() for row in self.candles]
        for row in stale:
            row[0] -= 2_000_000
        with patch.object(monitor, "candles_15m", return_value=stale):
            report = monitor.build_report()
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIn("stale", report["error"])

    def test_inconsistent_exchange_quotes_fail_closed(self):
        far_away = {"last": 0.002, "bid": 0.001999, "ask": 0.002001}
        with patch.object(monitor, "kucoin_price", return_value=far_away):
            report = monitor.build_report()
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["checks"][-1]["status"], "FAIL")

    def test_mexc_schema_error_is_rejected(self):
        with patch.object(monitor, "mexc_ticker", REAL_MEXC_TICKER):
            with patch.object(monitor, "http_json", return_value={"symbol": "OTHER"}):
                with self.assertRaises(monitor.DataUnavailable):
                    monitor.mexc_ticker()

    def test_fallback_report_has_no_market_quote(self):
        report = monitor.fallback_report("collector failed")
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIsNone(report["indicators"])
        self.assertNotIn("last", report["sources"]["mexc_ticker"])

    def test_unexpected_error_writes_fallback_and_exits_nonzero(self):
        output = Path(__file__).with_name("_report_test.json")
        try:
            with patch.object(sys, "argv", ["monitor", "--output", str(output)]):
                with patch.object(monitor, "build_report", side_effect=RuntimeError("boom")):
                    self.assertEqual(monitor.main(), 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ATTENDRE")
            self.assertNotIn("last", report["sources"]["mexc_ticker"])
        finally:
            output.unlink(missing_ok=True)

    def test_valid_attendre_report_exits_zero(self):
        """A valid ATTENDRE is a fail-closed decision, not a collection failure."""
        output = Path(__file__).with_name("_report_test.json")
        valid_attendre = {
            "schema_version": 1, "generated_at": self.now.isoformat(),
            "symbol": "TELUSDT", "mode": "READ_ONLY_ALERTS",
            "status": "ATTENDRE", "collection_status": "VALID",
            "sources": {"mexc_ticker": {"status": "OK"}}, "checks": [],
            "indicators": None,
        }
        try:
            with patch.object(sys, "argv", ["monitor", "--output", str(output)]):
                with patch.object(monitor, "build_report", return_value=valid_attendre):
                    self.assertEqual(monitor.main(), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "ATTENDRE")
        finally:
            output.unlink(missing_ok=True)

    def test_fallback_report_exits_nonzero(self):
        """Missing or incoherent market data must still fail the collection step."""
        output = Path(__file__).with_name("_report_test.json")
        try:
            with patch.object(sys, "argv", ["monitor", "--output", str(output)]):
                with patch.object(monitor, "build_report", return_value=monitor.fallback_report("offline")):
                    self.assertEqual(monitor.main(), 1)
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()


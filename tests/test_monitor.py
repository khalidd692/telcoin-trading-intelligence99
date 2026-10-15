import unittest
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src import monitor
from src.kraken_market_data import KrakenMarketDataError


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 14, 15, 45, tzinfo=timezone.utc)
        now_epoch = int(self.now.timestamp())
        self.candles = []
        start = now_epoch - 1200 - 59 * 900
        for i in range(60):
            self.candles.append({
                "open_time": datetime.fromtimestamp(start + i*900, timezone.utc).isoformat(),
                "open_time_epoch": start + i*900,
                "open": 0.0017 + i*1e-7, "high": 0.0018 + i*1e-7,
                "low": 0.0016 + i*1e-7, "close": 0.00171 + i*1e-7,
                "volume": 1000.0 + i, "trade_count": 10,
            })
        self.snapshot = {
            "source": "Kraken Spot public REST", "symbol": "TEL/USD", "pair_key": "TELUSD",
            "observed_at_utc": self.now.isoformat(), "server_time_utc": self.now.isoformat(),
            "ticker_timestamp": None, "ticker_freshness_verified": False,
            "ticker_freshness_note": "Ticker endpoint has no quote timestamp; cross-checked.",
            "depth_timestamp_note": "Level timestamp is not snapshot timestamp.",
            "last": 0.00178, "bid": 0.001779, "ask": 0.001781, "spread_pct": 0.1124,
            "trade": {"price": 0.00178, "quantity": 1000.0, "timestamp_utc": self.now.isoformat(), "age_seconds": 2},
            "depth": {"bids": [{"price": 0.001779, "quantity": 1000.0}], "asks": [{"price": 0.001781, "quantity": 1000.0}]},
            "latest_closed_15m_candle": self.candles[-1], "recent_closed_15m_candles": self.candles,
            "validation": {"exact_pair": True, "positive_prices": True, "bid_below_ask": True,
                "spread_within_limit": True, "depth_snapshot_retrieved": True, "trade_fresh": True,
                "ticker_depth_consistent": True, "ticker_trade_consistent": True, "closed_candle_available": True},
            "collection_duration_seconds": 2.1,
        }
        self.patches = [
            patch.object(monitor, "utc_now", return_value=self.now),
            patch.object(monitor, "collect_kraken_snapshot", return_value=self.snapshot),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_valid_report_uses_exact_kraken_usd_pair_and_indicators(self):
        report = monitor.build_report()
        self.assertEqual(report["symbol"], "TELUSD")
        self.assertEqual(report["pair"], "TEL/USD")
        self.assertEqual(report["status"], "SURVEILLER")
        self.assertEqual(report["sources"]["kraken_market"]["pair"], "TEL/USD")
        self.assertEqual(report["sources"]["kraken_market"]["last"], self.snapshot["last"])
        self.assertEqual(report["sources"]["kraken_depth"]["status"], "OK")
        self.assertEqual(report["sources"]["kraken_trades"]["status"], "OK")
        self.assertIsNotNone(report["indicators"]["ema50"])
        self.assertEqual(len(report["indicators"]["close_series"]), 48)

    def test_api_unavailable_fails_closed(self):
        with patch.object(monitor, "collect_kraken_snapshot", side_effect=KrakenMarketDataError("offline")):
            report = monitor.build_report()
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertNotIn("last", report["sources"]["kraken_market"])

    def test_stale_candles_fail_closed(self):
        stale_snapshot = dict(self.snapshot)
        stale_candles = []
        for row in self.candles:
            old = dict(row)
            old["open_time_epoch"] -= 2_000_000
            old["open_time"] = datetime.fromtimestamp(old["open_time_epoch"], timezone.utc).isoformat()
            stale_candles.append(old)
        stale_snapshot["recent_closed_15m_candles"] = stale_candles
        stale_snapshot["latest_closed_15m_candle"] = stale_candles[-1]
        with patch.object(monitor, "collect_kraken_snapshot", return_value=stale_snapshot):
            report = monitor.build_report()
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIn("stale", report["error"])

    def test_usd_pair_is_not_reported_as_usdt(self):
        report = monitor.build_report()
        self.assertEqual(report["quote_currency"], "USD")
        self.assertNotEqual(report["symbol"], "TELUSDT")
        self.assertIn("not interchangeable", report["disclaimer"])

    def test_fallback_report_has_no_market_quote(self):
        report = monitor.fallback_report("collector failed")
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertIsNone(report["indicators"])
        self.assertNotIn("last", report["sources"]["kraken_market"])

    def test_unexpected_error_writes_fallback_and_exits_nonzero(self):
        output = Path(__file__).with_name("_report_test.json")
        try:
            with patch.object(sys, "argv", ["monitor", "--output", str(output)]):
                with patch.object(monitor, "build_report", side_effect=RuntimeError("boom")):
                    self.assertEqual(monitor.main(), 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ATTENDRE")
            self.assertNotIn("last", report["sources"]["kraken_market"])
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

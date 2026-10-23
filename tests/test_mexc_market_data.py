import unittest
from unittest.mock import patch
from src import mexc_market_data as md


def responses(now_ms=1_800_000_000_000, *, trade_age_ms=5_000, bid="0.001692", ask="0.001700", last="0.001695"):
    trade_ms = now_ms - trade_age_ms
    return {
        "/api/v3/time": ({"serverTime": now_ms}, now_ms),
        "/api/v3/ticker/price?symbol=TELUSDT": ({"symbol": "TELUSDT", "price": last}, now_ms),
        "/api/v3/ticker/bookTicker?symbol=TELUSDT": ({
            "symbol": "TELUSDT", "bidPrice": bid, "bidQty": "1000", "askPrice": ask, "askQty": "1200"
        }, now_ms),
        "/api/v3/depth?symbol=TELUSDT&limit=5": ({
            "bids": [[bid, "1000"], ["0.001680", "2000"]],
            "asks": [[ask, "1200"], ["0.001710", "2500"]]
        }, now_ms),
        "/api/v3/trades?symbol=TELUSDT&limit=1": ([{
            "price": last, "time": trade_ms, "qty": "100", "isBuyerMaker": False
        }], now_ms),
        "/api/v3/klines?symbol=TELUSDT&interval=15m&limit=5": ([
            [now_ms - 3_600_000, "0.00168", "0.00172", "0.00167", "0.00170", "100"],
            [now_ms - 2_700_000, "0.00170", "0.00173", "0.00169", "0.001695", "110"],
            [now_ms - 1_800_000, "0.001695", "0.00171", "0.00169", "0.00170", "120"],
            [now_ms - 900_000, "0.00170", "0.00172", "0.00169", "0.001695", "130"],
            [now_ms, "0.001695", "0.00173", "0.00169", "0.00171", "140"],
        ], now_ms),
    }


class MarketSnapshotTests(unittest.TestCase):
    def run_snapshot(self, payloads):
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with patch.object(md.time, "time", return_value=1_800_000_0000):
                with patch.object(md.datetime, "now", return_value=md.datetime(2027, 1, 15, tzinfo=md.timezone.utc)):
                    return md.collect_snapshot()

    def test_valid_snapshot_has_prices_book_timestamps_and_closed_candle(self):
        now_ms = 1_800_000_000_000
        payloads = responses(now_ms)
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]), \
             patch.object(md.time, "time", return_value=now_ms / 1000):
            result = md.collect_snapshot()
        self.assertEqual(result["symbol"], "TELUSDT")
        self.assertGreater(result["last_price"], 0)
        self.assertLess(result["best_bid"]["price"], result["best_ask"]["price"])
        self.assertIn("received_at_utc", result)
        self.assertIn("server_time_utc", result)
        self.assertTrue(result["validation"]["last_trade_fresh"])
        self.assertTrue(result["latest_closed_15m_candle"]["close"] > 0)
        self.assertAlmostEqual(result["spread_pct"], (0.001700 - 0.001692) / ((0.001700 + 0.001692) / 2) * 100, places=4)

    def test_network_error_fails_closed(self):
        with patch.object(md, "_get_json", side_effect=md.MarketDataError("offline")):
            with self.assertRaisesRegex(md.MarketDataError, "offline"):
                md.collect_snapshot()

    def test_invalid_price_fails_closed(self):
        payloads = responses()
        payloads["/api/v3/ticker/price?symbol=TELUSDT"] = ({"symbol": "TELUSDT", "price": "0"}, 0)
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with self.assertRaisesRegex(md.MarketDataError, "last price"):
                md.collect_snapshot()

    def test_bid_greater_than_or_equal_to_ask_fails_closed(self):
        payloads = responses(bid="0.00170", ask="0.00170")
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with self.assertRaisesRegex(md.MarketDataError, "bid >= ask"):
                md.collect_snapshot()

    def test_stale_last_trade_fails_closed(self):
        payloads = responses(trade_age_ms=120_000)
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with self.assertRaisesRegex(md.MarketDataError, "stale"):
                md.collect_snapshot()

    def test_wide_spread_fails_closed(self):
        payloads = responses(bid="0.00160", ask="0.00170", last="0.00165")
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with self.assertRaisesRegex(md.MarketDataError, "spread too wide"):
                md.collect_snapshot()

    def test_depth_mismatch_fails_closed(self):
        payloads = responses()
        payloads["/api/v3/depth?symbol=TELUSDT&limit=5"] = ({"bids": [["0.00160", "1000"]], "asks": [["0.00170", "1000"]]}, 0)
        with patch.object(md, "_get_json", side_effect=lambda path: payloads[path]):
            with self.assertRaisesRegex(md.MarketDataError, "disagree"):
                md.collect_snapshot()


if __name__ == "__main__":
    unittest.main()

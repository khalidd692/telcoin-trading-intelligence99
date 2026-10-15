import unittest
from unittest.mock import patch

from src import kraken_market_data as km


def fixture_payloads(*, pair=True, bid="0.001689", ask="0.001691",
                     trade_age=5, depth_age=5, spread_pair="TEL/USD"):
    now = 1_797_000_000
    pair_meta = {"altname": "TELUSD", "wsname": spread_pair, "status": "online",
                 "base": "TEL", "quote": "ZUSD"}
    pairs = {"TELUSD": pair_meta} if pair else {"XBTUSD": {
        "altname": "XBTUSD", "wsname": "XBT/USD", "status": "online"}}
    depth = {
        "bids": [[bid, "10000", str(now-depth_age)], ["0.001688", "5000", str(now-depth_age)]],
        "asks": [[ask, "9000", str(now-depth_age)], ["0.001692", "4000", str(now-depth_age)]],
    }
    candles = [
        [now-1800, "0.00170", "0.00172", "0.00168", "0.00170", "0.00170", "120000", 25],
        [now-900, "0.00170", "0.00171", "0.00168", "0.00169", "0.00169", "100000", 20],
        [now, "0.00169", "0.00170", "0.00168", "0.00169", "0.00169", "2000", 2],
    ]
    return {
        "AssetPairs": {"error": [], "result": pairs},
        "Time": {"error": [], "result": {"unixtime": now, "rfc1123": "Thu, 15 Oct 2026 00:00:00 GMT"}},
        "Ticker": {"error": [], "result": {"TELUSD": {
            "a": [ask, "9000", "1"], "b": [bid, "10000", "1"], "c": ["0.001690", "12.5"]
        }}},
        "Depth": {"error": [], "result": {"TELUSD": depth}},
        "Trades": {"error": [], "result": {"TELUSD": [
            ["0.001690", "100", str(now-trade_age), "b", "l", "", 12345]
        ], "last": "12345"}},
        "OHLC": {"error": [], "result": {"TELUSD": candles, "last": "123456"}},
    }


class KrakenSnapshotTests(unittest.TestCase):
    def call_with(self, payloads):
        def fake_get(path, params=None):
            return payloads[path][ "result" ], 1
        with patch.object(km, "_get_json", side_effect=fake_get), patch.object(km.time, "sleep"):
            return km.collect_snapshot()

    def test_valid_snapshot_has_pair_book_trade_and_closed_candle(self):
        result = self.call_with(fixture_payloads())
        self.assertEqual(result["symbol"], "TEL/USD")
        self.assertTrue(result["validation"]["exact_pair"])
        self.assertLess(result["bid"], result["ask"])
        self.assertTrue(result["validation"]["depth_fresh"])
        self.assertTrue(result["validation"]["trade_fresh"])
        self.assertTrue(result["latest_closed_15m_candle"]["close"] > 0)
        self.assertEqual(result["latest_closed_15m_candle"]["open_time_epoch"], 1796999100 if False else result["latest_closed_15m_candle"]["open_time_epoch"])
        self.assertIsNone(result["ticker_timestamp"])
        self.assertFalse(result["ticker_freshness_verified"])

    def test_pair_missing_fails_closed(self):
        with self.assertRaisesRegex(km.KrakenMarketDataError, "missing or ambiguous"):
            self.call_with(fixture_payloads(pair=False))

    def test_unexpected_pair_fails_closed(self):
        with self.assertRaisesRegex(km.KrakenMarketDataError, "not exactly TEL/USD"):
            self.call_with(fixture_payloads(spread_pair="TEL/EUR"))

    def test_network_error_fails_closed(self):
        with patch.object(km, "_get_json", side_effect=km.KrakenMarketDataError("timeout")), patch.object(km.time, "sleep"):
            with self.assertRaisesRegex(km.KrakenMarketDataError, "timeout"):
                km.collect_snapshot()

    def test_zero_price_fails_closed(self):
        p = fixture_payloads()
        p["Ticker"]["result"]["TELUSD"]["a"][0] = "0"
        with self.assertRaisesRegex(km.KrakenMarketDataError, "ticker ask"):
            self.call_with(p)

    def test_crossed_book_fails_closed(self):
        p = fixture_payloads(bid="0.001691", ask="0.001691")
        with self.assertRaisesRegex(km.KrakenMarketDataError, "bid >= ask"):
            self.call_with(p)

    def test_wide_spread_fails_closed(self):
        p = fixture_payloads(bid="0.00160", ask="0.00170")
        with self.assertRaisesRegex(km.KrakenMarketDataError, "spread too wide"):
            self.call_with(p)

    def test_depth_mismatch_fails_closed(self):
        p = fixture_payloads()
        p["Depth"]["result"]["TELUSD"]["bids"][0][0] = "0.001600"
        with self.assertRaisesRegex(km.KrakenMarketDataError, "disagree"):
            self.call_with(p)

    def test_stale_trade_fails_closed(self):
        with self.assertRaisesRegex(km.KrakenMarketDataError, "trade stale"):
            self.call_with(fixture_payloads(trade_age=120))

    def test_stale_depth_fails_closed(self):
        with self.assertRaisesRegex(km.KrakenMarketDataError, "depth timestamp stale"):
            self.call_with(fixture_payloads(depth_age=120))

    def test_malformed_json_result_fails_closed(self):
        p = fixture_payloads()
        p["Ticker"]["result"]["TELUSD"].pop("a")
        with self.assertRaisesRegex(km.KrakenMarketDataError, "incomplete Kraken ticker"):
            self.call_with(p)

    def test_missing_closed_candle_fails_closed(self):
        p = fixture_payloads()
        now = p["Time"]["result"]["unixtime"]
        p["OHLC"]["result"]["TELUSD"] = [[now, "0.00169", "0.00170", "0.00168", "0.00169", "0.00169", "10", 1]]
        with self.assertRaisesRegex(km.KrakenMarketDataError, "not enough Kraken OHLC"):
            self.call_with(p)


if __name__ == "__main__":
    unittest.main()

import unittest
from datetime import datetime, timedelta, timezone

from src.agent_analysis import build_analysis, analyze_timeframe, TIMEFRAMES


def make_rows(count=240, rising=True):
    rows = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 0.001
    for i in range(count):
        price += (0.000001 if rising else -0.000001)
        opened = start + timedelta(minutes=15 * i)
        rows.append({
            "open_time": opened.isoformat().replace("+00:00", "Z"),
            "open": price * 0.999, "high": price * 1.002,
            "low": price * 0.998, "close": price, "volume": 1000 + i,
        })
    return rows


def make_snapshot(now, rising=True):
    rows = make_rows(240, rising)
    # Test fixture uses the same row count per interval; the analyzer only consumes closed rows.
    candles = {}
    for tf in TIMEFRAMES:
        candles[tf] = {
            "status": "OK", "last_closed_at": now.isoformat(),
            "closed_count": len(rows), "rows": rows,
        }
    return {
        "schema_version": 1, "symbol": "TELUSDT",
        "generated_at": now.isoformat(),
        "sources": {"mexc": {"candles": candles}, "kucoin": {}},
        "cross_check": {"independent_confirmation": "OUI"},
    }


class AgentAnalysisTests(unittest.TestCase):
    def test_stale_snapshot_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now - timedelta(minutes=21))
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["orders_sent"], 0)
        self.assertIn("périmé", report["reason"])

    def test_missing_snapshot_fails_closed(self):
        report = build_analysis(None, datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertEqual(report["alignment"], "INDETERMINE")

    def test_valid_snapshot_reports_all_timeframes_without_entry_signal(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        report = build_analysis(make_snapshot(now), now)
        self.assertEqual(set(report["timeframes"]), set(TIMEFRAMES))
        self.assertEqual(report["status"], "SURVEILLER")
        self.assertIn(report["alignment"], {"HAUSSIER_ALIGNE", "MIXTE", "BAISSIER_ALIGNE"})
        self.assertEqual(report["orders_sent"], 0)
        self.assertIn("pas des signaux d'achat", report["interpretation"])

    def test_critical_level_breach_is_reported_as_risk_not_buy_signal(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        report = build_analysis(make_snapshot(now), now)
        self.assertEqual(report["risk_checks"]["critical_level"], 0.001526)
        self.assertEqual(report["risk_checks"]["status"], "SOUS_NIVEAU_SURVEILLANCE")
        self.assertIn("15m", report["risk_checks"]["closed_timeframes_below_level"])
        self.assertEqual(report["orders_sent"], 0)
        self.assertTrue(any(x["flag"].startswith("NIVEAU_CRITIQUE_0_001526") for x in report["flags"]))

    def test_critical_level_above_closes_does_not_flag_breakdown(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        for rows in snapshot["sources"]["mexc"]["candles"].values():
            for row in rows["rows"]:
                for key in ("open", "high", "low", "close"):
                    row[key] += 0.001
        report = build_analysis(snapshot, now)
        self.assertEqual(report["risk_checks"]["status"], "AU_DESSUS_SUR_CLOTURE")
        self.assertEqual(report["risk_checks"]["closed_timeframes_below_level"], [])

    def test_stale_higher_timeframe_candle_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        snapshot["sources"]["mexc"]["candles"]["4h"]["last_closed_at"] = (now - timedelta(hours=5)).isoformat()
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")
        self.assertNotEqual(report["timeframes"]["4h"]["status"], "OK")

    def test_missing_timeframe_fails_closed(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        snapshot["sources"]["mexc"]["candles"].pop("1M")
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "ATTENDRE")

    def test_duplicate_rows_are_rejected(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        rows = snapshot["sources"]["mexc"]["candles"]["4h"]["rows"]
        rows[20] = dict(rows[19])
        result = analyze_timeframe(snapshot["sources"]["mexc"], "4h", now)
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_oversold_flag_is_not_a_reversal_claim(self):
        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now, rising=False)
        report = build_analysis(snapshot, now)
        self.assertEqual(report["status"], "SURVEILLER")
        flags = [flag["flag"] for flag in report["flags"]]
        self.assertIn("RSI_SURVENDU_NE_CONFIRME_PAS_UN_REBOND", flags)


if __name__ == "__main__":
    unittest.main()

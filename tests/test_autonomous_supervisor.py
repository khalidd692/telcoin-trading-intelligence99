import unittest
from datetime import datetime, timezone

from src.autonomous_supervisor import audit_pipeline


NOW = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)


def valid_analysis():
    return {
        "schema_version": 1, "symbol": "TELUSDT", "mode": "READ_ONLY_ANALYSIS",
        "collection_status": "VALID", "generated_at": "2026-10-23T00:59:00Z",
        "source_generated_at": "2026-10-23T00:59:00Z", "collection_id": "same",
        "timeframes": {tf: {"status": "OK"} for tf in ("15m", "1h", "4h", "1d", "1w", "1M")},
    }


def valid_snapshot():
    return {
        "schema_version": 1, "symbol": "TELUSDT", "collection_status": "VALID",
        "generated_at": "2026-10-23T00:59:00Z", "collection_id": "same",
        "sources": {
            "mexc": {"status": {"book": {"verdict": "VÉRIFIÉ"}, "trades": {"verdict": "VÉRIFIÉ"}}},
            "kucoin": {"status": {"book": {"verdict": "VÉRIFIÉ"}, "trades": {"verdict": "VÉRIFIÉ"}}},
        },
    }


class AutonomousSupervisorTests(unittest.TestCase):
    def test_healthy_pipeline_is_reported_without_market_recommendation(self):
        result = audit_pipeline(valid_analysis(), valid_snapshot(),
                                {"action": "AUCUNE_ALERTE"}, now=NOW)
        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["issues"], [])
        self.assertIn("ne constitue pas un signal", result["summary"])
        self.assertEqual(result["safety"]["orders_sent"], 0)
        self.assertFalse(result["safety"]["strategy_modified"])

    def test_stale_analysis_is_critical_and_fail_closed(self):
        analysis = valid_analysis()
        analysis["source_generated_at"] = "2026-10-23T00:20:00Z"
        result = audit_pipeline(analysis, valid_snapshot(), now=NOW)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("ANALYSIS_STALE", {x["code"] for x in result["issues"]})
        self.assertEqual(result["recommended_next_step"], "RECUPERATION_CONTROLEE_PUIS_RECONTROLE")

    def test_collection_mismatch_is_critical(self):
        snapshot = valid_snapshot()
        snapshot["collection_id"] = "other"
        result = audit_pipeline(valid_analysis(), snapshot, now=NOW)
        self.assertIn("COLLECTION_ID_MISMATCH", {x["code"] for x in result["issues"]})
        self.assertEqual(result["status"], "UNAVAILABLE")

    def test_missing_timeframe_degrades_pipeline(self):
        analysis = valid_analysis()
        analysis["timeframes"]["1w"]["status"] = "UNAVAILABLE"
        result = audit_pipeline(analysis, valid_snapshot(), now=NOW)
        self.assertEqual(result["status"], "DEGRADED")
        issue = next(x for x in result["issues"] if x["code"] == "TIMEFRAMES_INCOMPLETE")
        self.assertIn("1w", issue["detail"])

    def test_missing_analysis_never_returns_healthy(self):
        result = audit_pipeline(None, valid_snapshot(), now=NOW, analysis_error="absent")
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["safety"]["market_data_invented"], False)

    def test_unusable_alert_tracking_preserves_alert_state(self):
        result = audit_pipeline(valid_analysis(), valid_snapshot(),
                                {"action": "INDISPONIBLE", "reason": "données invalides"}, now=NOW)
        self.assertEqual(result["status"], "DEGRADED")
        issue = next(x for x in result["issues"] if x["code"] == "ALERT_TRACKING_INDETERMINATE")
        self.assertIn("Préserver l'alerte ouverte", issue["recommended_recovery"])

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            audit_pipeline(valid_analysis(), valid_snapshot(), now=datetime(2026, 10, 23))


if __name__ == "__main__":
    unittest.main()

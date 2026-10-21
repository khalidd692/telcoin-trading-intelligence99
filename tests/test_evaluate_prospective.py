"""
Tests de l'evaluation prospective (scripts/backtest/evaluate_prospective.py).

Verifie notamment la regle la plus importante : **un rendement a 24 h ne doit
jamais etre renseigne avant l'echeance reelle**, et jamais sans serie de prix
couvrant cette echeance.

Les series utilisees ici sont synthetiques et explicitement libellées comme
telles : aucune observation de marche n'est fabriquee.

Stdlib uniquement (contrainte CI : aucun requirements.txt).
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.backtest.evaluate_prospective import (
    COST_ROUND_TRIP,
    evaluate_journal,
    evaluate_row,
    load_series,
    parse_timestamp,
)

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


def make_row(minutes_ago: int, close=0.0015) -> dict:
    stamp = NOW - timedelta(minutes=minutes_ago)
    return {
        "at": stamp.isoformat(),
        "time_ms": stamp.isoformat(),
        "action": "AUCUNE_ALERTE",
        "status": "ATTENDRE",
        "regime": "NEUTRE",
        "direction": "INDETERMINE",
        "confidence": 0,
        "exploitable": False,
        "fees_appliquees": COST_ROUND_TRIP,
        "period_type": "live",
        "returns_24h_bruts": None,
        "returns_24h_net": None,
        "ci95": None,
        "pct_up": None,
        "close_15m": close,
        "snapshot_age_seconds": 0,
        "collection_status": "VALID",
    }


def synthetic_series(points: list[tuple[datetime, float]]) -> list:
    return [(stamp, price) for stamp, price in points]


class TestTimestampParsing(unittest.TestCase):
    def test_iso_forms(self):
        self.assertIsNotNone(parse_timestamp("2026-10-21T12:00:00+00:00"))
        self.assertIsNotNone(parse_timestamp("2026-10-21T12:00:00Z"))
        self.assertIsNone(parse_timestamp("pas une date"))
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))


class TestSeriesLoading(unittest.TestCase):
    def test_jsonl_series(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.jsonl"
            path.write_text(
                json.dumps({"time": "2026-10-20T00:00:00+00:00", "close": 0.0015}) + "\n"
                + json.dumps({"time": "2026-10-21T00:00:00+00:00", "close": 0.0016}) + "\n",
                encoding="utf-8")
            series = load_series(path)
            self.assertEqual(len(series), 2)
            self.assertAlmostEqual(series[1][1], 0.0016)

    def test_invalid_prices_are_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.jsonl"
            path.write_text(
                json.dumps({"time": "2026-10-20T00:00:00+00:00", "close": 0}) + "\n"
                + json.dumps({"time": "2026-10-20T01:00:00+00:00", "close": "abc"}) + "\n"
                + json.dumps({"time": "2026-10-20T02:00:00+00:00", "close": 0.0015}) + "\n",
                encoding="utf-8")
            self.assertEqual(len(load_series(path)), 1)


class TestEvaluationRules(unittest.TestCase):
    def test_no_return_before_the_deadline(self):
        """Regle centrale : rien n'est renseigne avant l'echeance de 24 h."""
        row = make_row(minutes_ago=30, close=0.0015)
        series = synthetic_series([
            (NOW - timedelta(days=2), 0.0014),
            (NOW - timedelta(hours=1), 0.0020),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "ECHEANCE_NON_ATTEINTE")
        self.assertIsNone(result["returns_24h_bruts"])
        self.assertIsNone(result["returns_24h_net"])
        self.assertIsNone(result["pct_up"])
        self.assertIn("evaluation_due_at", result)

    def test_return_computed_once_the_deadline_is_reached(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015)
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([
            (parse_timestamp(row["at"]), 0.0015),
            (deadline, 0.00165),
            (deadline + timedelta(hours=1), 0.0030),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "EVALUEE")
        brut = 0.00165 / 0.0015 - 1.0
        self.assertAlmostEqual(result["returns_24h_bruts"], brut, places=9)
        self.assertAlmostEqual(result["returns_24h_net"], brut - COST_ROUND_TRIP, places=9)
        self.assertTrue(result["pct_up"])

    def test_no_series_means_not_evaluable(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015)
        result = evaluate_row(row, [], NOW)
        self.assertEqual(result["evaluation_status"], "SERIE_INSUFFISANTE")
        self.assertIsNone(result["returns_24h_bruts"])

    def test_missing_entry_price_is_not_evaluable(self):
        row = make_row(minutes_ago=60 * 24 + 10)
        row["close_15m"] = None
        result = evaluate_row(row, [], NOW)
        self.assertEqual(result["evaluation_status"], "PRIX_ENTREE_ABSENT")
        self.assertIsNone(result["returns_24h_bruts"])

    def test_unreadable_timestamp_is_not_evaluable(self):
        row = make_row(minutes_ago=10)
        row["at"] = "pas une date"
        result = evaluate_row(row, [], NOW)
        self.assertEqual(result["evaluation_status"], "HORODATAGE_ILLISIBLE")

    def test_the_journal_is_never_modified(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015)
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([(deadline, 0.0015)])
        before = json.dumps(row, sort_keys=True)
        evaluate_row(row, series, NOW)
        self.assertEqual(json.dumps(row, sort_keys=True), before)


class TestJournalEvaluation(unittest.TestCase):
    def test_summary_separates_evaluated_and_pending(self):
        rows = [make_row(minutes_ago=30), make_row(minutes_ago=60 * 24 + 10)]
        deadline = parse_timestamp(rows[1]["at"]) + timedelta(hours=24)
        series = synthetic_series([(deadline, 0.0015)])
        report = evaluate_journal(rows, series, NOW)
        summary = report["summary"]
        self.assertEqual(summary["observations"], 2)
        self.assertEqual(summary["evaluated"], 1)
        self.assertEqual(summary["pending"], 1)
        self.assertIsNotNone(summary["mean_returns_24h_net"])

    def test_no_observation_due_yields_no_result(self):
        rows = [make_row(minutes_ago=10), make_row(minutes_ago=20)]
        report = evaluate_journal(rows, [], NOW)
        summary = report["summary"]
        self.assertEqual(summary["evaluated"], 0)
        self.assertIsNone(summary["mean_returns_24h_bruts"])
        self.assertIsNone(summary["mean_returns_24h_net"])

    def test_cost_is_the_frozen_protocol_scenario(self):
        self.assertAlmostEqual(COST_ROUND_TRIP, 0.0057, places=6)


if __name__ == "__main__":
    unittest.main()

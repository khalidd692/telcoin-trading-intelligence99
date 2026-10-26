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
    EXIT_STALENESS_SECONDS,
    direction_sign,
    evaluate_journal,
    evaluate_row,
    load_series,
    merge_series,
    parse_timestamp,
    quote_at,
    update_series_store,
)

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


def make_row(minutes_ago: int, close=0.0015, direction="HAUSSIER") -> dict:
    stamp = NOW - timedelta(minutes=minutes_ago)
    return {
        "at": stamp.isoformat(),
        "time_ms": stamp.isoformat(),
        "action": "AUCUNE_ALERTE",
        "status": "ATTENDRE",
        "regime": "NEUTRE",
        "direction": direction,
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


class TestDirection(unittest.TestCase):
    def test_direction_sign_reads_the_published_vocabulary(self):
        self.assertEqual(direction_sign("HAUSSIER"), 1)
        self.assertEqual(direction_sign("BAISSIER"), -1)
        self.assertEqual(direction_sign("INDETERMINE"), 0)
        self.assertEqual(direction_sign(None), 0)
        self.assertEqual(direction_sign("LONG"), 1)
        self.assertEqual(direction_sign("short"), -1)

    def test_bearish_signal_is_scored_as_a_short(self):
        """Un short gagnant ne doit pas etre compte comme une perte."""
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015, direction="BAISSIER")
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([
            (parse_timestamp(row["at"]), 0.0015),
            (deadline, 0.00135),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "EVALUEE")
        expected = (0.0015 - 0.00135) / 0.0015
        self.assertAlmostEqual(result["returns_24h_bruts"], expected, places=9)
        self.assertAlmostEqual(result["returns_24h_net"], expected - COST_ROUND_TRIP, places=9)
        self.assertTrue(result["pct_up"])

    def test_bearish_signal_losing_is_a_loss(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015, direction="BAISSIER")
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([(deadline, 0.00165)])
        result = evaluate_row(row, series, NOW)
        self.assertLess(result["returns_24h_net"], 0)
        self.assertFalse(result["pct_up"])

    def test_indeterminate_direction_is_never_given_a_return(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015, direction="INDETERMINE")
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([(deadline, 0.00165)])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "DIRECTION_INDETERMINEE")
        self.assertIsNone(result["returns_24h_bruts"])
        self.assertIsNone(result["returns_24h_net"])
        self.assertIsNone(result["pct_up"])


class TestExitFreshness(unittest.TestCase):
    def test_stale_exit_price_is_rejected(self):
        """Un prix vieux de plusieurs heures ne peut pas etre le prix a 24 h."""
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015)
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        series = synthetic_series([
            (parse_timestamp(row["at"]), 0.0015),
            (deadline - timedelta(hours=4), 0.00165),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "SERIE_INSUFFISANTE")
        self.assertIn("anterieur", result["evaluation_detail"])
        self.assertIsNone(result["returns_24h_bruts"])

    def test_quote_within_the_tolerance_is_accepted(self):
        when = NOW
        series = synthetic_series([(when - timedelta(seconds=EXIT_STALENESS_SECONDS), 0.0015)])
        self.assertIsNotNone(quote_at(series, when))

    def test_quote_beyond_the_tolerance_is_rejected(self):
        when = NOW
        series = synthetic_series([(when - timedelta(seconds=EXIT_STALENESS_SECONDS + 1), 0.0015)])
        self.assertIsNone(quote_at(series, when))

    def test_a_price_before_the_entry_is_not_an_exit_price(self):
        row = make_row(minutes_ago=60 * 24 + 10, close=0.0015)
        series = synthetic_series([(parse_timestamp(row["at"]), 0.0015)])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "PRIX_SORTIE_ANTERIEUR")
        self.assertIsNone(result["returns_24h_bruts"])


class TestSnapshotSeriesLoading(unittest.TestCase):
    def test_collector_snapshot_shape_is_readable(self):
        snapshot = {
            "schema_version": 1,
            "sources": {
                "mexc": {"candles": {"15m": {"rows": [
                    {"open_time": "2026-10-20T00:00:00Z", "close": 0.0015},
                    {"open_time": "2026-10-20T00:15:00Z", "close": 0.0016},
                ]}}},
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tel_snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            series = load_series(path)
        self.assertEqual(len(series), 2)
        self.assertAlmostEqual(series[1][1], 0.0016)

    def test_mexc_is_preferred_over_other_venues(self):
        snapshot = {
            "sources": {
                "kucoin": {"candles": {"15m": {"rows": [
                    {"open_time": "2026-10-20T00:00:00Z", "close": 9.9},
                ]}}},
                "mexc": {"candles": {"15m": {"rows": [
                    {"open_time": "2026-10-20T00:00:00Z", "close": 0.0015},
                ]}}},
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tel_snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            series = load_series(path)
        self.assertAlmostEqual(series[0][1], 0.0015)

    def test_empty_snapshot_yields_no_fabricated_points(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tel_snapshot.json"
            path.write_text(json.dumps({"sources": {}}), encoding="utf-8")
            self.assertEqual(load_series(path), [])


class TestHorizons(unittest.TestCase):
    def test_each_horizon_is_measured_separately(self):
        row = make_row(minutes_ago=60 * 72 + 10, close=0.0015)
        start = parse_timestamp(row["at"])
        series = synthetic_series([
            (start, 0.0015),
            (start + timedelta(hours=4), 0.00152),
            (start + timedelta(hours=24), 0.00160),
            (start + timedelta(hours=72), 0.00140),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["evaluation_status"], "EVALUEE")
        horizons = result["horizons"]
        self.assertEqual(sorted(horizons), ["24h", "4h", "72h"])
        self.assertTrue(horizons["4h"]["win"])
        self.assertTrue(horizons["24h"]["win"])
        self.assertFalse(horizons["72h"]["win"])
        self.assertEqual(horizons["4h"]["status"], "EVALUEE")

    def test_a_horizon_without_a_fresh_price_stays_unknown(self):
        row = make_row(minutes_ago=60 * 72 + 10, close=0.0015)
        start = parse_timestamp(row["at"])
        series = synthetic_series([
            (start, 0.0015),
            (start + timedelta(hours=72), 0.0016),
        ])
        result = evaluate_row(row, series, NOW)
        self.assertEqual(result["horizons"]["4h"]["status"], "PRIX_SORTIE_ANTERIEUR")
        self.assertEqual(result["horizons"]["24h"]["status"], "PRIX_SORTIE_ANTERIEUR")
        self.assertEqual(result["horizons"]["72h"]["status"], "EVALUEE")


class TestCalibration(unittest.TestCase):
    def _rows(self, *specs):
        rows = []
        for confidence, direction, status in specs:
            row = make_row(minutes_ago=60 * 24 + 10, direction=direction)
            row["confidence"] = confidence
            row["status"] = status
            rows.append(row)
        # Les deux observations partagent la meme echeance : un seul point suffit.
        deadline = parse_timestamp(rows[0]["at"]) + timedelta(hours=24)
        return rows, synthetic_series([(deadline, 0.0016)])

    def test_confidence_buckets_are_reported_not_turned_into_probabilities(self):
        rows, series = self._rows((25, "HAUSSIER", "ALERTE_PRÉCOCE"),
                                  (70, "HAUSSIER", "ALERTE_PRÉCOCE"))
        report = evaluate_journal(rows, series, NOW)
        calibration = report["summary"]["calibration_by_confidence"]
        self.assertEqual(sorted(calibration), ["20-39", "60-79"])
        self.assertEqual(calibration["20-39"]["evaluated"], 1)
        self.assertNotIn("probability", json.dumps(calibration).lower())

    def test_status_and_direction_are_broken_out(self):
        rows, series = self._rows((40, "HAUSSIER", "CONFIRMATION"),
                                  (40, "BAISSIER", "ALERTE_PRÉCOCE"))
        report = evaluate_journal(rows, series, NOW)
        summary = report["summary"]
        self.assertEqual(summary["evaluated"], 2)
        self.assertIn("CONFIRMATION", summary["by_status"])
        self.assertEqual(summary["by_direction"]["BAISSIER"]["evaluated"], 1)
        self.assertEqual(summary["signals_evaluated"], 2)

    def test_non_signal_rows_are_not_counted_as_signals(self):
        row = make_row(minutes_ago=60 * 24 + 10)
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        report = evaluate_journal([row], synthetic_series([(deadline, 0.0016)]), NOW)
        self.assertEqual(report["summary"]["evaluated"], 1)
        self.assertEqual(report["summary"]["signals_evaluated"], 0)

    def test_outcomes_are_broken_down_by_economic_validity(self):
        """La couche économique doit être mesurable, pas décorative."""
        covered, series = self._rows((40, "HAUSSIER", "CONFIRMATION"))
        not_covered = dict(covered[0])
        covered[0]["economic_validity"] = "COUVERT_MINORANT"
        not_covered["economic_validity"] = "NON_COUVERT"
        report = evaluate_journal(covered + [not_covered], series, NOW)
        breakdown = report["summary"]["by_economic_validity"]
        self.assertEqual(sorted(breakdown), ["COUVERT_MINORANT", "NON_COUVERT"])
        self.assertEqual(breakdown["NON_COUVERT"]["evaluated"], 1)

    def test_missing_economic_verdict_is_reported_as_unknown(self):
        row = make_row(minutes_ago=60 * 24 + 10)
        deadline = parse_timestamp(row["at"]) + timedelta(hours=24)
        report = evaluate_journal([row], synthetic_series([(deadline, 0.0016)]), NOW)
        self.assertIn("INCONNUE", report["summary"]["by_economic_validity"])


class TestSeriesStore(unittest.TestCase):
    def test_merge_deduplicates_and_later_values_win(self):
        early = datetime(2026, 10, 20, tzinfo=timezone.utc)
        later = early + timedelta(minutes=15)
        merged = merge_series([(early, 0.0015), (later, 0.0016)],
                              [(later, 0.0017)])
        self.assertEqual(len(merged), 2)
        self.assertAlmostEqual(merged[1][1], 0.0017)

    def test_store_accumulates_across_runs(self):
        first = datetime(2026, 10, 20, tzinfo=timezone.utc)
        second = first + timedelta(minutes=15)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.jsonl"
            update_series_store(path, [(first, 0.0015)])
            merged = update_series_store(path, [(second, 0.0016)])
            self.assertEqual(len(merged), 2)
            reread = load_series(path)
        self.assertEqual(len(reread), 2)
        self.assertAlmostEqual(reread[1][1], 0.0016)

    def test_store_keeps_no_duplicate_for_the_same_timestamp(self):
        stamp = datetime(2026, 10, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.jsonl"
            update_series_store(path, [(stamp, 0.0015)])
            merged = update_series_store(path, [(stamp, 0.0015)])
        self.assertEqual(len(merged), 1)


if __name__ == "__main__":
    unittest.main()

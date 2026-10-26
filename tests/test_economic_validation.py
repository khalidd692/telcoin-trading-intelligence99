"""
Tests de la validation économique (src/economic_validation.py).

Les carnets utilisés ici sont synthétiques et explicitement des fixtures : aucun
prix de marché n'est inventé. Les tests vérifient trois choses :

  1. le coût publié est mesuré sur le carnet, jamais supposé ;
  2. les frais ne sont appliqués que si leur provenance HMAC est valide ;
  3. un objectif qui ne couvre pas le coût n'est jamais présenté comme rentable.
"""

import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from collector.tel_collector import FEES_PROVENANCE_ENV, sign_fees_provenance
from src.economic_validation import (
    DEFAULT_NOTIONAL_USDT,
    measure_round_trip,
    objective_move,
    validate_economics,
)

TEST_KEY = "cle-de-test-uniquement-locale"

#: Carnet synthétique : 705 USDT de profondeur de chaque côté, spread ~0,71 %.
BIDS = [[0.00140, 500000.0]]
ASKS = [[0.00141, 500000.0]]


def signed_fees(pct_per_side=0.1):
    """Enveloppe de frais réellement signée avec la clé de test."""
    raw = {
        "verified": True,
        "pct": pct_per_side,
        "value": f"{pct_per_side}% taker",
        "provenance": {
            "source": "fixture de test",
            "source_url": "https://example.invalid/frais",
            "retrieved_at": "2026-10-20T00:00:00Z",
            "evidence_sha256": "a" * 64,
            "algorithm": "HMAC-SHA256",
            "key_id": "test",
        },
    }
    return sign_fees_provenance(raw, key=TEST_KEY)


def make_source(bids=None, asks=None, spread=None, fees=None, best=None):
    source = {}
    if bids is not None or asks is not None:
        source["book"] = {"bids": bids or [], "asks": asks or []}
    if spread is not None:
        source["spread"] = {"pct_mid": spread, "mid": 0.001405, "absolute": 0.00001}
    if best is not None:
        source["best"] = best
    if fees is not None:
        source["fees"] = fees
    return source


def make_early(direction="HAUSSIER", move=5.0, key="short_term"):
    early = {"direction": direction, "objectives": {}}
    if move is not None:
        early["objectives"][key] = {
            "level": 0.0015, "distance_pct": move, "kind": "niveau structurel de test",
        }
    return early


class TestCostMeasurement(unittest.TestCase):
    def test_cost_is_measured_on_the_observed_book(self):
        source = make_source(BIDS, ASKS, spread=0.7117,
                             best={"bid": 0.00140, "ask": 0.00141})
        block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["status"], "OK")
        cost = block["cost"]
        self.assertEqual(cost["method"], "order_book")
        self.assertTrue(cost["depth_complete"])
        self.assertGreater(cost["round_trip_pct"], 0)
        self.assertLess(cost["round_trip_pct"], 2.0)
        self.assertIsNotNone(cost["slippage_pct"])
        self.assertGreaterEqual(cost["slippage_pct"], 0.0)

    def test_measured_cost_comes_from_the_round_trip_not_from_the_spread(self):
        """Le coût A/R inclut la traversée du carnet, pas seulement le spread."""
        source = make_source(BIDS, ASKS, spread=0.7117,
                             best={"bid": 0.00140, "ask": 0.00141})
        measured = measure_round_trip(source)
        self.assertIsNotNone(measured)
        expected = 1.0 - 0.00140 / 0.00141
        self.assertAlmostEqual(measured["cost_pct"], expected * 100, places=6)

    def test_missing_book_falls_back_to_spread_as_a_declared_lower_bound(self):
        source = make_source(spread=0.85)
        block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["status"], "PARTIEL")
        self.assertEqual(block["cost"]["method"], "spread_only")
        self.assertTrue(block["cost"]["is_lower_bound"])
        self.assertFalse(block["cost"]["depth_complete"])
        self.assertAlmostEqual(block["cost"]["round_trip_pct"], 0.85, places=9)
        self.assertIsNone(block["cost"]["slippage_pct"])

    def test_no_market_data_is_indeterminate_and_says_why(self):
        block = validate_economics(make_early(), {})
        self.assertEqual(block["status"], "INDETERMINE")
        self.assertEqual(block["economic_validity"], "INDETERMINE")
        self.assertIsNone(block["cost"])
        self.assertIn("non mesurable", block["reason"])

    def test_a_full_snapshot_payload_is_accepted(self):
        snapshot = {"sources": {"mexc": make_source(BIDS, ASKS, spread=0.7117)}}
        block = validate_economics(make_early(move=5.0), snapshot)
        self.assertEqual(block["cost"]["method"], "order_book")

    def test_liquidity_cost_is_preferred_when_usable(self):
        source = {
            "liquidity_cost": {
                "usable": True,
                "scenarios": [{
                    "amount_usdt": 300.0,
                    "execution_status": "COMPLET",
                    "initial_spread_pct": 0.70,
                    "round_trip": {"cost_pct": 0.92},
                }],
                "fees": {"verified": False, "pct_per_side": None},
            },
            "book": {"bids": BIDS, "asks": ASKS},
        }
        block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["cost"]["method"], "liquidity_cost")
        self.assertAlmostEqual(block["cost"]["measured_ex_fees_pct"], 0.92, places=9)

    def test_insufficient_depth_is_a_declared_lower_bound_not_a_measured_cost(self):
        source = make_source([[0.00140, 1.0]], [[0.00141, 1.0]], spread=0.7117)
        measured = measure_round_trip(source)
        self.assertIsNotNone(measured)
        self.assertEqual(measured["method"], "spread_only")
        self.assertFalse(measured["depth_complete"])
        self.assertEqual(measured["depth_failure"]["execution_status"],
                         "PROFONDEUR_ACHAT_INSUFFISANTE")


class TestFees(unittest.TestCase):
    def test_unverified_fees_are_never_applied(self):
        source = make_source(BIDS, ASKS, spread=0.7117,
                             fees={"verified": False, "pct": 0.5, "value": None})
        block = validate_economics(make_early(move=5.0), source)
        self.assertIsNone(block["cost"]["fees_pct"])
        self.assertEqual(block["cost"]["fees_status"], "NOT_VERIFIED")
        self.assertTrue(block["cost"]["is_lower_bound"])

    def test_a_fake_verified_flag_is_rejected(self):
        source = make_source(BIDS, ASKS, spread=0.7117,
                             fees={"verified": True, "pct": 0.1, "value": None})
        block = validate_economics(make_early(move=5.0), source)
        self.assertIsNone(block["cost"]["fees_pct"])
        self.assertEqual(block["cost"]["fees_status"], "NOT_VERIFIED")

    def test_signed_fees_are_added_to_the_round_trip(self):
        fees = signed_fees(0.1)
        source = make_source(BIDS, ASKS, spread=0.7117, fees=fees)
        with mock.patch.dict(os.environ, {FEES_PROVENANCE_ENV: TEST_KEY}):
            block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["cost"]["fees_status"], "VERIFIED")
        self.assertAlmostEqual(block["cost"]["fees_pct"], 0.2, places=9)
        self.assertFalse(block["cost"]["is_lower_bound"])
        measured = block["cost"]["measured_ex_fees_pct"]
        self.assertAlmostEqual(block["cost"]["round_trip_pct"], measured + 0.2, places=9)

    def test_a_normalized_fee_block_is_verified_not_trusted(self):
        """Un bloc déjà normalisé doit repasser la vérification HMAC."""
        fees = signed_fees(0.1)
        normalized = {
            "verified": True, "pct_per_side": 0.1, "value": fees["value"],
            "note": "normalisé", "provenance": fees["provenance"],
            "provenance_status": "VERIFIED",
        }
        source = make_source(BIDS, ASKS, spread=0.7117, fees=normalized)
        with mock.patch.dict(os.environ, {FEES_PROVENANCE_ENV: TEST_KEY}):
            block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["cost"]["fees_status"], "VERIFIED")
        self.assertAlmostEqual(block["cost"]["fees_pct"], 0.2, places=9)


class TestCoverage(unittest.TestCase):
    def test_objective_below_cost_is_not_covered(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=0.2), source)
        self.assertEqual(block["economic_validity"], "NON_COUVERT")
        self.assertLess(block["coverage_ratio"], 1.0)
        self.assertLess(block["net_edge_pct"], 0)

    def test_covered_objective_with_unverified_fees_stays_provisional(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["economic_validity"], "COUVERT_MINORANT")
        self.assertGreater(block["coverage_ratio"], 1.0)

    def test_covered_objective_with_verified_fees_is_covered(self):
        fees = signed_fees(0.1)
        source = make_source(BIDS, ASKS, spread=0.7117, fees=fees)
        with mock.patch.dict(os.environ, {FEES_PROVENANCE_ENV: TEST_KEY}):
            block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["economic_validity"], "COUVERT")
        self.assertGreater(block["coverage_ratio"], 1.0)

    def test_an_objective_behind_the_price_is_not_covered(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=-1.2), source)
        self.assertEqual(block["economic_validity"], "NON_COUVERT")
        self.assertIn("derrière le prix", block["reason"])

    def test_indeterminate_direction_has_no_verdict(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(direction="INDETERMINE", move=5.0), source)
        self.assertEqual(block["economic_validity"], "INDETERMINE")
        self.assertIsNotNone(block["cost"])
        self.assertIsNone(block["coverage_ratio"])

    def test_missing_objective_has_no_verdict(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=None), source)
        self.assertEqual(block["economic_validity"], "INDETERMINE")
        self.assertIn("objectif", block["reason"])

    def test_short_term_objective_is_preferred_over_swing(self):
        early = make_early(move=5.0)
        early["objectives"]["swing"] = {"level": 0.0016, "distance_pct": 12.0}
        self.assertEqual(objective_move(early)["source"], "short_term")
        self.assertAlmostEqual(objective_move(early)["move_pct"], 5.0)

    def test_swing_is_used_when_short_term_is_absent(self):
        early = make_early(move=5.0, key="swing")
        self.assertEqual(objective_move(early)["source"], "swing")


class TestHonesty(unittest.TestCase):
    def test_no_probability_is_published(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=5.0), source)
        self.assertNotIn("probability", json.dumps(block).lower())
        self.assertNotIn("probabilite", json.dumps(block).lower())

    def test_default_notional_is_the_collector_reference(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(), source, notional=None)
        self.assertEqual(block["notional_usdt"], DEFAULT_NOTIONAL_USDT)

    def test_limits_are_explicit(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=5.0), source)
        self.assertTrue(any("minorant" in item for item in block["limits"]))
        self.assertTrue(any("non une règle validée" in item for item in block["limits"]))

    def test_no_orders_are_ever_claimed(self):
        source = make_source(BIDS, ASKS, spread=0.7117)
        block = validate_economics(make_early(move=5.0), source)
        self.assertEqual(block["orders_sent"], 0)
        self.assertTrue(block["read_only"])


class TestAgentAnalysisIntegration(unittest.TestCase):
    """Le bloc est joint au rapport sans modifier la décision du détecteur."""

    def _report(self, with_book):
        from tests.test_agent_analysis import make_snapshot
        from src.agent_analysis import build_analysis

        now = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)
        snapshot = make_snapshot(now)
        if with_book:
            snapshot["sources"]["mexc"].update({
                "book": {"bids": BIDS, "asks": ASKS},
                "spread": {"pct_mid": 0.7117, "mid": 0.001405},
                "best": {"bid": 0.00140, "ask": 0.00141},
                "fees": {"verified": False, "pct": None, "value": None},
            })
        return build_analysis(snapshot, now)

    def test_the_block_is_attached_to_the_early_reversal(self):
        report = self._report(with_book=True)
        early = report["early_reversal"]
        self.assertIn("economic_validation", early)
        self.assertEqual(early["economic_validation"]["cost"]["method"], "order_book")

    def test_the_detector_decision_is_unchanged_by_the_economic_layer(self):
        with_book = self._report(with_book=True)["early_reversal"]
        without = self._report(with_book=False)["early_reversal"]
        for key in ("signal_status", "direction", "confidence", "exploitable",
                    "exploitable_reason", "reason"):
            self.assertEqual(with_book[key], without[key], key)
        self.assertNotEqual(with_book["economic_validation"], without["economic_validation"])


if __name__ == "__main__":
    unittest.main()

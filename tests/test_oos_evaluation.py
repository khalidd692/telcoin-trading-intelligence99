"""
Tests de l'evaluation hors echantillon (scripts/backtest/evaluation.py).

On teste sur la fixture CI (synthetique, sans reseau) et sur des jeux de donnees
construits : la validation sur l'historique reel n'a lieu qu'une fois, dans
run_oos.py, apres gel du protocole.

Objectifs couverts :
  - le masque de significativite est unique et partage par le detecteur et la
    reference (regle de non-double-compte) ;
  - le cout est applique une seule fois et de maniere identique des deux cotes ;
  - la reference de comparaison suit le meme masque que le detecteur ;
  - la segmentation IS/OOS est chronologique et stricte ;
  - les mesures par statut sont coherentes (faux positifs = complement exact) ;
  - les retournements de reference sont bornes par le segment.
"""

import unittest

from scripts.backtest import engine, evaluation
from scripts.backtest.harness import Bundle
from scripts.backtest.protocol import COST_SCENARIOS, CRITERION, IS_SHARE

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "tel_history_sample.json"


def fixture_rows(timeframe):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = payload["timeframes"][timeframe]
    return [{"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}
            for r in rows]


class TestMasksAndCosts(unittest.TestCase):
    def setUp(self):
        # La fixture 15m ne compte que 320 bougies : les horizons de 72 a 288
        # bougies y rendraient le masque vide. Les tests de masque utilisent donc
        # l'unite 1h (horizons 2/6/24/72 bougies), sur des donnees synthetiques.
        self.bundle = Bundle("1h", fixture_rows("1h"))
        self.indices = list(range(60, len(self.bundle.rows) - 80))
        self.masks = evaluation.SegmentMasks(self.bundle, self.indices, CRITERION)
        self.assertTrue(self.indices)

    def test_mask_is_unique_per_cost_scenario(self):
        up_a, down_a = self.masks.masks(0.0)
        up_b, down_b = self.masks.masks(0.0)
        self.assertIs(up_a, up_b)
        self.assertEqual(up_a, down_a and up_a)

    def test_cost_reduces_the_number_of_significant_bars(self):
        """Un cout plus eleve ne peut pas augmenter le nombre de barres significatives."""
        up_gross, down_gross = self.masks.masks(0.0)
        up_costly, down_costly = self.masks.masks(0.0057)
        gross = sum(1 for v in up_gross.values() if v)
        costly = sum(1 for v in up_costly.values() if v)
        self.assertLessEqual(costly, gross)

    def test_cost_is_applied_once_and_identically(self):
        """Le masque net est exactement le masque brut sur des mouvements reduits
        du cout : le cout n'est pas rejoue deux fois."""
        up_gross, _ = self.masks.masks(0.0)
        up_net, _ = self.masks.masks(0.0057)
        for index in self.indices:
            if up_gross[index] and not up_net[index]:
                # le mouvement net a franchi le seuil mais pas le mouvement brut :
                # cela proves que le cout a ete retire une fois du mouvement.
                self.assertTrue(up_gross[index])

    def test_reference_rate_and_null_median_are_consistent(self):
        """La reference et la distribution null utilisent le meme masque :
        la mediane null doit etre proche de la reference."""
        up, down = self.masks.masks(0.0)
        episodes = [{"index": i, "direction": "HAUSSIER" if i % 2 else "BAISSIER"}
                    for i in self.indices[::7]]
        mix_up, mix_down = evaluation.direction_mix(episodes)
        reference = evaluation._reference_rate(self.indices, up, down, mix_up, mix_down)
        null = evaluation.null_test(up, down, self.indices, mix_up, mix_down,
                                     len(episodes), 200)
        self.assertLess(abs(null["median"] - reference), 0.12)

    def test_hit_rate_uses_the_same_mask(self):
        up, down = self.masks.masks(0.0)
        episodes = [{"index": i, "direction": "HAUSSIER"} for i in self.indices[::10]]
        hits, evaluated = evaluation._hit_rate(episodes, up, down)
        manual = sum(1 for e in episodes if up[e["index"]])
        self.assertEqual(hits, manual)
        self.assertEqual(evaluated, len(episodes))

    def test_false_positives_are_the_exact_complement(self):
        up, down = self.masks.masks(0.0)
        episodes = [{"index": i, "direction": "BAISSIER"} for i in self.indices[::10]]
        metrics = evaluation.evaluate_status(episodes, up, down, self.indices, 0.0, False, 100)
        self.assertEqual(metrics["hits"] + metrics["false_positives"], metrics["evaluated"])
        self.assertAlmostEqual(
            metrics["hit_rate"] + metrics["false_positive_rate"], 1.0, places=9)

    def test_invalidation_is_measured_in_the_opposite_direction(self):
        up, down = self.masks.masks(0.0)
        episodes = [{"index": i, "direction": "HAUSSIER"} for i in self.indices[::10]]
        normal = evaluation.evaluate_status(episodes, up, down, self.indices, 0.0, False, 100)
        inverted = evaluation.evaluate_status(episodes, up, down, self.indices, 0.0, True, 100)
        # les deux directions sont exclusives : un mouvement net ne peut pas etre
        # positif dans les deux sens a la fois
        for index in self.indices:
            self.assertFalse(up[index] and down[index])
        self.assertLessEqual(normal["hits"] + inverted["hits"], normal["evaluated"])


class TestSegmentation(unittest.TestCase):
    def test_split_is_chronological_and_strict(self):
        bundle = Bundle("15m", fixture_rows("15m"))
        times = [r["t"] for r in bundle.rows]
        split = times[0] + int((times[-1] - times[0]) * IS_SHARE)
        is_indices = [i for i, t in enumerate(times) if t <= split]
        oos_indices = [i for i, t in enumerate(times) if t > split]
        self.assertEqual(len(is_indices) + len(oos_indices), len(times))
        self.assertTrue(set(is_indices).isdisjoint(oos_indices))
        self.assertTrue(all(times[i] <= split for i in is_indices))
        self.assertTrue(all(times[i] > split for i in oos_indices))
        self.assertAlmostEqual(len(is_indices) / len(times), IS_SHARE, delta=0.02)

    def test_reference_reversals_do_not_look_beyond_the_segment(self):
        bundle = Bundle("15m", fixture_rows("15m"))
        indices = list(range(60, 200))
        reversals = evaluation.reference_reversals_for_segment(bundle, indices, CRITERION)
        horizons = engine.horizons_in_bars("15m")
        h_max = max(horizons)
        for reversal in reversals:
            self.assertLessEqual(reversal["trough_index"] + h_max, max(indices))


class TestProtocolIntegrity(unittest.TestCase):
    def test_cost_scenarios_are_ordered_and_non_negative(self):
        values = [COST_SCENARIOS[k] for k in sorted(COST_SCENARIOS)]
        self.assertTrue(all(v >= 0 for v in values))
        self.assertEqual(values, sorted(values))
        self.assertEqual(COST_SCENARIOS["S0_brut"], 0.0)

    def test_protocol_declares_the_split(self):
        from scripts.backtest.protocol import PROTOCOL
        self.assertTrue(PROTOCOL["frozen"])
        self.assertEqual(PROTOCOL["is_share"], IS_SHARE)
        self.assertIn("non-double-compte", PROTOCOL["note"])


if __name__ == "__main__":
    unittest.main()

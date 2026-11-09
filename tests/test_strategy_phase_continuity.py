"""Régressions attendues sur la continuité temporelle du simulateur Kraken 4h.

Ces tests comparent une exécution unique à un découpage artificiel IS/VAL/OOS.
Ils doivent échouer sur le moteur initial tant que run() réinitialise l'état.
Aucune donnée réelle, aucun réseau, aucun ordre.
"""
import datetime as dt
import unittest

from scripts.strategy_backtest import engine as E


T0 = dt.datetime(2026, 1, 1, tzinfo=E.UTC)
COST = E.COSTS["brut"]


def segment(p, high_at=(), low_at=(), n=14):
    highs, lows = set(high_at), set(low_at)
    bars = []
    for i in range(n):
        bars.append(E.Bar(
            T0 + i * E.BAR,
            10.0,
            12.5 if i in highs else 10.0,
            8.0 if i in lows else 10.0,
            10.0,
        ))
    return E.Segment(bars, 0, p)


def candidate(seg, t):
    return E.Candidate(
        t, "A", seg, status="ok",
        entry=seg.bars[t + 1].o, stop=9.0, target=12.0, rr_gross=2.0,
    )


class TestPhaseStateContinuity(unittest.TestCase):
    def test_trade_crossing_phase_blocks_competing_entry(self):
        """Un trade IS ouvert jusqu'en VAL empêche une entrée VAL concurrente."""
        p = E.Params(expiry_bars=5)
        seg = segment(p, high_at=(6,))
        first, second = candidate(seg, 2), candidate(seg, 4)

        continuous, _ = E.run([first, second], p, COST, 0, seg.n)
        phase_is, _ = E.run([first], p, COST, 0, 4)
        phase_val, _ = E.run([second], p, COST, 4, seg.n)

        self.assertEqual(len(continuous), 1)
        self.assertEqual(
            len(phase_is) + len(phase_val), len(continuous),
            "Une position IS traverse la frontière et VAL ouvre un trade concurrent",
        )

    def test_stop_cooldown_survives_phase_boundary(self):
        """Le cooldown d'un stop IS doit aussi s'appliquer aux signaux VAL."""
        p = E.Params(expiry_bars=5, cooldown_after_stop_bars=3)
        seg = segment(p, low_at=(3,))
        first, second = candidate(seg, 2), candidate(seg, 4)

        continuous, _ = E.run([first, second], p, COST, 0, seg.n)
        phase_is, _ = E.run([first], p, COST, 0, 4)
        phase_val, _ = E.run([second], p, COST, 4, seg.n)

        self.assertEqual(len(continuous), 1)
        self.assertEqual(continuous[0].exit_reason, "stop")
        self.assertEqual(
            len(phase_is) + len(phase_val), len(continuous),
            "La frontière de phase a effacé le cooldown après stop",
        )

    def test_equity_is_not_reset_at_phase_boundary(self):
        """Le second trade doit être dimensionné avec l'equity du premier."""
        p = E.Params(expiry_bars=5)
        seg = segment(p, high_at=(2, 6))
        first, second = candidate(seg, 0), candidate(seg, 4)

        continuous, _ = E.run([first, second], p, COST, 0, seg.n)
        phase_is, _ = E.run([first], p, COST, 0, 3)
        phase_val, _ = E.run([second], p, COST, 3, seg.n)

        self.assertEqual(len(continuous), 2)
        self.assertEqual(len(phase_is), 1)
        self.assertEqual(len(phase_val), 1)
        self.assertAlmostEqual(
            phase_val[-1].equity_after, continuous[-1].equity_after,
            places=8,
            msg="Le runner a réinitialisé le capital au début de VAL",
        )


if __name__ == "__main__":
    unittest.main()

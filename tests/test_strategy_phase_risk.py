"""Additional phase-boundary risk regressions; synthetic bars only."""
import unittest
from scripts.strategy_backtest import engine as E
from tests.test_strategy_phase_continuity import segment, candidate


class TestPhaseRisk(unittest.TestCase):
    def test_daily_loss_limit_survives_boundary(self):
        p = E.Params(expiry_bars=3, cooldown_after_stop_bars=0,
                     daily_loss_frac=0.002)
        seg = segment(p, low_at=(1,))
        first, second = candidate(seg, 0), candidate(seg, 1)
        continuous, _ = E.run([first, second], p, E.COSTS['brut'], 0, seg.n)
        phase_is, _ = E.run([first], p, E.COSTS['brut'], 0, 1)
        phase_val, log = E.run([second], p, E.COSTS['brut'], 1, seg.n)
        self.assertEqual(len(continuous), 1)
        self.assertEqual(len(phase_is) + len(phase_val), 1)
        self.assertEqual(log[0]['statut'], 'rejet:perte_quotidienne_max')

    def test_explicit_state_survives_empty_phase_and_segment_change(self):
        p = E.Params(expiry_bars=3)
        seg = segment(p, high_at=(2,))
        later = segment(p, high_at=(6,))
        first, second = candidate(seg, 0), candidate(later, 4)
        expected, _ = E.run([first, second], p, E.COSTS['brut'], 0, seg.n)
        state = E.RunState(p, E.COSTS['brut'])
        a, _ = E.run([first], p, E.COSTS['brut'], 0, 3, state=state)
        E.run([], p, E.COSTS['brut'], 3, 4, state=state)
        b, _ = E.run([second], p, E.COSTS['brut'], 4, seg.n, state=state)
        self.assertEqual(a + b, expected)

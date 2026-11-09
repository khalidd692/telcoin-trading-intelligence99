import datetime as dt, random, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.strategy_backtest import engine as E

T0 = dt.datetime(2026, 1, 1, tzinfo=E.UTC)

def mk(rows, start=T0, skip=None):
    bars, ts = [], start
    for i, (o, h, l, c) in enumerate(rows):
        if skip and i == skip:
            ts += E.BAR
        bars.append(E.Bar(ts, o, h, l, c)); ts += E.BAR
    return bars

def rnd(n, seed):
    r, p, rows = random.Random(seed), 1.0, []
    for _ in range(n):
        o = p; c = o * (1 + r.uniform(-.03, .035)); h = max(o, c) * (1 + r.uniform(0, .015)); l = min(o, c) * (1 - r.uniform(0, .015))
        rows.append((o, h, l, c)); p = c
    return rows

class TestIndicators(unittest.TestCase):
    def test_atr_wilder_manual(self):
        bars = mk([(10, 12, 9, 11), (11, 13, 10, 12), (12, 12.5, 11, 11.5), (11.5, 14, 11, 13)])
        tr = E.true_range(bars)
        self.assertEqual(tr, [3, 3, 1.5, 3])
        a = E.atr_wilder(bars, 3)
        self.assertAlmostEqual(a[2], (3 + 3 + 1.5) / 3)
        self.assertAlmostEqual(a[3], (a[2] * 2 + 3) / 3)
        self.assertIsNone(a[1])

    def test_ema_sma_seed(self):
        e = E.ema([1, 2, 3, 4, 5], 3)
        self.assertAlmostEqual(e[2], 2.0); self.assertAlmostEqual(e[3], 4 * .5 + 2 * .5)

class TestLookahead(unittest.TestCase):
    def test_pivot_known_only_after_five_bars(self):
        rows = [(10, 10.5, 9.5, 10)] * 5 + [(10, 20, 9.5, 10)] + [(10, 10.5, 9.5, 10)] * 5
        bars = mk(rows)
        ph, _ = E.pivots(bars, 5)
        self.assertTrue(ph[5])
        seg = E.Segment(bars, 0, E.Params())
        self.assertIsNone(seg.first_resistance_above(9, 10.0))
        self.assertEqual(seg.first_resistance_above(10, 10.0), (5, 20))

    def test_signals_unchanged_when_future_removed(self):
        for seed in range(5):
            bars = mk(rnd(400, seed))
            p = E.Params()
            full = {c.t: c.branch for c in E.candidates(E.build_segments(bars, p))}
            for cut in (150, 250, 333):
                part = {c.t: c.branch for c in E.candidates(E.build_segments(bars[:cut], p))}
                self.assertEqual(part, {t: b for t, b in full.items() if t < cut}, (seed, cut))

    def test_future_change_does_not_alter_past_signals(self):
        rows = rnd(300, 7); alt = rows[:200] + rnd(100, 99)
        a = {c.t: c.branch for c in E.candidates(E.build_segments(mk(rows), E.Params()))}
        b = {c.t: c.branch for c in E.candidates(E.build_segments(mk(alt), E.Params()))}
        self.assertEqual({t: v for t, v in a.items() if t < 200}, {t: v for t, v in b.items() if t < 200})

def seg_for_exit(rows):
    return E.Segment(mk(rows), 0, E.Params(expiry_bars=3))

class TestExits(unittest.TestCase):
    P = E.Params(expiry_bars=3)
    def test_stop_priority_when_both_touched(self):
        s = seg_for_exit([(10, 10, 10, 10), (10, 13, 8, 10), (10, 10, 10, 10), (10, 10, 10, 10), (10, 10, 10, 10)])
        self.assertEqual(E.simulate_exit(s, 0, 9.0, 12.0, self.P), (1, 9.0, "stop"))

    def test_gap_down_fills_at_open_not_stop(self):
        s = seg_for_exit([(10, 10, 10, 10), (10, 10.5, 9.5, 10), (8, 8.5, 7.5, 8), (8, 8, 8, 8), (8, 8, 8, 8)])
        self.assertEqual(E.simulate_exit(s, 0, 9.0, 12.0, self.P), (2, 8, "stop_gap"))

    def test_gap_up_never_better_than_target(self):
        s = seg_for_exit([(10, 10, 10, 10), (10, 10.5, 9.5, 10), (14, 15, 13, 14), (8, 8, 8, 8), (8, 8, 8, 8)])
        self.assertEqual(E.simulate_exit(s, 0, 9.0, 12.0, self.P), (2, 12.0, "cible"))

    def test_expiry_at_close_of_bar_entry_plus_expiry(self):
        s = seg_for_exit([(10, 10, 10, 10)] + [(10, 10.5, 9.5, 10.2)] * 4)
        self.assertEqual(E.simulate_exit(s, 0, 9.0, 12.0, self.P), (4, 10.2, "expiration"))

    def test_stop_hit_on_entry_bar(self):
        s = seg_for_exit([(10, 10, 10, 10), (10, 10.2, 8.9, 9.5), (9, 9, 9, 9), (9, 9, 9, 9), (9, 9, 9, 9)])
        self.assertEqual(E.simulate_exit(s, 0, 9.0, 12.0, self.P)[2], "stop")

class TestGapsAndSegments(unittest.TestCase):
    def test_segments_split_on_missing_bar(self):
        bars = mk([(1, 1, 1, 1)] * 10, skip=4)
        self.assertEqual(E.split_segments(bars), [(0, 4), (4, 10)])

    def test_indicators_never_cross_gap(self):
        bars = mk(rnd(200, 3), skip=100)
        segs = E.build_segments(bars, E.Params())
        self.assertEqual([s.n for s in segs], [100, 100])
        self.assertTrue(all(s.e_slow[48] is None for s in segs))

    def test_incomplete_window_excluded(self):
        bars = mk(rnd(120, 5)); segs = E.build_segments(bars, E.Params())
        c = E.Candidate(110, "A", segs[0]); E.build_order(c, E.Params())
        self.assertTrue(c.status.startswith("exclu"))

class TestRiskAndCosts(unittest.TestCase):
    def _cand(self, rows, entry_stop_target):
        p = E.Params(expiry_bars=3); seg = E.Segment(mk(rows), 0, p)
        c = E.Candidate(0, "A", seg, "ok", entry=rows[1][0], stop=entry_stop_target[1], target=entry_stop_target[2], rr_gross=2.0)
        return p, c

    def test_loss_at_stop_equals_quarter_percent(self):
        rows = [(10, 10, 10, 10), (10, 10.1, 9.0, 9.5)] + [(9, 9, 9, 9)] * 4
        p, c = self._cand(rows, (10, 9.0, 12.0))
        for cost in E.COSTS.values():
            tr, _ = E.run([c], p, cost, 0, 10)
            self.assertEqual(len(tr), 1)
            self.assertAlmostEqual(tr[0].pnl_usd, -2.5, places=6, msg=cost.name)

    def test_one_position_and_cooldown(self):
        rows = [(10, 10, 10, 10), (10, 10.1, 9.0, 9.5)] + [(9, 9, 9, 9)] * 6
        p, c1 = self._cand(rows, (10, 9.0, 12.0))
        seg = c1.segment
        c2 = E.Candidate(1, "A", seg, "ok", entry=9.0, stop=8.0, target=12.0, rr_gross=3.0)
        c3 = E.Candidate(2, "A", seg, "ok", entry=9.0, stop=8.0, target=12.0, rr_gross=3.0)
        tr, log = E.run([c1, c2, c3], p, E.COSTS["brut"], 0, 10)
        self.assertEqual(len(tr), 2); self.assertEqual([r["statut"] for r in log].count("rejet:position_ouverte_ou_cooldown"), 1)
        self.assertEqual(tr[0].exit_reason, "stop")

    def test_costs_lower_pnl(self):
        rows = [(10, 10, 10, 10), (10, 12.5, 9.9, 12), (12, 12, 12, 12), (12, 12, 12, 12), (12, 12, 12, 12)]
        p, c = self._cand(rows, (10, 9.0, 12.0))
        pn = {k: E.run([c], p, v, 0, 5)[0][0].pnl_usd for k, v in E.COSTS.items()}
        self.assertGreater(pn["brut"], pn["central"]); self.assertGreater(pn["central"], pn["prudent"])

    def test_no_leverage_cap(self):
        rows = [(10, 10, 10, 10), (10, 10.1, 9.99, 10)] + [(10, 10, 10, 10)] * 4
        p, c = self._cand(rows, (10, 9.99, 10.5))
        tr, _ = E.run([c], p, E.COSTS["brut"], 0, 10)
        self.assertLessEqual(tr[0].qty * 10, 1000.0 + 1e-9)

if __name__ == "__main__":
    unittest.main()

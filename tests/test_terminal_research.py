import unittest
from src.terminal import model as M
from scripts.terminal import research as R
from tests.test_terminal_model import dataset, BASE, STEP

class Research(unittest.TestCase):
    def test_signals_ignore_future_bars(self):
        d=dataset(180)
        full=R.signals(d['bars'],'breakout20')
        small=R.signals(d['bars'][:100],'breakout20')
        self.assertEqual([s for s in full if s['index']<100],small)

    def test_breakout_enters_next_open_and_preserves_fixed_target(self):
        rows=dataset(180)['bars'];rows[80].update(c=195,h=196,v=10000)
        signals=R.signals(rows,'breakout20')
        self.assertTrue(any(s['index']==80 for s in signals))
        c=next(c for c in R.orders(rows,'breakout20') if c.t==80)
        self.assertEqual(c.entry,181)
        self.assertAlmostEqual(c.target,c.entry+2*(c.entry-c.stop))

    def test_fold_excludes_position_crossing_boundary(self):
        rows=dataset(180)['bars'];rows[80].update(c=195,h=196,v=10000)
        result=R.evaluate(rows,'breakout20',70,90)
        self.assertEqual(result['costs']['central']['n'],0)
        self.assertGreater(result['boundary_excluded'],0)

    def test_empty_trades_metrics_not_fabricated(self):
        result=R.evaluate(dataset(180)['bars'],'recovery30',90,120)
        r=result['costs']['central']
        self.assertEqual(r['n'],0)
        self.assertIsNone(r['expectancy_R'])
        self.assertIsNone(r['profit_factor'])
        self.assertEqual(r['ending_equity'],1000)

    def test_deterministic_replay(self):
        rows=dataset(180)['bars'];rows[80].update(c=195,h=196,v=10000)
        a=R.evaluate(rows,'breakout20',70,120)
        b=R.evaluate(rows,'breakout20',70,120)
        self.assertEqual(a,b)
        for cost in a['costs'].values():
            for trade in cost['trades']:
                self.assertLessEqual(trade['risk_usd'],2.5)
                self.assertGreaterEqual(trade['rr_gross'],1.51)

class DisplayAdapter(unittest.TestCase):
    def test_legacy_requested_6h_on_4h_is_labeled_effective_4h(self):
        from scripts.terminal.build import event_view
        src={'timeframe':'4h','horizon_hours':6,'n':194}
        view=event_view(src)
        self.assertEqual(view['effective_horizon_hours'],4)
        self.assertEqual(view['horizon_hours'],6)
        self.assertNotIn('effective_horizon_hours',src)

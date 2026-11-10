import datetime as dt
import unittest
from scripts.strategy_backtest import entry_study as S

UTC = dt.timezone.utc


def rows(n=130):
    start = dt.datetime(2026, 1, 1, tzinfo=UTC)
    return [dict(timestamp_utc=start + dt.timedelta(hours=i), open=10., high=12.,
                 low=8., close=11., volume=1.) for i in range(n)]


class TestEntryStudy(unittest.TestCase):
    def test_reference_next_open_and_exact_horizon(self):
        data = rows()
        data[50]['close'] = 100  # signal close must not be the fill reference
        event = S.measure(data, 50, 6)
        self.assertAlmostEqual(event['return'], .1)
        self.assertAlmostEqual(event['mfe'], .2)
        self.assertAlmostEqual(event['mae'], -.2)
        self.assertIsNone(S.measure(data, 126, 6))

    def test_gap_inside_horizon_rejected(self):
        data = rows()
        data[54]['timestamp_utc'] += dt.timedelta(minutes=1)
        self.assertIsNone(S.measure(data, 50, 6))

    def test_signals_do_not_change_with_future(self):
        data = rows(200)
        for i, row in enumerate(data):
            row['close'] = 10 + (i % 17) * .1
        full = S.signals(data)
        partial = S.signals(data[:123])
        for key in full:
            self.assertEqual(full[key][:123], partial[key])
        changed = data[:123] + [{**r, 'close': 1000} for r in data[123:]]
        other = S.signals(changed)
        for key in full:
            self.assertEqual(full[key][:123], other[key][:123])

    def test_nonoverlap_and_phase_boundary(self):
        data = rows()
        masks = {k: [True] * len(data) for k in S.NAMES}
        events, counts = S.collect(data, dt.timedelta(hours=1), 6, masks=masks)
        selected = [e for e in events if e['hypothesis'] == 'divergence']
        self.assertTrue(selected)
        for a, b in zip(selected, selected[1:]):
            self.assertGreater(b['index'], a['index'] + 6)
        for event in selected:
            self.assertEqual(S.phase(event['index'], 130), S.phase(event['index'] + 6, 130))
        self.assertGreater(counts['divergence']['phase_or_tail_excluded'], 0)

    def test_holm_accounts_for_all_comparisons_and_missing_evidence(self):
        self.assertEqual(S.holm([.01, .04, None]), [.03, .08, 1.])

    def test_insufficient_independent_clusters_is_not_significant(self):
        events = [{'excess': .2, 'cluster': 'one'}] * 40
        self.assertIsNone(S.bootstrap(events)['p'])

    def test_bootstrap_is_repeatable_and_detects_zero_effect(self):
        events = [{'excess': 0., 'cluster': str(i // 3)} for i in range(30)]
        result = S.bootstrap(events)
        self.assertEqual(result, S.bootstrap(events))
        self.assertEqual(result['ci95'], [0., 0.])
        self.assertEqual(result['p'], 1.)

    def test_positive_effect_has_nonzero_power_and_finite_correction(self):
        events = [{'excess': .2, 'cluster': str(i // 3)} for i in range(30)]
        result = S.bootstrap(events)
        self.assertEqual(result['p'], .001)
        self.assertAlmostEqual(result['ci95'][0], .2)
        self.assertAlmostEqual(result['ci95'][1], .2)

    def test_existing_oversold_component_is_detected_without_rr(self):
        data = rows(70)
        for i, row in enumerate(data):
            row['close'] = 100-i
        masks = S.signals(data)
        self.assertFalse(any(masks['oversold'][:49]))
        self.assertTrue(masks['oversold'][-1])

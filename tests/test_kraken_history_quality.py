"""Offline validation of Kraken history and simulator temporal boundaries."""
import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from scripts.strategy_backtest import engine as E
from scripts.strategy_backtest import history_quality as Q

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, tzinfo=UTC)


class TestHistoryQuality(unittest.TestCase):
    def validate(self, rows, timeframe='1h'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bars.csv'
            with path.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(Q.COLUMNS)
                writer.writerows(rows)
            return Q.validate_csv(path, timeframe, as_of=NOW)

    def row(self, hour, **changes):
        row = dict(zip(Q.COLUMNS, [f'2026-11-09T{hour:02}:00:00Z', 10, 11, 9, 10, 1]))
        row.update(changes)
        return [row[k] for k in Q.COLUMNS]

    def test_quarantine_wick_and_nonfinite_or_inconsistent_ohlc(self):
        rows = [self.row(0), self.row(1, high=50), self.row(2, low=12),
                self.row(3, close='nan'), self.row(4, volume=-1), self.row(5)]
        result = self.validate(rows)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len(result.quarantine), 4)
        self.assertEqual(result.report['gap_count'], 1)
        self.assertEqual(result.report['missing_bars'], 4)

    def test_all_duplicate_copies_excluded_even_when_conflicting(self):
        result = self.validate([self.row(0), self.row(1), self.row(1, close=10.5), self.row(2)])
        self.assertEqual(len(result.rows), 2)
        self.assertTrue(all('duplicate_timestamp' in q['reasons'] for q in result.quarantine))

    def test_utc_alignment_order_and_closed_candles(self):
        rows = [self.row(0, timestamp_utc='2026-11-08T22:00:00'),
                self.row(0, timestamp_utc='2026-11-08T23:00:00+01:00'),
                self.row(0), self.row(2), self.row(1),
                self.row(3, timestamp_utc='2026-11-09T03:01:00Z'),
                self.row(23), self.row(0, timestamp_utc='2026-11-10T00:00:00Z')]
        result = self.validate(rows)
        self.assertEqual([r['timestamp_utc'].hour for r in result.rows], [0, 23])
        reasons = {r for q in result.quarantine for r in q['reasons']}
        self.assertTrue({'timestamp_not_utc', 'out_of_order', 'misaligned_timestamp', 'unclosed'} <= reasons)

    def test_dataset_provenance_hash_and_final_bar_exclusion(self):
        for tf, path in Q.CANONICAL.items():
            result = Q.load_history(path, as_of=NOW)
            self.assertEqual(result.report['provenance']['market'], 'KRAKEN:TELUSD')
            self.assertEqual(result.report['timeframe'], tf)
            self.assertTrue(any('unclosed' in q['reasons'] for q in result.quarantine))
            if tf in ('1h', '4h'):
                self.assertTrue(any('price_wick' in q['reasons'] and float(q['row']['high']) == .02
                                    for q in result.quarantine))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'KRAKEN_TELUSD.csv'
            path.write_text('timestamp_utc,open,high,low,close,volume\n')
            with self.assertRaises(ValueError):
                Q.load_history(path, as_of=NOW)
        source = Q.ROOT / Q.CANONICAL['4h']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tampered.csv'
            path.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'hash'):
                Q.validate_csv(path, '4h', as_of=NOW,
                               provenance=Q.manifest()[Q.CANONICAL['4h']])

    def test_engine_uses_validated_four_hour_input_only(self):
        result = Q.load_history(Q.CANONICAL['4h'], as_of=NOW)
        bars = E.load_csv(Q.CANONICAL['4h'])
        self.assertEqual(len(bars), len(result.rows))
        self.assertLess(max(b.h for b in bars), .02)
        with self.assertRaisesRegex(ValueError, '4h'):
            E.load_csv(Q.CANONICAL['1h'])

    def test_indicators_signals_and_trade_horizon_never_cross_quarantine(self):
        # A quarantined middle candle must restart EMA and exclude entry windows.
        rows = [self.row(i) for i in range(12)]
        rows[5] = self.row(5, high=50)
        result = self.validate(rows, '1h')
        # Use the same timestamps scaled to the existing 4h strategy interval.
        bars = [E.Bar(dt.datetime(2026, 1, 1, tzinfo=UTC) + 4 * dt.timedelta(hours=r['timestamp_utc'].hour),
                      r['open'], r['high'], r['low'], r['close']) for r in result.rows]
        p = E.Params(ema_fast=3, ema_slow=4, atr_n=3, pivot=1, expiry_bars=3)
        segments = E.build_segments(bars, p)
        self.assertEqual([s.n for s in segments], [5, 6])
        self.assertIsNone(segments[1].e_fast[0])
        self.assertIsNone(segments[1].signal(0))
        c = E.Candidate(2, 'A', segments[0])
        self.assertTrue(E.build_order(c, p).status.startswith('exclu:'))
        with self.assertRaises(ValueError):
            E.simulate_exit(segments[0], 2, 9, 12, p)
        with self.assertRaises(ValueError):
            E.Segment(bars, 0, p)
        self.assertEqual(E.build_segments([], p), [])
        incomplete = E.Candidate(4, 'A', segments[0], status='ok',
                                 entry=10, stop=9, target=12, rr_gross=2)
        trades, log = E.run([incomplete], p, E.COSTS['brut'], 0, 5)
        self.assertEqual(trades, [])
        self.assertTrue(log[0]['statut'].startswith('exclu:'))

    def test_extreme_consecutive_close_jump_is_quarantined(self):
        result = self.validate([self.row(0), self.row(1, open=40, high=41, low=39, close=40)])
        self.assertEqual(len(result.rows), 1)
        self.assertIn('price_jump', result.quarantine[0]['reasons'])

    def test_exported_csv_is_accepted_by_existing_engine_and_hash_checked(self):
        history = Q.load_history(Q.CANONICAL['4h'], as_of=NOW)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '4h_valid.csv'
            Q.write_valid_csv(history, path)
            self.assertEqual(len(E.load_csv(path)), len(history.rows))
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'hash'):
                E.load_csv(path)

    def test_real_snapshot_counts_are_reproducible(self):
        expected = {'15m': (5590, 801, 1116, 1), '1h': (6796, 166, 193, 2),
                    '4h': (1746, 1, 1, 2)}
        for tf, path in Q.CANONICAL.items():
            report = Q.load_history(path, as_of=NOW).report
            self.assertEqual(tuple(report[k] for k in ('valid_bars', 'gap_count', 'missing_bars',
                                                       'quarantined_rows')), expected[tf])

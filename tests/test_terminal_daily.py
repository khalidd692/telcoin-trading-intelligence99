import math
import unittest

from scripts.terminal.daily import correlations, rsi_setups


DAY = 86400


def daily(returns, symbol='TEL', missing=()):
    prices = [1.0]
    for value in returns:
        prices.append(prices[-1] * math.exp(value))
    bars = [{'t': i * DAY, 'c': p} for i, p in enumerate(prices) if i not in missing]
    return {'symbol': 'KRAKEN:' + symbol + 'USD', 'bars': bars,
            'quality': {'last_close': bars[-1]['t'] + DAY, 'invalid_tail': False}}


class DailyStudies(unittest.TestCase):
    def test_three_assets_use_same_thirty_returns(self):
        values = [((i % 7) - 3) / 100 for i in range(34)]
        tel = daily(values)
        btc = daily([2 * x for x in values], 'XBT')
        eth = daily([-x for x in values], 'ETH')
        result = correlations(tel, btc, eth, 35 * DAY)
        self.assertEqual(result['n'], 30)
        self.assertEqual(result['last_close'], 35 * DAY)
        self.assertEqual(result['first_return_close'], 6 * DAY)
        for actual, expected in zip(result['matrix'][0], [1, 1, -1]):
            self.assertAlmostEqual(actual, expected)

    def test_gap_missing_asset_and_old_coverage(self):
        values = [0.01] * 34
        tel = daily(values)
        btc = daily(values, 'XBT')
        eth = daily(values, 'ETH', missing=(10,))
        result = correlations(tel, btc, eth, 36 * DAY)
        self.assertEqual(result['n'], 28)
        self.assertIsNone(result['matrix'])
        self.assertFalse(result['fresh'])
        self.assertEqual(correlations(tel, btc, None, 35 * DAY)['n'], 0)

    def test_zero_variance_and_bad_tail(self):
        frames = [daily([0] * 30, symbol) for symbol in ('TEL', 'XBT', 'ETH')]
        self.assertIsNone(correlations(*frames, 31 * DAY)['matrix'][0][0])
        frames[2]['quality']['invalid_tail'] = True
        self.assertFalse(correlations(*frames, 31 * DAY)['fresh'])

    def test_only_crossings_and_complete_forward_windows_count(self):
        frame = daily([0.01] * 14 + [-0.35, -0.1] + [0.04] * 15 + [-1.1])
        rows = frame['bars']
        result = rsi_setups(frame)
        self.assertEqual(result['n'], 1)
        self.assertEqual(result['pending'], 1)
        first = result['events'][0]
        i = first['signal_close'] // DAY - 1
        self.assertEqual(first['outcome_close'] - first['signal_close'], 5 * DAY)
        self.assertAlmostEqual(first['return_pct'], (rows[i + 5]['c'] / rows[i]['c'] - 1) * 100)
        self.assertEqual(result['successes'], 1)
        frame['bars'] = [row for row in rows if row['t'] != (i + 2) * DAY]
        broken = rsi_setups(frame)
        self.assertEqual(broken['n'], 0)
        self.assertEqual(broken['gapped'], 1)

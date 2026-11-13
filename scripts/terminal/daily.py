"""Descriptive studies on validated Kraken daily candles."""
import math
from statistics import fmean, median

from src.terminal.model import STEPS, rsi_wilder_series

DAY = STEPS['1D']
SYMBOLS = ('TEL/USD', 'BTC/USD', 'ETH/USD')
CORRELATION_WINDOW = 30
SETUP_HORIZON = 5


def correlations(tel, btc, eth, as_of):
    frames = (tel, btc, eth)
    closes = [
        {row['t'] + DAY: row['c'] for row in frame['bars'] if row['t'] + DAY <= as_of}
        if frame else {} for frame in frames
    ]
    last_by_symbol = {symbol: max(prices, default=None) for symbol, prices in zip(SYMBOLS, closes)}
    latest_common = max(closes[0].keys() & closes[1].keys() & closes[2].keys(), default=None)
    aligned = [] if latest_common is None else [
        t for t in range(latest_common - (CORRELATION_WINDOW - 1) * DAY, latest_common + DAY, DAY)
        if all(t in prices and t - DAY in prices for prices in closes)
    ]
    matrix = None
    if len(aligned) == CORRELATION_WINDOW:
        returns = [[math.log(prices[t] / prices[t - DAY]) for t in aligned] for prices in closes]
        centered = [[value - fmean(values) for value in values] for values in returns]
        norms = [math.sqrt(sum(value ** 2 for value in values)) for values in centered]
        matrix = [
            [max(-1, min(1, sum(a * b for a, b in zip(x, y)) / (nx * ny))) if nx and ny else None
             for y, ny in zip(centered, norms)]
            for x, nx in zip(centered, norms)
        ]
    expected_close = int(as_of) // DAY * DAY
    return {
        'version': 'pearson-log-1d-v1', 'symbols': SYMBOLS, 'window': CORRELATION_WINDOW,
        'n': len(aligned), 'matrix': matrix, 'last_close': aligned[-1] if aligned else None,
        'first_return_close': aligned[0] if aligned else None, 'last_by_symbol': last_by_symbol,
        'fresh': bool(aligned and aligned[-1] == expected_close and all(
            frame and not frame['quality']['invalid_tail'] for frame in frames)),
    }


def rsi_setups(frame):
    bars = frame['bars']
    last = bars[-1]['t'] if bars else 0
    prices = {row['t']: row['c'] for row in bars}
    times = list(range(bars[0]['t'], last + DAY, DAY)) if bars else []
    closes = [prices.get(t) for t in times]
    rsi = rsi_wilder_series(closes)
    events = []
    pending = gapped = 0
    for i in range(1, len(times)):
        if not rsi[i - 1] >= 30 > rsi[i]:
            continue
        outcome = i + SETUP_HORIZON
        if any(p is None for p in closes[i + 1:outcome + 1]):
            gapped += 1
        elif outcome >= len(times):
            pending += 1
        else:
            events.append({
                'signal_close': times[i] + DAY,
                'outcome_close': times[outcome] + DAY,
                'rsi14': rsi[i],
                'return_pct': (closes[outcome] / closes[i] - 1) * 100,
                'success': closes[outcome] > closes[i],
            })
    returns = [event['return_pct'] for event in events]
    successes = sum(event['success'] for event in events)
    return {
        'version': 'rsi14-wilder-cross-under-30-1d-plus5-v1',
        'horizon_bars': SETUP_HORIZON, 'n': len(events), 'successes': successes,
        'success_pct': 100 * successes / len(events) if events else None,
        'median_return_pct': median(returns) if returns else None,
        'pending': pending, 'gapped': gapped, 'events': events,
        'first_close': times[0] + DAY if times else None,
        'last_close': last + DAY if bars else None,
    }

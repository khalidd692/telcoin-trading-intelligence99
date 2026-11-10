"""Small offline event study of existing TEL hypotheses, never an order engine."""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import json
import math
import random
import statistics as stats
from collections import Counter, defaultdict
from pathlib import Path

from src import agent_analysis as A
from scripts.strategy_backtest import history_quality as Q

NAMES = ('divergence', 'oversold', 'pullback')
PROTOCOL = Q.ROOT / 'research/ENTRY_STUDY_PROTOCOL.json'


def signals(rows):
    closes = [r['close'] for r in rows]
    rsi = A.rsi_series(closes, 14)
    fast, slow = A.ema_series(closes, 20), A.ema_series(closes, 50)
    result = {name: [False] * len(rows) for name in NAMES}
    for i in range(49, len(rows)):
        r = rows[i]
        # Only the ten trailing observations are needed by the existing detector.
        result['divergence'][i] = A.has_rsi_divergence(rsi[i-9:i+1], closes[i-9:i+1])
        result['oversold'][i] = rsi[i] < 30 and closes[i] < slow[i]
        result['pullback'][i] = (fast[i] > slow[i] and closes[i] > slow[i]
                                 and r['low'] <= fast[i] and closes[i] > r['open']
                                 and closes[i] > fast[i])
    return result


def phase(i, n):
    return 'IS_exposed' if i < int(.6*n) else ('VAL_exposed' if i < int(.8*n) else 'OOS_exposed')


def measure(rows, i, h):
    if i < 0 or h < 1 or i + h >= len(rows):
        return None
    step = rows[i+1]['timestamp_utc'] - rows[i]['timestamp_utc']
    if step not in Q.INTERVALS.values():
        return None
    if any(rows[j]['timestamp_utc'] - rows[j-1]['timestamp_utc'] != step
           for j in range(i+1, i+h+1)):
        return None
    future = rows[i+1:i+h+1]
    entry = future[0]['open']
    return {'return': future[-1]['close']/entry-1,
            'mfe': max(r['high'] for r in future)/entry-1,
            'mae': min(r['low'] for r in future)/entry-1}


def collect(rows, step, hours, *, offset=0, total=None, segment=0, masks=None):
    total = total or len(rows)
    h = int(dt.timedelta(hours=hours)/step)
    masks = masks if masks is not None else signals(rows)
    fast, slow = A.ema_series([r['close'] for r in rows], 20), A.ema_series([r['close'] for r in rows], 50)
    eligible, baselines = {}, defaultdict(list)
    for i in range(49, len(rows)):
        if phase(offset+i, total) != phase(offset+i+h, total):
            continue
        value = measure(rows, i, h)
        if value is None:
            continue
        key = (phase(offset+i, total), fast[i] > slow[i])
        eligible[i] = (value, key)
        baselines[key].append(value['return'])
    baseline_mean = {k: stats.mean(v) for k, v in baselines.items()}
    events, counts = [], {}
    for name in NAMES:
        count = Counter(raw_signals=0, phase_or_tail_excluded=0, overlap_excluded=0, evaluated=0)
        last = -h-1
        for i in range(49, len(rows)):
            if not masks[name][i]:
                continue
            count['raw_signals'] += 1
            if i not in eligible:
                count['phase_or_tail_excluded'] += 1
                continue
            if i <= last+h:
                count['overlap_excluded'] += 1
                continue
            last = i
            count['evaluated'] += 1
            value, key = eligible[i]
            iso = rows[i]['timestamp_utc'].isocalendar()
            events.append({'hypothesis': name, 'horizon_hours': hours, 'segment': segment,
                           'index': offset+i, 'phase': key[0], 'trend_up': key[1],
                           'signal_close_utc': (rows[i]['timestamp_utc']+step).isoformat(),
                           'reference_open_utc': rows[i+1]['timestamp_utc'].isoformat(),
                           'outcome_close_utc': (rows[i+h]['timestamp_utc']+step).isoformat(),
                           **value, 'baseline': baseline_mean[key],
                           'baseline_n': len(baselines[key]),
                           'excess': value['return']-baseline_mean[key],
                           'cluster': f'{iso.year}-{iso.week}'})
        counts[name] = dict(count)
    return events, counts


def bootstrap(events):
    clusters = defaultdict(list)
    for event in events:
        clusters[event['cluster']].append(event['excess'])
    result = {'clusters': len(clusters), 'ci95': None, 'p': None}
    if len(clusters) < 10 or len(events) < 30:
        return result
    groups = [(sum(v), len(v)) for v in clusters.values()]
    observed = stats.mean(e['excess'] for e in events)
    rng = random.Random(99)
    draws = []
    for _ in range(999):
        sample = rng.choices(groups, k=len(groups))
        draws.append(sum(x for x, n in sample)/sum(n for x, n in sample))
    ordered = sorted(draws)
    result.update(ci95=[ordered[24], ordered[974]],
                  p=(1+sum(d-observed >= observed for d in draws))/1000)
    return result


def holm(values):
    order = sorted(range(len(values)), key=lambda i: values[i] if values[i] is not None else 1.)
    adjusted, previous = [1.]*len(values), 0.
    for rank, index in enumerate(order):
        previous = min(1., max(previous, (len(values)-rank)*(values[index] if values[index] is not None else 1.)))
        adjusted[index] = previous
    return adjusted


def summary(events):
    if not events:
        return {'n': 0}
    return {'n': len(events), 'mean_return_pct': 100*stats.mean(e['return'] for e in events),
            'median_return_pct': 100*stats.median(e['return'] for e in events),
            'mean_mfe_pct': 100*stats.mean(e['mfe'] for e in events),
            'mean_mae_pct': 100*stats.mean(e['mae'] for e in events),
            'mean_excess_pct': 100*stats.mean(e['excess'] for e in events),
            'positive_fraction': stats.mean(e['return'] > 0 for e in events)}


def main():
    protocol = json.loads(PROTOCOL.read_text())
    out = Q.ROOT / 'results/entry_research'
    out.mkdir(parents=True, exist_ok=True)
    report = {'implementation_sha256': {str(p.relative_to(Q.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Q.ROOT/'src/agent_analysis.py', Q.ROOT/'scripts/strategy_backtest/history_quality.py')}, 'protocol_sha256': hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
              'protocol': protocol, 'datasets': {}, 'comparisons': [], 'startup_sensitivity': {}}
    journal = []
    for tf, path in Q.CANONICAL.items():
        history = Q.load_history(path, as_of=dt.datetime(2026, 11, 10, tzinfo=Q.UTC))
        rows = history.rows
        step = Q.INTERVALS[tf]
        pieces, start = [], 0
        for i in range(1, len(rows)):
            if rows[i]['timestamp_utc'] - rows[i-1]['timestamp_utc'] != step:
                pieces.append((start, rows[start:i])); start = i
        if rows:
            pieces.append((start, rows[start:]))
        report['datasets'][tf] = history.report
        masks = [signals(piece) for offset, piece in pieces]
        longest = max((piece for offset, piece in pieces), key=len)
        sensitivity = []
        for window in (100, 200, 400):
            if len(longest) < window:
                continue
            full, short = signals(longest), signals(longest[-window:])
            entry = {'window': window, 'last_signal_changed': {name: full[name][-1] != short[name][-1] for name in NAMES}}
            closes = [r['close'] for r in longest]
            entry['ema50_last_relative_difference_pct'] = 100*(A.ema_series(closes[-window:],50)[-1]/A.ema_series(closes,50)[-1]-1)
            sensitivity.append(entry)
        report['startup_sensitivity'][tf] = sensitivity
        for hours in protocol['horizons_hours']:
            events, counts = [], {name: Counter() for name in NAMES}
            for segment, ((offset, piece), mask) in enumerate(zip(pieces, masks)):
                batch, tally = collect(piece, step, hours, offset=offset, total=len(rows), segment=segment, masks=mask)
                events.extend(batch)
                for name in NAMES:
                    counts[name].update(tally[name])
            for name in NAMES:
                selected = [e for e in events if e['hypothesis'] == name]
                report['comparisons'].append({'timeframe': tf, 'hypothesis': name, 'horizon_hours': hours,
                    'counts': dict(counts[name]), **summary(selected), 'inference': bootstrap(selected),
                    'phases': {ph: summary([e for e in selected if e['phase'] == ph])
                               for ph in ('IS_exposed','VAL_exposed','OOS_exposed')}})
            journal.extend({'timeframe': tf, **event} for event in events)
    comparisons = report['comparisons']
    adjusted = holm([c['inference']['p'] for c in comparisons])
    for c, p in zip(comparisons, adjusted):
        c['inference']['holm_p'] = p
        c['statistical_lead_only'] = p < .05 and c.get('mean_excess_pct',0) > 0
    report['conclusion'] = 'AUCUNE STRATEGIE VALIDEE; historical holdout exposed; gross event study only'
    (out/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    with (out/'events.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(journal[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(journal)
    for c in comparisons:
        if c['horizon_hours'] == 24:
            print({k: c.get(k) for k in ('timeframe','hypothesis','n','mean_return_pct','mean_excess_pct','statistical_lead_only')})


if __name__ == '__main__':
    main()

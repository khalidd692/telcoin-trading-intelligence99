"""Offline Kraken TEL/USD history validation; no fetching, filling or interpolation.

Price checks are quarantine heuristics, not claims that a market print was false.
Raw exports remain immutable; all exclusions retain their source line and values.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'research/data/kraken_manifest.json'
COLUMNS = ('timestamp_utc', 'open', 'high', 'low', 'close', 'volume')
INTERVALS = {'15m': dt.timedelta(minutes=15), '1h': dt.timedelta(hours=1),
             '4h': dt.timedelta(hours=4)}
CANONICAL = {
    '15m': 'research/data/KRAKEN_TELUSD_15m_tradingview_5591_bars_2026-11-09.csv',
    '1h': 'research/data/KRAKEN_TELUSD_1h_tradingview_6798_bars_2026-11-09.csv',
    '4h': 'research/data/KRAKEN_TELUSD_4h_tradingview_1748_bars_2026-11-09.csv',
}
PRICE_RATIO = 3.0


def manifest():
    return json.loads(MANIFEST.read_text())


def utc_timestamp(value):
    stamp = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0):
        raise ValueError('timestamp_not_utc')
    return stamp.astimezone(UTC)


@dataclass
class History:
    rows: list
    quarantine: list
    report: dict


def coverage(rows, step):
    """Continuous intervals use an exclusive close boundary; no missing bars made."""
    if not rows:
        return [], []
    periods, gaps = [], []
    start = previous = rows[0]['timestamp_utc']
    count = 1
    for row in rows[1:]:
        stamp = row['timestamp_utc']
        if stamp - previous != step:
            periods.append({'start_utc': start.isoformat(),
                            'end_exclusive_utc': (previous + step).isoformat(), 'bars': count})
            gaps.append({'start_utc': (previous + step).isoformat(),
                         'end_exclusive_utc': stamp.isoformat(),
                         'missing_bars': max(0, int((stamp - previous) / step) - 1)})
            start, count = stamp, 0
        count += 1
        previous = stamp
    periods.append({'start_utc': start.isoformat(),
                    'end_exclusive_utc': (previous + step).isoformat(), 'bars': count})
    return periods, gaps


def validate_csv(path, timeframe, *, as_of, provenance=None):
    """Validate values and chronology. Provenance, when supplied, is hash pinned.

    Both copies of duplicate timestamps and both sides of an inversion are
    quarantined. Extreme wicks/body ratios or consecutive close jumps >3x are
    suspicious and require source review, never automatic price correction.
    """
    path = Path(path)
    step = INTERVALS[timeframe]
    if as_of.tzinfo is None or as_of.utcoffset() != dt.timedelta(0):
        raise ValueError('as_of must be UTC')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    cutoff = as_of
    if provenance is not None:
        if provenance.get('market') != 'KRAKEN:TELUSD' or provenance.get('timeframe') != timeframe:
            raise ValueError('Kraken TEL/USD provenance/timeframe mismatch')
        if digest != provenance.get('sha256'):
            raise ValueError('Provenance hash mismatch')
        cutoff = min(cutoff, utc_timestamp(provenance['closed_before']))
    records = []
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError('Unexpected OHLCV CSV schema')
        for line, raw in enumerate(reader, 2):
            reasons, parsed = [], {}
            try:
                stamp = utc_timestamp(raw['timestamp_utc'])
                parsed['timestamp_utc'] = stamp
                if stamp.timestamp() % step.total_seconds():
                    reasons.append('misaligned_timestamp')
                if stamp + step > cutoff:
                    reasons.append('unclosed')
            except (ValueError, TypeError, AttributeError) as exc:
                reasons.append('timestamp_not_utc' if str(exc) == 'timestamp_not_utc' else 'invalid_timestamp')
            try:
                parsed.update({k: float(raw[k]) for k in COLUMNS[1:]})
                if not all(math.isfinite(parsed[k]) for k in COLUMNS[1:]):
                    reasons.append('nonfinite_value')
                elif (min(parsed[k] for k in ('open', 'high', 'low', 'close')) <= 0
                      or parsed['volume'] < 0):
                    reasons.append('nonpositive_price_or_negative_volume')
                elif not (parsed['low'] <= min(parsed['open'], parsed['close'])
                          <= max(parsed['open'], parsed['close']) <= parsed['high']):
                    reasons.append('inconsistent_ohlc')
                elif (parsed['high'] / max(parsed['open'], parsed['close']) > PRICE_RATIO
                      or min(parsed['open'], parsed['close']) / parsed['low'] > PRICE_RATIO):
                    reasons.append('price_wick')
            except (ValueError, TypeError, KeyError):
                reasons.append('invalid_numeric_value')
            records.append({'line': line, 'row': raw, 'parsed': parsed, 'reasons': reasons})
    by_time = {}
    previous = None
    previous_price = None
    for record in records:
        stamp = record['parsed'].get('timestamp_utc')
        if stamp is not None:
            by_time.setdefault(stamp, []).append(record)
            if previous is not None and stamp < previous['parsed']['timestamp_utc']:
                previous['reasons'].append('out_of_order')
                record['reasons'].append('out_of_order')
            previous = record
        close = record['parsed'].get('close', 0)
        if math.isfinite(close) and close > 0:
            if (previous_price is not None and stamp is not None
                    and stamp - previous_price[0] == step
                    and max(close / previous_price[1], previous_price[1] / close) > PRICE_RATIO):
                record['reasons'].append('price_jump')
            previous_price = (stamp, close) if stamp is not None else None
        else:
            previous_price = None
    for copies in by_time.values():
        if len(copies) > 1:
            for record in copies:
                record['reasons'].append('duplicate_timestamp')
    rows, quarantine = [], []
    for record in records:
        if record['reasons']:
            quarantine.append({k: record[k] for k in ('line', 'row', 'reasons')})
        else:
            rows.append(record['parsed'])
    periods, gaps = coverage(rows, step)
    raw_times = [{'timestamp_utc': stamp} for stamp in sorted(by_time)
                 if stamp.timestamp() % step.total_seconds() == 0]
    _, source_gaps = coverage(raw_times, step)
    report = {'timeframe': timeframe, 'sha256': digest,
              'provenance': provenance, 'as_of_utc': as_of.isoformat(),
              'closed_before_utc': cutoff.isoformat(), 'price_ratio_quarantine_threshold': PRICE_RATIO,
              'source_rows': len(records), 'valid_bars': len(rows),
              'quarantined_rows': len(quarantine),
              'reasons': dict(Counter(reason for q in quarantine for reason in set(q['reasons']))),
              'source_gap_count': len(source_gaps),
              'source_missing_bars': sum(g['missing_bars'] for g in source_gaps),
              'gap_count': len(gaps), 'missing_bars': sum(g['missing_bars'] for g in gaps),
              'gaps': gaps, 'usable_periods': periods}
    return History(rows, quarantine, report)


def load_history(path, *, as_of=None):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    catalog = manifest()
    try:
        key = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        key = None
    provenance = catalog.get(key)
    if provenance is None:
        sidecar = path.with_suffix('.provenance.json')
        if not sidecar.is_file():
            raise ValueError('Unregistered history: Kraken provenance required')
        provenance = json.loads(sidecar.read_text())
        source = catalog.get(provenance.get('derived_from'))
        if (source is None or provenance.get('source_sha256') != source['sha256']
                or provenance.get('market') != source['market']
                or provenance.get('timeframe') != source['timeframe']
                or provenance.get('source_commit') != source['source_commit']
                or utc_timestamp(provenance['closed_before']) > utc_timestamp(source['closed_before'])):
            raise ValueError('Derived CSV provenance does not match registered Kraken source')
    return validate_csv(path, provenance['timeframe'], as_of=as_of or dt.datetime.now(UTC),
                        provenance=provenance)


def write_valid_csv(history, path):
    """Export only validated observations, with hash-pinned source lineage."""
    path = Path(path)
    source = history.report['provenance']
    if source is None:
        raise ValueError('Export requires registered Kraken provenance')
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        for row in history.rows:
            writer.writerow({**row, 'timestamp_utc': row['timestamp_utc'].isoformat()})
    provenance = {**source, 'derived_from': source.get('derived_from', source['source_path']),
                  'source_sha256': source.get('source_sha256', source['sha256']),
                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'closed_before': history.report['closed_before_utc']}
    path.with_suffix('.provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', default=None, help='UTC cutoff; default: current UTC')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/kraken_history')
    args = parser.parse_args()
    as_of = utc_timestamp(args.as_of) if args.as_of else dt.datetime.now(UTC)
    args.output.mkdir(parents=True, exist_ok=True)
    reports = {}
    for tf, path in CANONICAL.items():
        history = load_history(path, as_of=as_of)
        reports[tf] = history.report
        (args.output / f'{tf}_quarantine.json').write_text(json.dumps(history.quarantine, indent=2) + '\n')
        write_valid_csv(history, args.output / f'{tf}_valid.csv')
        r = history.report
        print(f"{tf}: source={r['source_rows']} valid={r['valid_bars']} quarantined={r['quarantined_rows']} "
              f"gaps={r['gap_count']} missing={r['missing_bars']} segments={len(r['usable_periods'])}")
    (args.output / 'report.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    main()

"""Versioned, descriptive close-to-close evaluation; never generates signals."""
import math
from statistics import median

VERSION = 'tel99-rebounds-v1'
STEP = 900
HORIZON = 86400
ATTRIBUTION = 3600
THRESHOLDS = (2, 3, 5, 10)


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def evaluate(candles, events, start_at, now, observations=()):
    """Evaluate mature, fully observed windows; missing data is never a miss."""
    prices = {}
    for row in candles:
        t, p = row.get('close_at'), row.get('close')
        if number(t) and t % STEP == 0 and t <= now and number(p) and p > 0:
            if t in prices and prices[t] != p:
                raise ValueError('conflicting candle')
            prices[t] = p
    alerts = {}
    for event in events:
        if event.get('type') != 'EARLY_ALERT' or not isinstance(event.get('id'), str):
            continue
        t = event.get('observed_at')
        if number(t) and t <= now:
            if event['id'] not in alerts or t < alerts[event['id']]['observed_at']:
                alerts[event['id']] = event
    coverage = set()
    for row in observations:
        try:
            observed, close_at = float(row['observed_at']), float(row['price_at'])
        except (KeyError, ValueError, TypeError):
            continue
        if row.get('radar_covered') is True and close_at % STEP == 0 and close_at <= observed <= close_at + STEP:
            coverage.add((int(close_at), observed))
    output = {}
    for percent in THRESHOLDS:
        detected = missed = unknown = late = 0
        leads, delays = [], []
        skip_until = -1
        for start in sorted(prices):
            if start < start_at or start <= skip_until or start + HORIZON > now:
                continue
            future = list(range(start + STEP, start + HORIZON + STEP, STEP))
            if any(t not in prices for t in future):
                continue
            crossing = next((t for t in future if prices[t] >= prices[start] * (1+percent/100) - 1e-12*prices[start]), None)
            if crossing is None:
                continue
            skip_until = start + HORIZON
            timely = [e for e in alerts.values() if start-ATTRIBUTION <= e['observed_at'] <= start]
            late_alerts = [e for e in alerts.values() if start < e['observed_at'] <= crossing]
            if timely:
                detected += 1
                leads.append((start-max(e['observed_at'] for e in timely))/60)
            elif all(any(c == t and seen <= start for c,seen in coverage) for t in range(start-ATTRIBUTION,start,STEP)):
                missed += 1
            else:
                unknown += 1
            if late_alerts:
                late += 1
                delays.append((min(e['observed_at'] for e in late_alerts)-start)/60)
        total = detected + missed + unknown
        output[str(percent)] = {'episodes':total,'detected':detected,'missed':missed,'unknown':unknown,
          'detection_fraction_known':detected/(detected+missed) if detected+missed else None,
          'late_alerts':late,'median_lead_minutes':median(leads) if leads else None,
          'median_late_minutes':median(delays) if delays else None}
    false_count = evaluable = pending = unknown = 0
    for event in alerts.values():
        t, p = event['observed_at'], event.get('price')
        if t < start_at:
            continue
        if not number(p) or p <= 0:
            unknown += 1
            continue
        if t + HORIZON > now:
            pending += 1
            continue
        first = (int(t)//STEP+1)*STEP
        last = int((t+HORIZON)//STEP)*STEP
        times = range(first,last+STEP,STEP)
        if any(x not in prices for x in times):
            unknown += 1
            continue
        evaluable += 1
        if not any(prices[x] >= p*1.05-1e-12*p for x in times):
            false_count += 1
    return {'version':VERSION,'start_at':start_at,'thresholds':output,
      'false_positives':{'count':false_count,'evaluable':evaluable,'pending':pending,'unknown':unknown,
                         'definition':'Alerte précoce sans clôture +5% en 24 h; variation de prix, pas résultat de trade.'}}

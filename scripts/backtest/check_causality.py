#!/usr/bin/env python3
"""
Controle de causalite sur l'historique REEL (protocole OOS, section 5).

Pour un echantillon de barres reparties sur l'historique :
  1. le detecteur est calcule sur la serie tronquee a la barre i ;
  2. toutes les barres posterieures a i sont perturbees (facteur aleatoire) ;
  3. le detecteur est recalcule sur la serie tronquee a i, avec la perturbation ;
  4. les deux sorties doivent etre STRICTEMENT identiques.

Cela prouve qu'un signal emis en i n'utilise aucune information posterieure a i,
donc qu'il est exploitable au moment ou il est emis.

Usage : python scripts/backtest/check_causality.py [--sample 150]
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402

VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL
TIMEFRAMES = ["15m", "1h", "4h", "1d"]


def perturb(rows, index, seed):
    rng = random.Random(seed)
    out = [dict(r) for r in rows]
    for row in out[index + 1:]:
        factor = rng.uniform(0.4, 2.5)
        for field in ("o", "h", "l", "c"):
            row[field] = round(row[field] * factor, 12)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=150)
    args = parser.parse_args()

    failures = 0
    checked = 0
    for tf in TIMEFRAMES:
        rows = store.load_timeframe(VENUE, SYMBOL, tf)
        if len(rows) < 400:
            continue
        bundle = Bundle(tf, rows)
        other_bundles = {}
        indexes = {}
        for other in TIMEFRAMES:
            other_rows = store.load_timeframe(VENUE, SYMBOL, other)
            if not other_rows:
                continue
            other_bundles[other] = Bundle(other, other_rows)
            indexes[other] = engine.TimeframeIndex(other_bundles[other])
        step = max(1, (len(rows) - 400) // args.sample)
        positions = list(range(300, len(rows) - 300, step))[:args.sample]

        for position in positions:
            now = store.close_time_ms(rows[position], tf)
            timeframes = {}
            for other, other_bundle in other_bundles.items():
                k = indexes[other].index_at(now)
                timeframes[other] = fast_timeframe_state(other_bundle, k, now) if k is not None else {
                    "status": "UNAVAILABLE", "reason": "aucune bougie", "candle_count": 0,
                    "trend": "INDETERMINE"}
            series = detection_state(bundle, position)
            reference = call_detector(timeframes, series)

            perturbed_rows = perturb(rows, position, seed=position)
            perturbed_bundle = Bundle(tf, perturbed_rows)
            perturbed_series = detection_state(perturbed_bundle, position)
            after = call_detector(timeframes, perturbed_series)

            checked += 1
            if reference["signal_status"] != after["signal_status"] \
                    or reference["direction"] != after["direction"] \
                    or [e["type"] for e in reference["evidence"]] != [e["type"] for e in after["evidence"]]:
                failures += 1
                print(f"  DIVERGENCE {tf}@{position} : "
                      f"{reference['signal_status']} -> {after['signal_status']}")
        print(f"  {tf:4s} : {len(positions)} positions verifiees")

    print()
    print(f"positions verifiees : {checked} | divergences : {failures}")
    print("CAUSALITE VERIFIEE SUR DONNEES REELLES" if failures == 0 else "CAUSALITE COMPROMISE")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

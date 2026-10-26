#!/usr/bin/env python3
"""
Analyse de discrimination des combinaisons de preuves — segment de CONCEPTION (IS) UNIQUEMENT.

Le segment de validation (OOS) a deja ete consulte pour comparer les deux
moteurs : il ne peut donc PLUS servir a regler quoi que ce soit. Cet outil
travaille exclusivement sur la partie de conception, par construction.

Pour chaque combinaison de familles de preuves, il affiche l'effectif, le taux de
reussite, la reference de comparaison du segment et l'ecart.

Usage : python scripts/backtest/analyse_families.py [--timeframe 15m] [--criterion quantile]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, evaluation, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402
from scripts.backtest.protocol import CRITERION  # noqa: E402

VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]

# Date absolue de coupure IS/OOS, identique a run_oos.py (SEGMENT_DATES["OOS"][0]).
# Une coupure en pourcentage se deplacerait si l'historique est prolonge.
SPLIT_DATE = "2026-04-16"


def pct(value):
    return "n/a" if value is None else f"{value * 100:.2f}%"


def num(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--criterion", default=CRITERION)
    parser.add_argument("--segment", default="IS", choices=["IS", "IS1", "IS2"],
                        help="IS = tout le segment de conception ; IS1 = sa premiere moitie "
                             "(zone de conception d'une regle) ; IS2 = sa seconde moitie "
                             "(zone de validation, a ne pas consulter pendant la conception)")
    args = parser.parse_args()
    target = args.timeframe

    rows = store.load_timeframe(VENUE, SYMBOL, target)
    bundle = Bundle(target, rows)
    times = [store.close_time_ms(r, target) for r in rows]
    # Date absolue de coupure (identique a run_oos.py) : une coupure en pourcentage
    # se deplacerait si l'historique est prolonge.
    split = int(datetime.fromisoformat(SPLIT_DATE + "+00:00").timestamp() * 1000)
    is_indices = [i for i, t in enumerate(times) if t <= split]
    if args.segment == "IS1":
        is_indices = is_indices[:len(is_indices) // 2]
    elif args.segment == "IS2":
        is_indices = is_indices[len(is_indices) // 2:]
    print(f"cible {target} · segment {args.segment} : {len(is_indices)} barres")

    others = {}
    for tf in ALL_TFS:
        if tf == target:
            continue
        r = store.load_timeframe(VENUE, SYMBOL, tf)
        if r:
            others[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in others.items()}

    signals = []
    for i in is_indices:
        t_ms = times[i]
        timeframes = {target: fast_timeframe_state(bundle, i, t_ms)}
        for tf, other in others.items():
            k = indexes[tf].index_at(t_ms)
            timeframes[tf] = fast_timeframe_state(other, k, t_ms) if k is not None else {
                "status": "UNAVAILABLE", "reason": "aucune bougie", "candle_count": 0,
                "trend": "INDETERMINE"}
        detection = call_detector(timeframes, detection_state(bundle, i))
        if detection["signal_status"] in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"):
            signals.append({
                "index": i, "time_ms": t_ms, "status": detection["signal_status"],
                "direction": detection["direction"], "confidence": detection["confidence"],
                "families": detection.get("families", []),
                "setup": detection.get("setup"),
                "evidence": [e.get("type") for e in detection.get("evidence", [])],
                "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                "reason": detection.get("reason"), "price": bundle.closes[i],
            })
    episodes = engine.group_episodes(signals)
    print(f"signaux={len(signals)} episodes={len(episodes)}")

    masks = evaluation.SegmentMasks(bundle, is_indices, args.criterion)
    up, down = masks.masks(0.0)

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for episode in episodes:
        buckets[tuple(sorted(episode.get("families", [])))].append(episode)

    print()
    print(f"{'familles':40s} {'n':>6} {'taux':>9} {'ref':>9} {'ecart':>7} {'fp':>6} {'null_pct':>9}")
    rows_out = []
    for key, group in buckets.items():
        hits, evaluated = evaluation._hit_rate(group, up, down)
        rate = hits / evaluated if evaluated else None
        mix_up, mix_down = evaluation.direction_mix(group)
        reference = evaluation._reference_rate(is_indices, up, down, mix_up, mix_down)
        lift = (rate / reference) if (rate is not None and reference) else None
        null = evaluation.null_test(up, down, is_indices, mix_up, mix_down,
                                    max(evaluated, 1), 2000)
        if rate is not None and null["rates"]:
            percentile = sum(1 for v in null["rates"] if v <= rate) / len(null["rates"])
        else:
            percentile = None
        rows_out.append((key, evaluated, rate, reference, lift, evaluated - hits, percentile))
    for key, evaluated, rate, reference, lift, fp, percentile in sorted(rows_out, key=lambda r: (-(r[4] or 0))):
        print(f"{str(key):40s} {evaluated:>6} {pct(rate):>9} {pct(reference):>9} {num(lift):>7} "
              f"{fp:>6} {num(percentile, 3):>9}")

    mix = evaluation.direction_mix(episodes)
    print()
    print(f"reference globale du segment (IS) : "
          f"{pct(evaluation._reference_rate(is_indices, up, down, mix[0], mix[1]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

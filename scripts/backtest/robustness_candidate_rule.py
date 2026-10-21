"""
Robustesse de la regle candidate R1 (CONFIRMATION + regime 1d neutre).

Verifie :
  - la stabilite de la bande de regime (5 % vs 8 %) sur tous les segments ;
  - l'estimation POOLEE sur les segments non utilises pour la conception
    (NEW vierge + IS2 validation) ;
  - le cout d'equilibre (round trip maximum encore rentable) ;
  - la persistance a l'horizon 72 h ;
  - la reduction du volume de signaux (faux positifs) ;
  - le profil gains/pertes.

Usage : python scripts/backtest/robustness_candidate_rule.py
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402

VENUE, TEL = "kucoin", "TEL-USDT"
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
ROUND_TRIP_OBSERVED = 0.0057
OUT = Path(__file__).resolve().parent.parent.parent / "oos_rule_robustness.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def bootstrap_ci(values, iterations=5000, seed=4242):
    values = [v for v in values if v is not None]
    if len(values) < 20:
        return (None, None)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iterations):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    return (means[int(0.025 * (len(means) - 1))], means[int(0.975 * (len(means) - 1))])


def main() -> int:
    tel_rows = store.load_timeframe(VENUE, TEL, "15m")
    tel = Bundle("15m", tel_rows)
    times = [store.close_time_ms(r, "15m") for r in tel_rows]
    closes = tel.closes
    n = len(closes)

    def ms_of(text):
        return int(datetime.fromisoformat(text + "+00:00").timestamp() * 1000)

    boundaries = {
        "NEW": (times[0], ms_of("2025-07-09")),
        "IS1": (ms_of("2025-07-09"), ms_of("2025-11-27")),
        "IS2": (ms_of("2025-11-27"), ms_of("2026-04-16")),
        "OOS": (ms_of("2026-04-16"), times[-1] + 1),
    }
    others = {}
    for tf in ALL_TFS:
        if tf == "15m":
            continue
        r = store.load_timeframe(VENUE, TEL, tf)
        if r:
            others[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in others.items()}
    daily = store.load_timeframe(VENUE, TEL, "1d")
    daily_closes = [r["c"] for r in daily]
    daily_times = [store.close_time_ms(r, "1d") for r in daily]

    signals = []
    for i in range(n):
        t = times[i]
        tfm = {"15m": fast_timeframe_state(tel, i, t)}
        for tf, b in others.items():
            k = indexes[tf].index_at(t)
            tfm[tf] = fast_timeframe_state(b, k, t) if k is not None else {
                "status": "UNAVAILABLE", "reason": "x", "candle_count": 0, "trend": "INDETERMINE"}
        detection = call_detector(tfm, detection_state(tel, i))
        if detection["signal_status"] in ("ALERTE_PRÉCOCE", "CONFIRMATION"):
            signals.append({
                "index": i, "time_ms": t, "status": detection["signal_status"],
                "direction": detection["direction"], "confidence": detection.get("confidence", 0),
                "families": detection.get("families", []), "setup": detection.get("setup"),
                "evidence": [e.get("type") for e in detection.get("evidence", [])],
                "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                "reason": detection.get("reason", ""), "price": closes[i],
            })
    episodes = engine.group_episodes(signals)

    for episode in episodes:
        i = episode["index"]
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        pos = None
        for k in range(len(daily_times) - 1, -1, -1):
            if daily_times[k] <= episode["time_ms"]:
                pos = k
                break
        episode["regime"] = ((daily_closes[pos] - daily_closes[pos - 30]) / daily_closes[pos - 30]
                             if pos is not None and pos >= 30 else None)
        episode["returns"] = {h: (sign * (closes[i + h] - closes[i]) / closes[i])
                              if (sign and i + h < n) else None for h in (96, 288)}

    def segment_of(episode):
        for name, (start, end) in boundaries.items():
            if start <= episode["time_ms"] < end:
                return name
        return None

    def rule_group(band, status, segments=None):
        return [e for e in episodes
                if e["status"] == status and e["regime"] is not None and abs(e["regime"]) < band
                and (segments is None or segment_of(e) in segments)]

    payload = {"round_trip_observed": ROUND_TRIP_OBSERVED, "segments": {}}

    print("=== 1. Stabilite de la bande de regime (CONFIRMATION) ===")
    for band in (0.05, 0.08):
        line = f"  bande {band * 100:>4.0f} % :"
        for seg in ("NEW", "IS1", "IS2", "OOS"):
            group = rule_group(band, "CONFIRMATION", [seg])
            r24 = [e["returns"][96] for e in group if e["returns"][96] is not None]
            line += (f"  {seg} n={len(r24):>3} esp={mean(r24) * 100:+.2f}%"
                     if r24 else f"  {seg} n=0")
        print(line)
        payload.setdefault("bands", {})[str(band)] = {
            seg: {"n": len([e for e in rule_group(band, "CONFIRMATION", [seg])
                            if e["returns"][96] is not None]),
                  "expectancy": mean([e["returns"][96] for e in rule_group(band, "CONFIRMATION", [seg])])}
            for seg in ("NEW", "IS1", "IS2", "OOS")}

    print()
    print("=== 2. Estimation POOLEE sur les segments NON utilises pour la conception (NEW + IS2) ===")
    pooled = rule_group(0.05, "CONFIRMATION", ["NEW", "IS2"])
    r24 = [e["returns"][96] for e in pooled if e["returns"][96] is not None]
    low, high = bootstrap_ci(r24)
    print(f"  n={len(r24)} esperance={mean(r24) * 100:+.3f}% IC95=[{low * 100:+.3f},{high * 100:+.3f}] "
          f"| nette apres {ROUND_TRIP_OBSERVED * 100:.2f} % = {(mean(r24) - ROUND_TRIP_OBSERVED) * 100:+.3f}%")
    print(f"  part en hausse={100 * sum(1 for v in r24 if v > 0) / len(r24):.1f}% "
          f"| pire={min(r24) * 100:+.2f}% | meilleur={max(r24) * 100:+.2f}%")
    gains = [v for v in r24 if v > 0]
    losses = [v for v in r24 if v <= 0]
    print(f"  gains n={len(gains)} moyenne={mean(gains) * 100:+.3f}% | "
          f"pertes n={len(losses)} moyenne={mean(losses) * 100:+.3f}% | "
          f"ratio={mean(gains) / abs(mean(losses)):.2f}")
    payload["pooled_new_is2"] = {"n": len(r24), "expectancy": mean(r24), "ci95": [low, high],
                                  "net": mean(r24) - ROUND_TRIP_OBSERVED,
                                  "pct_up": 100 * sum(1 for v in r24 if v > 0) / len(r24),
                                  "worst": min(r24), "best": max(r24),
                                  "mean_gain": mean(gains), "mean_loss": mean(losses)}

    print()
    print("=== 3. Cout d'equilibre (round trip maximum encore rentable) ===")
    for seg in ("NEW", "IS1", "IS2", "OOS"):
        group = rule_group(0.05, "CONFIRMATION", [seg])
        r = [e["returns"][96] for e in group if e["returns"][96] is not None]
        if r:
            print(f"  {seg:4s} : rentabilite jusqu'a un round trip de {mean(r) * 100:.2f} % "
                  f"(observe {ROUND_TRIP_OBSERVED * 100:.2f} %)")

    print()
    print("=== 4. Horizon 72 h ===")
    for seg in ("NEW", "IS1", "IS2", "OOS"):
        group = rule_group(0.05, "CONFIRMATION", [seg])
        r = [e["returns"][288] for e in group if e["returns"][288] is not None]
        if r:
            print(f"  {seg:4s} : n={len(r):>3} esp72={mean(r) * 100:+.3f}% "
                  f"| nette apres {ROUND_TRIP_OBSERVED * 100:.2f} % = {(mean(r) - ROUND_TRIP_OBSERVED) * 100:+.3f}%")

    print()
    print("=== 5. Reduction de volume (faux positifs ecartes) ===")
    for seg in ("NEW", "IS1", "IS2", "OOS"):
        total = len([e for e in episodes if segment_of(e) == seg and e["status"] == "CONFIRMATION"])
        kept = len(rule_group(0.05, "CONFIRMATION", [seg]))
        total_a = len([e for e in episodes if segment_of(e) == seg and e["status"] == "ALERTE_PRÉCOCE"])
        kept_a = len([e for e in episodes if segment_of(e) == seg and e["status"] == "ALERTE_PRÉCOCE"
                      and e["regime"] is not None and abs(e["regime"]) < 0.05])
        print(f"  {seg:4s} : CONFIRMATION {kept}/{total} retenus ({100 * kept / total if total else 0:.0f} %) "
              f"| ALERTE {kept_a}/{total_a} ({100 * kept_a / total_a if total_a else 0:.0f} %)")

    print()
    print("=== 6. Le regime neutre : combien de temps passe-t-il le marche ? ===")
    for seg, (start, end) in boundaries.items():
        idxs = [i for i, t in enumerate(times) if start <= t < end]
        pos_map = {}
        counts = {"neutre": 0, "tendance": 0}
        for i in idxs[::37]:
            pos = None
            for k in range(len(daily_times) - 1, -1, -1):
                if daily_times[k] <= times[i]:
                    pos = k
                    break
            if pos is None or pos < 30:
                continue
            trend = (daily_closes[pos] - daily_closes[pos - 30]) / daily_closes[pos - 30]
            counts["neutre" if abs(trend) < 0.05 else "tendance"] += 1
        total = counts["neutre"] + counts["tendance"]
        print(f"  {seg:4s} : neutre {100 * counts['neutre'] / total:.0f} % du temps | "
              f"en tendance {100 * counts['tendance'] / total:.0f} %")

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

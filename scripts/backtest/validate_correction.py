"""
Validation de la correction : le moteur v2 (avec regime + exploitable) doit
reproduire EXACTEMENT l'esperance validee hors echantillon.

Comparaison attendue (issue de validate_candidate_rule.py, avant modification
du moteur) :
  CONFIRMATION + regime neutre, esperance 24 h brute :
    NEW +0,682 % | IS1 +1,910 % | IS2 +1,796 % | OOS +0,792 %

Usage : python scripts/backtest/validate_correction.py
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
EXPECTED = {"NEW": 0.00682, "IS1": 0.01910, "IS2": 0.01796, "OOS": 0.00792}
ROUND_TRIP = 0.0057
OUT = Path(__file__).resolve().parent.parent.parent / "oos_correction_validation.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def bootstrap_ci(values, iterations=5000, seed=31337):
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
                "exploitable": detection.get("exploitable", False),
                "regime": detection.get("regime", {}),
            })
    episodes = engine.group_episodes(signals)

    def segment_of(episode):
        for name, (start, end) in boundaries.items():
            if start <= episode["time_ms"] < end:
                return name
        return None

    def returns(episode, horizon=96):
        i = episode["index"]
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        if not sign or i + horizon >= n:
            return None
        return sign * (closes[i + horizon] - closes[i]) / closes[i]

    payload = {"expected_before_correction": EXPECTED, "round_trip": ROUND_TRIP, "segments": {}}
    print("=== Reproduction de l'esperance validee, par le moteur CORRIGE ===")
    for seg in ("NEW", "IS1", "IS2", "OOS"):
        group = [e for e in episodes if segment_of(e) == seg and e.get("exploitable")]
        r24 = [v for v in (returns(e) for e in group) if v is not None]
        r288 = [v for v in (returns(e, 288) for e in group) if v is not None]
        low, high = bootstrap_ci(r24)
        got = mean(r24) if r24 else None
        expected = EXPECTED[seg]
        delta = (got - expected) if (got is not None and expected is not None) else None
        print(f"  {seg:4s} : n={len(r24):>4} esp24={got * 100:+.3f}% (attendu {expected * 100:+.3f}%, "
              f"ecart {delta * 100:+.4f} pt) IC95=[{low * 100:+.3f},{high * 100:+.3f}] "
              f"| nette={(got - ROUND_TRIP) * 100:+.3f}% | esp72={mean(r288) * 100:+.3f}%")
        payload["segments"][seg] = {
            "n": len(r24), "expectancy_24h": got, "expected": expected, "delta": delta,
            "ci95": [low, high], "net": (got - ROUND_TRIP) if got is not None else None,
            "expectancy_72h": mean(r288),
        }

    print()
    print("=== Controles de coherence ===")
    max_delta = max(abs(v["delta"]) for v in payload["segments"].values() if v["delta"] is not None)
    # les valeurs attendues sont arrondies a 3 decimales en pourcentage
    exact = max_delta < 5e-5
    print(f"  ecart maximal entre avant/apres correction : {max_delta * 100:.5f} point(s) "
          f"-> {'REPRODUCTION EXACTE' if exact else 'DIVERGENCE A EXPLIQUER'}")

    # volumetrie : combien de signaux restent exploitables
    print()
    print("=== Volumetrie exploitable ===")
    for seg in ("NEW", "IS1", "IS2", "OOS"):
        total = len([e for e in episodes if segment_of(e) == seg])
        explo = len([e for e in episodes if segment_of(e) == seg and e.get("exploitable")])
        print(f"  {seg:4s} : {explo}/{total} signaux exploitables "
              f"({100 * explo / total if total else 0:.1f} %)")

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Validation d'une regle candidate, pre-enregistree sur le segment de CONCEPTION (IS1).

Regle candidate (concue sur IS1, jamais sur IS2/NEW/OOS) :
  R1  signal exploitable = CONFIRMATION  ET  regime 1d 30 barres neutre (|tendance| < 5 %)
  R2  alerte precoce     = ALERTE_PRÉCOCE ET  regime 1d 30 barres neutre

Validation attendue : IS2 (validation) et NEW (periode vierge) doivent montrer une
esperance NETTE (apres 0,57 % aller-retour) superieure a la reference et positive,
avec un intervalle de confiance bootstrap qui n'inclut pas zero.

Usage : python scripts/backtest/validate_candidate_rule.py
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
HORIZONS = [96, 288]
ROUND_TRIP = 0.0057
REGIME_BAND = 0.05          # |tendance 1d 30 barres| < 5 %
OUT = Path(__file__).resolve().parent.parent.parent / "oos_rule_validation.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def bootstrap_ci(values, iterations=3000, seed=987):
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
    daily_rows = store.load_timeframe(VENUE, TEL, "1d")
    daily_closes = [r["c"] for r in daily_rows]
    daily_times = [store.close_time_ms(r, "1d") for r in daily_rows]

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
        episode["sign"] = sign
        pos = None
        for k in range(len(daily_times) - 1, -1, -1):
            if daily_times[k] <= episode["time_ms"]:
                pos = k
                break
        episode["regime"] = ((daily_closes[pos] - daily_closes[pos - 30]) / daily_closes[pos - 30]
                             if pos is not None and pos >= 30 else None)
        episode["returns"] = {h: (sign * (closes[i + h] - closes[i]) / closes[i])
                              if (sign and i + h < n) else None for h in HORIZONS}

    def segment_of(episode):
        for name, (start, end) in boundaries.items():
            if start <= episode["time_ms"] < end:
                return name
        return None

    def evaluate(label, predicate, status=None):
        out = {}
        for seg in ("NEW", "IS1", "IS2", "OOS"):
            group = [e for e in episodes if segment_of(e) == seg
                     and (status is None or e["status"] == status) and predicate(e)]
            r24 = [e["returns"][96] for e in group if e["returns"][96] is not None]
            r288 = [e["returns"][288] for e in group if e["returns"][288] is not None]
            if len(r24) < 15:
                out[seg] = {"n": len(r24), "insufficient": True}
                continue
            low, high = bootstrap_ci(r24)
            out[seg] = {
                "n": len(r24),
                "expectancy_24h": mean(r24), "ci95": [low, high],
                "expectancy_24h_net": mean(r24) - ROUND_TRIP,
                "expectancy_72h": mean(r288),
                "pct_up": 100 * sum(1 for v in r24 if v > 0) / len(r24),
            }
        return {"label": label, "segments": out}

    def show(result):
        for seg in ("NEW", "IS1", "IS2", "OOS"):
            s = result["segments"][seg]
            if s.get("insufficient"):
                print(f"    {seg:4s} : n={s['n']:>4} (effectif insuffisant)")
                continue
            ci = s["ci95"]
            print(f"    {seg:4s} : n={s['n']:>5} esp24={s['expectancy_24h'] * 100:+.3f}% "
                  f"[{ci[0] * 100:+.3f},{ci[1] * 100:+.3f}] net={s['expectancy_24h_net'] * 100:+.3f}% "
                  f"haut={s['pct_up']:.0f}%")

    # --------------------------------------------- sensibilite de la bande
    print("=== Sensibilite de la bande de regime (sur IS1 uniquement, segment de conception) ===")
    for band in (0.03, 0.05, 0.08, 0.12):
        group = [e for e in episodes if segment_of(e) == "IS1" and e["status"] == "CONFIRMATION"
                 and e["regime"] is not None and abs(e["regime"]) < band]
        r24 = [e["returns"][96] for e in group if e["returns"][96] is not None]
        if r24:
            print(f"  bande |trend| < {band * 100:>4.0f} % : n={len(r24):>4} "
                  f"esp24={mean(r24) * 100:+.3f}% net={(mean(r24) - ROUND_TRIP) * 100:+.3f}%")

    # ------------------------------------------------------- regle candidate
    print()
    print("=== Regle candidate R1 : CONFIRMATION + regime neutre (|tendance 1d 30j| < 5 %) ===")
    r1 = evaluate("R1", lambda e: e["regime"] is not None and abs(e["regime"]) < REGIME_BAND,
                  status="CONFIRMATION")
    show(r1)
    print()
    print("=== Regle candidate R2 : ALERTE_PRÉCOCE + regime neutre ===")
    r2 = evaluate("R2", lambda e: e["regime"] is not None and abs(e["regime"]) < REGIME_BAND,
                  status="ALERTE_PRÉCOCE")
    show(r2)
    print()
    print("=== References : tous les signaux (sans filtre) ===")
    all_alerts = evaluate("ALERTE tous", lambda e: True, status="ALERTE_PRÉCOCE")
    show(all_alerts)
    all_conf = evaluate("CONFIRMATION tous", lambda e: True, status="CONFIRMATION")
    show(all_conf)
    print()
    print("=== Reference : entree aleatoire (meme barre) ===")
    for seg, (start, end) in boundaries.items():
        idxs = [i for i, t in enumerate(times) if start <= t < end]
        moves = [(closes[i + 96] - closes[i]) / closes[i] for i in idxs if i + 96 < n]
        print(f"    {seg:4s} : n={len(moves):>6} esp24={mean(moves) * 100:+.3f}% "
              f"| net apres {ROUND_TRIP * 100:.2f} % = {(mean(moves) - ROUND_TRIP) * 100:+.3f}%")

    payload = {
        "regime_band": REGIME_BAND, "round_trip": ROUND_TRIP,
        "boundaries": {k: [datetime.fromtimestamp(v[0] / 1000, timezone.utc).isoformat(),
                           datetime.fromtimestamp(v[1] / 1000, timezone.utc).isoformat()]
                       for k, v in boundaries.items()},
        "R1_confirmation_neutral": r1, "R2_alerte_neutral": r2,
        "all_alerts": all_alerts, "all_confirmations": all_conf,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

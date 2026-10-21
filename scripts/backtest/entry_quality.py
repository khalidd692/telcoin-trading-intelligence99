"""
Diagnostic de la qualite economique des entrees (15m, segment OOS deja consulte).

Questions :
  1. Quelle est l'esperance d'une entree ALEATOIRE (meme barre, meme direction) ?
     -> permet de distinguer "le detecteur est mauvais" de "le marche etait mauvais".
  2. Les pertes viennent-elles d'entrees TARDIVES (le mouvement a deja commence) ?
  3. Les signaux sont-ils des CONTINUATIONS deguisees en retournements ?
  4. Quelle part du resultat tient a la REGIME (tendance lente, volatilite) ?
  5. Quelle est la SENSIBILITE aux couts ?

Sortie : JSON (oos_entry_quality.json) + affichage console.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402
from scripts.backtest.protocol import COST_SCENARIOS, IS_SHARE  # noqa: E402

VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
OUT = Path(__file__).resolve().parent.parent.parent / "oos_entry_quality.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def main() -> int:
    target = "15m"
    rows = store.load_timeframe(VENUE, SYMBOL, target)
    bundle = Bundle(target, rows)
    times = [store.close_time_ms(r, target) for r in rows]
    # Frontieres ABSOLUES (identiques a run_oos.py) : une coupure en pourcentage
    # se deplacerait des que l'historique est prolonge.
    def ms_of(text):
        return int(datetime.fromisoformat(text + "+00:00").timestamp() * 1000)

    SEGMENTS = {
        "NEW": ("2024-03-27", "2025-07-09"),
        "IS1": ("2025-07-09", "2025-11-27"),
        "IS2": ("2025-11-27", "2026-04-16"),
        "OOS": ("2026-04-16", "2030-01-01"),
    }
    oos_start, oos_end = ms_of(SEGMENTS["OOS"][0]), ms_of(SEGMENTS["OOS"][1])
    oos = [i for i, t in enumerate(times) if oos_start <= t < oos_end]
    print(f"cible {target} · segment OOS : {len(oos)} barres")
    closes = bundle.closes
    atr = bundle.atr
    n = len(closes)

    # ---------------------------------------------------------------- signaux
    others = {}
    for tf in ALL_TFS:
        if tf == target:
            continue
        r = store.load_timeframe(VENUE, SYMBOL, tf)
        if r:
            others[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in others.items()}

    signals = []
    for i in oos:
        t_ms = times[i]
        timeframes = {target: fast_timeframe_state(bundle, i, t_ms)}
        for tf, other in others.items():
            k = indexes[tf].index_at(t_ms)
            timeframes[tf] = fast_timeframe_state(other, k, t_ms) if k is not None else {
                "status": "UNAVAILABLE", "reason": "aucune bougie", "candle_count": 0,
                "trend": "INDETERMINE"}
        detection = call_detector(timeframes, detection_state(bundle, i))
        if detection["signal_status"] in ("ALERTE_PRÉCOCE", "CONFIRMATION"):
            signals.append({
                "index": i, "time_ms": t_ms, "status": detection["signal_status"],
                "direction": detection["direction"], "confidence": detection.get("confidence", 0),
                "families": detection.get("families", []),
                "setup": detection.get("setup"),
                "evidence": [e.get("type") for e in detection.get("evidence", [])],
                "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                "price": closes[i],
            })
    episodes = engine.group_episodes(signals)
    print(f"episodes (OOS) : {len(episodes)}")

    # ------------------------------------------------- 1. entree aleatoire
    print()
    print("=== 1. Reference : entree ALEATOIRE a la meme barre et meme direction ===")
    random_expectancy = {}
    for horizon in (96, 288):
        moves = []
        for i in oos:
            j = i + horizon
            if j >= n:
                continue
            moves.append((closes[j] - closes[i]) / closes[i])
        random_expectancy[str(horizon)] = {
            "mean": mean(moves),
            "median": statistics.median(moves),
            "pct_up": 100 * sum(1 for m in moves if m > 0) / len(moves),
        }
        print(f"  h={horizon:>3} | esperance moyenne={mean(moves) * 100:+.3f}% "
              f"| mediane={statistics.median(moves) * 100:+.3f}% "
              f"| part en hausse={100 * sum(1 for m in moves if m > 0) / len(moves):.1f}%")

    # ------------------------------------------- 2. entree tardive / fresque
    print()
    print("=== 2. Entree tardive : le mouvement avait-il deja commence ? ===")
    print("   (pre-mouvement mesure depuis l'ancre du setup jusqu'a la barre du signal, en ATR)")
    buckets = {"frais <0.25 ATR": [], "0.25-0.5 ATR": [], "0.5-1 ATR": [], ">1 ATR": []}
    per_status_buckets = {"ALERTE_PRÉCOCE": {k: [] for k in buckets},
                          "CONFIRMATION": {k: [] for k in buckets}}
    pre_move_all = []
    for episode in episodes:
        i = episode["index"]
        setup = episode.get("setup") or {}
        # l'index du setup est RELATIF a la fenetre analysee : on passe par l'age
        age = setup.get("age_bars", 0)
        e = i - age
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        if not sign or e < 0 or i + 96 >= n:
            continue
        atr_value = atr[i] if i < len(atr) else None
        if atr_value is None or not math.isfinite(atr_value) or atr_value <= 0:
            continue
        pre = sign * (closes[i] - closes[e]) / closes[e]
        pre_atr = pre / atr_value
        j = i + 96
        forward = sign * (closes[j] - closes[i]) / closes[i]
        pre_move_all.append(pre_atr)
        if pre_atr < 0.25:
            key = "frais <0.25 ATR"
        elif pre_atr < 0.5:
            key = "0.25-0.5 ATR"
        elif pre_atr < 1.0:
            key = "0.5-1 ATR"
        else:
            key = ">1 ATR"
        buckets[key].append(forward)
        per_status_buckets[episode["status"]][key].append(forward)
    for key, values in buckets.items():
        if values:
            print(f"  {key:16s} n={len(values):>4} esperance a 24 h={mean(values) * 100:+.3f}% "
                  f"| part en hausse={100 * sum(1 for v in values if v > 0) / len(values):.1f}%")
    print(f"  pre-mouvement median={statistics.median([v for v in pre_move_all if v is not None]) * 100 if any(v is not None for v in pre_move_all) else 0:+.3f} % de l'ATR")

    # --------------------------------- 3. continuations deguisees ?
    print()
    print("=== 3. Signal de continuation deguise en retournement ? ===")
    print("   (mouvement AVANT l'ancre, dans le sens du signal : un retournement vrai")
    print("    doit avoir ete declenche par un mouvement oppose)")
    continuation = {"contre": [], "dans_le_sens": []}
    for episode in episodes:
        i = episode["index"]
        setup = episode.get("setup") or {}
        age = setup.get("age_bars", 0)
        e = i - age
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        if not sign or e < 12 or i + 96 >= n:
            continue
        before = sign * (closes[e] - closes[e - 12]) / closes[e - 12]
        j = i + 96
        forward = sign * (closes[j] - closes[i]) / closes[i]
        key = "contre" if before < 0 else "dans_le_sens"
        continuation[key].append(forward)
    for key, values in continuation.items():
        if values:
            print(f"  mouvement anterieur {key:14s} n={len(values):>4} "
                  f"esperance a 24 h={mean(values) * 100:+.3f}% "
                  f"| part en hausse={100 * sum(1 for v in values if v > 0) / len(values):.1f}%")

    # ---------------------------------------------------- 4. regime
    print()
    print("=== 4. Regime : la perte est-elle concentree ? ===")
    daily = store.load_timeframe(VENUE, SYMBOL, "1d")
    d_closes = [r["c"] for r in daily]
    d_times = [store.close_time_ms(r, "1d") for r in daily]
    regime_buckets = {"marche en baisse": [], "marche en hausse": [], "neutre": []}
    for episode in episodes:
        i = episode["index"]
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        if not sign or i + 96 >= n:
            continue
        t_ms = times[i]
        pos = None
        for k in range(len(d_times) - 1, -1, -1):
            if d_times[k] <= t_ms:
                pos = k
                break
        if pos is None or pos < 30:
            continue
        trend = (d_closes[pos] - d_closes[pos - 30]) / d_closes[pos - 30]
        j = i + 96
        forward = sign * (closes[j] - closes[i]) / closes[i]
        key = "marche en baisse" if trend < -0.05 else ("marche en hausse" if trend > 0.05 else "neutre")
        regime_buckets[key].append(forward)
    for key, values in regime_buckets.items():
        if values:
            print(f"  {key:18s} n={len(values):>4} esperance a 24 h={mean(values) * 100:+.3f}% "
                  f"| part en hausse={100 * sum(1 for v in values if v > 0) / len(values):.1f}%")

    # ---------------------------------------------------- 5. couts
    print()
    print("=== 5. Esperance nette par scenario de couts (toutes alertes, 24 h) ===")
    for label, cost in COST_SCENARIOS.items():
        net = []
        for episode in episodes:
            i = episode["index"]
            sign = 1.0 if episode["direction"] == "HAUSSIER" else (
                -1.0 if episode["direction"] == "BAISSIER" else 0.0)
            if not sign or i + 96 >= n:
                continue
            net.append(sign * (closes[i + 96] - closes[i]) / closes[i] - cost)
        print(f"  {label:26s} esperance nette={mean(net) * 100:+.3f}% "
              f"| par episode={mean(net) * 100:+.3f} %")

    payload = {
        "target": target, "segment": "OOS", "horizons": [96, 288],
        "random_entry_reference": random_expectancy,
        "late_entry_buckets": {k: {"n": len(v), "expectancy": mean(v),
                                   "pct_up": 100 * sum(1 for x in v if x > 0) / len(v) if v else None}
                               for k, v in buckets.items()},
        "late_entry_by_status": {status: {k: {"n": len(v), "expectancy": mean(v)}
                                               for k, v in groups.items()}
                                  for status, groups in per_status_buckets.items()},
        "continuation_buckets": {k: {"n": len(v), "expectancy": mean(v),
                                     "pct_up": 100 * sum(1 for x in v if x > 0) / len(v) if v else None}
                                 for k, v in continuation.items()},
        "regime_buckets": {k: {"n": len(v), "expectancy": mean(v),
                               "pct_up": 100 * sum(1 for x in v if x > 0) / len(v) if v else None}
                           for k, v in regime_buckets.items()},
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

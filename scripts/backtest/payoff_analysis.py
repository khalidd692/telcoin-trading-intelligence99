"""
Profil gains/pertes des signaux du moteur v2 sur le segment de validation (OOS, 15m).

Repond a la question : les signaux qui reussissent compensent-ils ceux qui
echouent ? Un taux de reussite ne dit rien de la quality du payoff.

Sortie : pour chaque statut et chaque horizon de reference, distribution des
mouvements diriges (moyenne, mediane, pire, meilleur), moyenne des gains,
moyenne des pertes, et le ratio gain/perte.

Usage : python scripts/backtest/payoff_analysis.py
"""

from __future__ import annotations

import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402
from scripts.backtest.protocol import IS_SHARE  # noqa: E402

VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]


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
    oos_indices = [i for i, t in enumerate(times) if oos_start <= t < oos_end]
    print(f"cible {target} · segment de VALIDATION (OOS) : {len(oos_indices)} barres")

    others = {}
    for tf in ALL_TFS:
        if tf == target:
            continue
        r = store.load_timeframe(VENUE, SYMBOL, tf)
        if r:
            others[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in others.items()}

    signals = []
    for i in oos_indices:
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
                "reason": detection.get("reason", ""), "price": bundle.closes[i],
                "exploitable": detection.get("exploitable", False),
            })
    episodes = engine.group_episodes(signals)
    print(f"episodes (OOS) : {len(episodes)}")

    # horizons de reference : 24 h (96 bougies 15m) et 72 h (288 bougies)
    closes = bundle.closes
    report = {}
    for status in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "EXPLOITABLE"):
        group = ([e for e in episodes if e.get("exploitable")] if status == "EXPLOITABLE"
                 else [e for e in episodes if e["status"] == status])
        if not group:
            continue
        print()
        print(f"--- {status} (n={len(group)}) ---")
        report[status] = {}
        for horizon in (96, 288):
            moves = []
            for episode in group:
                i = episode["index"]
                j = i + horizon
                if j >= len(closes):
                    continue
                sign = 1.0 if episode["direction"] == "HAUSSIER" else (
                    -1.0 if episode["direction"] == "BAISSIER" else 0.0)
                if not sign:
                    continue
                moves.append(sign * (closes[j] - closes[i]) / closes[i])
            if not moves:
                continue
            gains = [m for m in moves if m > 0]
            losses = [m for m in moves if m <= 0]
            mean_gain = statistics.fmean(gains) if gains else float("nan")
            mean_loss = statistics.fmean(losses) if losses else float("nan")
            ratio = (mean_gain / abs(mean_loss)) if losses and mean_loss == mean_loss and mean_loss != 0 else float("nan")
            expectancy = statistics.fmean(moves)
            print(f"  h={horizon:>3} bougies | moyenne={statistics.fmean(moves) * 100:+.3f}% "
                  f"| mediane={statistics.median(moves) * 100:+.3f}% "
                  f"| pire={min(moves) * 100:+.2f}% | meilleur={max(moves) * 100:+.2f}%")
            print(f"          gains n={len(gains):>4} moyenne={mean_gain * 100:+.3f}% "
                  f"| pertes n={len(losses):>4} moyenne={mean_loss * 100:+.3f}% "
                  f"| ratio gain/perte={ratio:.2f} | espérance={expectancy * 100:+.3f}%")
            report[status][str(horizon)] = {
                "episodes": len(group), "moves": len(moves),
                "mean": expectancy, "median": statistics.median(moves),
                "worst": min(moves), "best": max(moves),
                "gains": len(gains), "mean_gain": mean_gain,
                "losses": len(losses), "mean_loss": mean_loss, "payoff_ratio": ratio,
            }
    import json
    out = Path(__file__).resolve().parent.parent.parent / "oos_payoff.json"
    out.write_text(json.dumps({"target": target, "segment": "OOS", "horizons_bars": [96, 288],
                               "results": report}, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

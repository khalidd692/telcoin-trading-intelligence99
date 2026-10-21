"""
Tableau par statut ET par unite de temps : gains, pertes, mouvements favorables et
defavorables, delai d'avance, faux positifs, retournements manques.

Segments : NEW (vierge), IS1, IS2, OOS (deja consulte). Les mesures de rendement
sont exprimees en pourcentage de mouvement dirige, a 24 h et 72 h.

Usage : python scripts/backtest/status_timeframe_matrix.py
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402

VENUE, TEL = "kucoin", "TEL-USDT"
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
OUT = Path(__file__).resolve().parent.parent.parent / "oos_status_matrix.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def ms_of(text):
    return int(datetime.fromisoformat(text + "+00:00").timestamp() * 1000)


def main() -> int:
    def ms_of(text):
        return int(datetime.fromisoformat(text + "+00:00").timestamp() * 1000)

    tel_rows = store.load_timeframe(VENUE, TEL, "15m")
    tel = Bundle("15m", tel_rows)
    times = [store.close_time_ms(r, "15m") for r in tel_rows]
    n = len(tel_rows)
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
        if detection["signal_status"] in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"):
            signals.append({
                "index": i, "time_ms": t, "status": detection["signal_status"],
                "direction": detection["direction"], "confidence": detection.get("confidence", 0),
                "families": detection.get("families", []), "setup": detection.get("setup"),
                "evidence": [e.get("type") for e in detection.get("evidence", [])],
                "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                "reason": detection.get("reason", ""), "price": tel.closes[i],
                "exploitable": detection.get("exploitable", False),
            })
    episodes = engine.group_episodes(signals)
    print(f"episodes totaux : {len(episodes)}")

    # prix de reference pour les rendements
    closes = tel.closes
    horizons = {"15m": (96, 288), "1h": (24, 72), "4h": (6, 18), "1d": (1, 3)}

    def segment_of(episode):
        for name, (start, end) in boundaries.items():
            if start <= episode["time_ms"] < end:
                return name
        return None

    payload = {}
    print()
    print(f"{'UT':4s} {'statut':16s} {'seg':4s} {'n':>5} {'esp24':>8} {'esp72':>8} {'haut%':>6} {'perte max':>9} {'gain max':>9}")
    for tf in ("15m", "1h", "4h", "1d"):
        h24, h72 = horizons[tf]
        for status in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "EXPLOITABLE"):
            for seg in ("NEW", "IS1", "IS2", "OOS"):
                group = [e for e in episodes if segment_of(e) == seg
                         and (status != "EXPLOITABLE" or e.get("exploitable"))
                         and (status == "EXPLOITABLE" or e["status"] == status)]
                r24, r288 = [], []
                for e in group:
                    i = e["index"]
                    sign = 1.0 if e["direction"] == "HAUSSIER" else (
                        -1.0 if e["direction"] == "BAISSIER" else 0.0)
                    if not sign:
                        continue
                    if i + h24 < n:
                        r24.append(sign * (closes[i + h24] - closes[i]) / closes[i])
                    if i + h72 < n:
                        r288.append(sign * (closes[i + h72] - closes[i]) / closes[i])
                if not r24:
                    continue
                payload[f"{tf}|{status}|{seg}"] = {
                    "n": len(r24), "expectancy_24h": mean(r24), "expectancy_72h": mean(r288),
                    "pct_up": 100 * sum(1 for v in r24 if v > 0) / len(r24),
                    "worst": min(r24), "best": max(r24),
                }
                if seg in ("NEW", "OOS"):
                    print(f"{tf:4s} {status:16s} {seg:4s} {len(r24):>5} "
                          f"{mean(r24) * 100:>+8.3f} {mean(r288) * 100:>+8.3f} "
                          f"{100 * sum(1 for v in r24 if v > 0) / len(r24):>5.0f}% "
                          f"{min(r24) * 100:>+9.2f} {max(r24) * 100:>+9.2f}")

    # --------------------------------------- retards et retournements manques
    print()
    print("=== Delai d'avance et retournements manques (15m) ===")
    reversals = engine.find_reference_reversals(tel, list(range(300, n - 300)), "quantile")
    matching = engine.match_reversals(reversals, [e for e in episodes if e["status"] == "ALERTE_PRÉCOCE"], tel)
    leads = [m["lead_ms"] / 60000 for m in matching["detected"]]
    print(f"  retournements de reference (15m, hors segment) : {len(reversals)}")
    print(f"  detectes a l'avance par une ALERTE : {len(matching['detected'])} "
          f"({100 * len(matching['detected']) / len(reversals) if reversals else 0:.1f} %)")
    print(f"  manques : {len(matching['missed'])}")
    print(f"  avance mediane : {statistics.median(leads) if leads else None} min | "
          f"part avant entree : {100 * sum(1 for l in leads if l > 0) / len(leads) if leads else 0:.1f} %")
    payload["lead"] = {"reversals": len(reversals), "detected": len(matching["detected"]),
                       "missed": len(matching["missed"]),
                       "median_lead_min": statistics.median(leads) if leads else None}

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

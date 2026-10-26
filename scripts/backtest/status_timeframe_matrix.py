"""
Tableau par statut ET par unite de temps : gains, pertes, mouvements favorables et
defavorables, delai d'avance, faux positifs, retournements manques.

Segments : NEW (vierge), IS1, IS2, OOS (deja consulte). Les mesures de rendement
sont exprimees en pourcentage de mouvement dirige, aux horizons d'indices 1 et 2
de la grille de chaque unite de temps (convention de presentation, cf. protocol.py
HORIZON_PRESENTATION_INDICES) :
  15m -> 6h (24 barres) et 24h (96 barres)
  1h  -> 6h (6 barres) et 24h (24 barres)
  4h  -> 72h (18 barres) et 168h (42 barres)
  1d  -> 120h (5 barres) et 240h (10 barres)

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
from scripts.backtest.harness import (Bundle, call_detector, detection_state,  # noqa: E402
    fast_timeframe_state, horizons_in_bars)
from scripts.backtest.protocol import HORIZON_PRESENTATION_INDICES  # noqa: E402

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

    # Build bundles for all timeframes (each evaluated on its own grid)
    bundles: dict[str, Bundle] = {}
    for tf in ALL_TFS:
        r = store.load_timeframe(VENUE, TEL, tf)
        if r:
            bundles[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in bundles.items()}

    # Per-TF episode collection (each TF evaluated on its own bar grid)
    tf_episodes: dict[str, list[dict]] = {}
    for tf, bundle in bundles.items():
        rows_tf = bundle.rows
        times_tf = [store.close_time_ms(r, tf) for r in rows_tf]
        n_tf = len(rows_tf)
        boundaries = {
            "NEW": (times_tf[0], ms_of("2025-07-09")),
            "IS1": (ms_of("2025-07-09"), ms_of("2025-11-27")),
            "IS2": (ms_of("2025-11-27"), ms_of("2026-04-16")),
            "OOS": (ms_of("2026-04-16"), times_tf[-1] + 1),
        }
        signals = []
        for i in range(n_tf):
            t = times_tf[i]
            tfm = {}
            for tf2, b2 in bundles.items():
                k = indexes[tf2].index_at(t)
                tfm[tf2] = fast_timeframe_state(b2, k, t) if k is not None else {
                    "status": "UNAVAILABLE", "reason": "x", "candle_count": 0, "trend": "INDETERMINE"}
            detection = call_detector(tfm, detection_state(bundles["15m"],
                indexes["15m"].index_at(t) if indexes["15m"].index_at(t) is not None else 0))
            if detection["signal_status"] in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"):
                signals.append({
                    "index": i, "time_ms": t, "status": detection["signal_status"],
                    "direction": detection["direction"], "confidence": detection.get("confidence", 0),
                    "families": detection.get("families", []), "setup": detection.get("setup"),
                    "evidence": [e.get("type") for e in detection.get("evidence", [])],
                    "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                    "reason": detection.get("reason", ""), "price": bundle.closes[i],
                    "exploitable": detection.get("exploitable", False),
                })
        tf_episodes[tf] = engine.group_episodes(signals)
        print(f"  {tf}: {len(signals)} signaux, {len(tf_episodes[tf])} episodes")

    # Use the first TF for the global episode count and lead analysis
    tel = bundles["15m"]
    tel_rows = tel.rows
    times = [store.close_time_ms(r, "15m") for r in tel_rows]
    n = len(tel_rows)
    episodes = tf_episodes["15m"]
    print(f"episodes totaux (15m) : {len(episodes)}")

    # Prix de reference pour les rendements : on utilise les horizons du protocole
    # (HORIZON_DURATIONS) tels qu'ils sont, sans chercher a forcer une correspondance
    # avec 24h/72h. Chaque ligne affiche ses propres horizons reelment mesures.
    # Les colonnes sont renommees selon la timeframe pour eviter la tromperie.
    horizons = {}
    horizon_labels = {}
    for tf in ("15m", "1h", "4h", "1d"):
        available = horizons_in_bars(tf)
        if len(available) >= 4:
            # Utiliser les horizons d'indices HORIZON_PRESENTATION_INDICES
            # (convention de presentation, cf. protocol.py) :
            # le 1er horizon (indice 0) est trop proche du signal pour
            # mesurer un mouvement dirige fiable.
            h_a, h_b = available[HORIZON_PRESENTATION_INDICES[0]], available[HORIZON_PRESENTATION_INDICES[1]]
            horizons[tf] = (h_a, h_b)
            tf_sec = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}[tf]
            label_a = "{}h".format(int(round(h_a * tf_sec / 3600)))
            label_b = "{}h".format(int(round(h_b * tf_sec / 3600)))
            horizon_labels[tf] = (label_a, label_b)
        else:
            horizons[tf] = None
            horizon_labels[tf] = ("-", "-")

    payload = {}
    print()
    # Chaque timeframe affiche son propre en-tête avec ses horizons réellement
    # mesurés. Le choix des horizons d'indices HORIZON_PRESENTATION_INDICES
    # (1,2) est une convention de présentation, pas une valeur statistiquement
    # validée (cf. protocol.py).
    for tf in ("15m", "1h", "4h", "1d"):
        if horizons[tf] is None:
            print(f"{tf:4s} {'NON MESURABLE':16s} {'-':4s} {'-':>5s} "
                  f"{'-':>8s} {'-':>8s} {'-':>6s} {'-':>9s} {'-':>9s}")
            continue
        h_a, h_b = horizons[tf]
        label_a, label_b = horizon_labels[tf]
        print(f"# {tf} : horizons mesures = {label_a} ({h_a} barres) / "
              f"{label_b} ({h_b} barres)")
        print(f"{'UT':4s} {'statut':16s} {'seg':4s} {'n':>5} "
              f"{'esp' + label_a:>8s} {'esp' + label_b:>8s} "
              f"{'haut%':>6} {'perte max':>9} {'gain max':>9}")
        tf_bundle = bundles[tf]
        closes_tf = tf_bundle.closes
        n_tf = len(closes_tf)
        times_tf = [store.close_time_ms(r, tf) for r in tf_bundle.rows]
        tf_boundaries = {
            "NEW": (times_tf[0], ms_of("2025-07-09")),
            "IS1": (ms_of("2025-07-09"), ms_of("2025-11-27")),
            "IS2": (ms_of("2025-11-27"), ms_of("2026-04-16")),
            "OOS": (ms_of("2026-04-16"), times_tf[-1] + 1),
        }
        tf_eps = tf_episodes[tf]

        def segment_of(episode, bnds=tf_boundaries):
            for name, (start, end) in bnds.items():
                if start <= episode["time_ms"] < end:
                    return name
            return None

        for status in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION", "EXPLOITABLE"):
            for seg in ("NEW", "IS1", "IS2", "OOS"):
                group = [e for e in tf_eps if segment_of(e) == seg
                         and (status != "EXPLOITABLE" or e.get("exploitable"))
                         and (status == "EXPLOITABLE" or e["status"] == status)]
                r_a, r_b = [], []
                for e in group:
                    i = e["index"]
                    sign = 1.0 if e["direction"] == "HAUSSIER" else (
                        -1.0 if e["direction"] == "BAISSIER" else 0.0)
                    if not sign:
                        continue
                    if i + h_a < n_tf:
                        r_a.append(sign * (closes_tf[i + h_a] - closes_tf[i]) / closes_tf[i])
                    if i + h_b < n_tf:
                        r_b.append(sign * (closes_tf[i + h_b] - closes_tf[i]) / closes_tf[i])
                if not r_a:
                    continue
                payload["{}|{}|{}".format(tf, status, seg)] = {
                    "n": len(r_a), "horizon_a_bars": h_a, "horizon_b_bars": h_b,
                    "horizon_a_label": label_a, "horizon_b_label": label_b,
                    "expectancy_a": mean(r_a), "expectancy_b": mean(r_b),
                    "pct_up": 100 * sum(1 for v in r_a if v > 0) / len(r_a),
                    "worst": min(r_a), "best": max(r_a),
                }
                if seg in ("NEW", "OOS"):
                    print(f"{tf:4s} {status:16s} {seg:4s} {len(r_a):>5} "
                          f"{mean(r_a) * 100:>+8.3f} {mean(r_b) * 100:>+8.3f} "
                          f"{100 * sum(1 for v in r_a if v > 0) / len(r_a):>5.0f}% "
                          f"{min(r_a) * 100:>+9.2f} {max(r_a) * 100:>+9.2f}")

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

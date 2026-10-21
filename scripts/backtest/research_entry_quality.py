"""
Recherche sur la qualite economique des entrees : contexte BTC / ETH / TEL-BTC,
regime, continuation, et hypotheses testees sur separation chronologique stricte.

Segmentation (chronologique, sur l'axe 15m) :
  NEW  : 2024-03-27 -> 2025-07-09   (periode VERGEINE, jamais consultee)
  IS1  : 2025-07-09 -> 2025-11-27   (zone de CONCEPTION d'une regle)
  IS2  : 2025-11-27 -> 2026-04-16   (zone de VALIDATION de la regle)
  OOS  : 2026-04-16 -> 2026-10-20   (deja consulte : usage exploratoire uniquement)

Une hypothese n'est retenue que si elle survit sur IS2 ET sur NEW, avec une
esperance NETTE (apres 0,57 % aller-retour) positive.

Usage : python scripts/backtest/research_entry_quality.py
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import engine, history_store as store  # noqa: E402
from scripts.backtest.harness import Bundle, call_detector, detection_state, fast_timeframe_state  # noqa: E402

VENUE = "kucoin"
TEL = "TEL-USDT"
CONTEXT = {"BTC": "BTC-USDT", "ETH": "ETH-USDT", "TELBTC": "TEL-BTC"}
ALL_TFS = ["15m", "1h", "4h", "1d", "1w", "1M"]
HORIZONS = [96, 288]           # 24 h et 72 h en bougies 15m
ROUND_TRIP = 0.0057            # aller-retour observe (slippage MEXC seul)
BOOTSTRAP = 2000
OUT = Path(__file__).resolve().parent.parent.parent / "oos_research.json"


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def bootstrap_ci(values, iterations=BOOTSTRAP, seed=12345):
    """IC 95 % bootstrap de l'esperance."""
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


def aligned_index(context_bundle: Bundle, times, index):
    """Dernier contexte dont la cloture est <= la barre de signal (causal)."""
    t_ms = times[index]
    lo, hi = 0, len(context_bundle.rows) - 1
    found = None
    while lo <= hi:
        mid = (lo + hi) // 2
        close_ms = store.close_time_ms(context_bundle.rows[mid], context_bundle.timeframe)
        if close_ms <= t_ms:
            found = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return found


def main() -> int:
    tel_rows = store.load_timeframe(VENUE, TEL, "15m")
    tel = Bundle("15m", tel_rows)
    times = [store.close_time_ms(r, "15m") for r in tel_rows]
    closes = tel.closes
    n = len(closes)

    # Frontieres alignees sur le protocole OOS publie (OOS_PROTOCOL.md) :
    #   NEW  : la periode vierge fraichement collectee (2024-03-27 -> 2025-07-09)
    #   IS1  : premiere moitie de la periode de conception
    #   IS2  : seconde moitie de la periode de conception
    #   OOS  : exactement le segment de validation du protocole OOS (coupure 2026-04-16)
    def ms_of(text):
        return int(datetime.fromisoformat(text + "+00:00").timestamp() * 1000)

    t_new_end = ms_of("2025-07-09")
    t_is1_end = ms_of("2025-11-27")
    t_is2_end = ms_of("2026-04-16")
    boundaries = {
        "NEW": (times[0], t_new_end),
        "IS1": (t_new_end, t_is1_end),
        "IS2": (t_is1_end, t_is2_end),
        "OOS": (t_is2_end, times[-1] + 1),
    }
    for name, (start, end) in boundaries.items():
        print(f"  {name:4s} : {datetime.fromtimestamp(start / 1000, timezone.utc).date()} -> "
              f"{datetime.fromtimestamp(end / 1000, timezone.utc).date()}")

    # ------------------------------------------------- contexte 1h + daily TEL
    ctx = {}
    for label, symbol in CONTEXT.items():
        rows = store.load_timeframe(VENUE, symbol, "1h")
        if rows:
            ctx[label] = Bundle("1h", rows)
            print(f"  contexte {label:7s} ({symbol}) : {len(rows)} bougies 1h")
    daily_rows = store.load_timeframe(VENUE, TEL, "1d")
    daily = Bundle("1d", daily_rows)
    daily_times = [store.close_time_ms(r, "1d") for r in daily_rows]

    # ----------------------------------------------------------- signaux v2
    others = {}
    for tf in ALL_TFS:
        if tf == "15m":
            continue
        r = store.load_timeframe(VENUE, TEL, tf)
        if r:
            others[tf] = Bundle(tf, r)
    indexes = {tf: engine.TimeframeIndex(b) for tf, b in others.items()}

    signals = []
    for i in range(0, n):
        t = times[i]
        tfm = {"15m": fast_timeframe_state(tel, i, t)}
        for tf, b in others.items():
            k = indexes[tf].index_at(t)
            tfm[tf] = fast_timeframe_state(b, k, t) if k is not None else {
                "status": "UNAVAILABLE", "reason": "aucune bougie", "candle_count": 0,
                "trend": "INDETERMINE"}
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
    episodes = engine.group_epitals = engine.group_episodes(signals)
    print(f"  signaux totaux : {len(signals)} · episodes : {len(episodes)}")

    # --------------------------------------------------- enrichissement
    atr = tel.atr
    daily_closes = daily.closes
    for episode in episodes:
        i = episode["index"]
        sign = 1.0 if episode["direction"] == "HAUSSIER" else (
            -1.0 if episode["direction"] == "BAISSIER" else 0.0)
        episode["sign"] = sign
        # regime : tendance 30 jours sur le 1d TEL
        pos = None
        for k in range(len(daily_times) - 1, -1, -1):
            if daily_times[k] <= episode["time_ms"]:
                pos = k
                break
        if pos is not None and pos >= 30:
            episode["regime_30d"] = (daily_closes[pos] - daily_closes[pos - 30]) / daily_closes[pos - 30]
        else:
            episode["regime_30d"] = None
        # mouvement avant l'ancre (sens du signal)
        age = (episode.get("setup") or {}).get("age_bars", 0)
        e = i - age
        if e >= 12 and sign:
            episode["pre_anchor"] = sign * (closes[e] - closes[e - 12]) / closes[e - 12]
        else:
            episode["pre_anchor"] = None
        # pre-mouvement depuis l'ancre (fraîcheur de l'entree)
        atr_value = atr[i] if i < len(atr) else None
        if (sign and e >= 0 and atr_value and math.isfinite(atr_value) and atr_value > 0):
            episode["pre_move_atr"] = sign * (closes[i] - closes[e]) / closes[e] / atr_value
        else:
            episode["pre_move_atr"] = None
        # contexte
        for label, bundle in ctx.items():
            k = aligned_index(bundle, times, i)
            if k is None or k < 30:
                episode[f"ctx_{label}_24h"] = None
                episode[f"ctx_{label}_4h"] = None
                continue
            c = bundle.closes
            episode[f"ctx_{label}_24h"] = (c[k] - c[k - 24]) / c[k - 24]
            episode[f"ctx_{label}_4h"] = (c[k] - c[k - 4]) / c[k - 4]
        # rendements
        episode["returns"] = {}
        for h in HORIZONS:
            j = i + h
            episode["returns"][h] = (sign * (closes[j] - closes[i]) / closes[i]) if (sign and j < n) else None

    # ------------------------------------------------------- evaluation
    def segment_of(episode):
        for name, (start, end) in boundaries.items():
            if start <= episode["time_ms"] < end:
                return name
        return None

    def subset(seg, status, predicate):
        return [e for e in episodes if segment_of(e) == seg and e["status"] == status and predicate(e)]

    def report(label, seg, status, predicate):
        group = subset(seg, status, predicate)
        if len(group) < 30:
            return None
        r24 = [e["returns"][96] for e in group if e["returns"][96] is not None]
        r288 = [e["returns"][288] for e in group if e["returns"][288] is not None]
        if not r24:
            return None
        low, high = bootstrap_ci(r24)
        return {
            "label": label, "segment": seg, "status": status, "n": len(group),
            "expectancy_24h": mean(r24), "ci95_24h": [low, high],
            "median_24h": statistics.median(r24),
            "expectancy_72h": mean(r288),
            "expectancy_24h_net": mean(r24) - ROUND_TRIP,
            "pct_up_24h": 100 * sum(1 for v in r24 if v > 0) / len(r24),
        }

    def show(rows):
        for r in rows:
            if not r:
                continue
            ci = r["ci95_24h"]
            print(f"    {r['label'][:52]:52s} n={r['n']:>5} esp24={r['expectancy_24h'] * 100:+.3f}% "
                  f"[{ci[0] * 100:+.3f},{ci[1] * 100:+.3f}] net={r['expectancy_24h_net'] * 100:+.3f}% "
                  f"haut={r['pct_up_24h']:.0f}%")

    print()
    print("=== A. Reference : entree aleatoire (meme barre, direction tiree au hasard) ===")
    random_ref = {}
    for seg, (start, end) in boundaries.items():
        idxs = [i for i, t in enumerate(times) if start <= t < end]
        moves = []
        for i in idxs:
            j = i + 96
            if j < n:
                moves.append((closes[j] - closes[i]) / closes[i])
        random_ref[seg] = {"n": len(moves), "expectancy": mean(moves),
                           "median": statistics.median(moves) if moves else None,
                           "pct_up": 100 * sum(1 for v in moves if v > 0) / len(moves) if moves else None}
        print(f"  {seg:4s} : n={len(moves):>6} esperance={mean(moves) * 100:+.3f}% "
              f"| mediane={statistics.median(moves) * 100:+.3f}% "
              f"| part en hausse={random_ref[seg]['pct_up']:.1f}%")

    print()
    print("=== B. Statut ALERTE_PRÉCOCE, par segment et par condition ===")
    conditions = [
        ("tous", lambda e: True),
        ("regime neutre (|tendance 30j| < 5 %)", lambda e: e.get("regime_30d") is not None and abs(e["regime_30d"]) < 0.05),
        ("regime en baisse", lambda e: e.get("regime_30d") is not None and e["regime_30d"] < -0.05),
        ("regime en hausse", lambda e: e.get("regime_30d") is not None and e["regime_30d"] > 0.05),
        ("mouvement anterieur oppose (vrai retournement)",
         lambda e: e.get("pre_anchor") is not None and e["pre_anchor"] < 0),
        ("mouvement anterieur dans le sens (continuation)",
         lambda e: e.get("pre_anchor") is not None and e["pre_anchor"] >= 0),
        ("BTC 24h en hausse", lambda e: (e.get("ctx_BTC_24h") or 0) > 0),
        ("BTC 24h en baisse", lambda e: (e.get("ctx_BTC_24h") or 0) <= 0),
        ("TEL/BTC 24h en hausse", lambda e: (e.get("ctx_TELBTC_24h") or 0) > 0),
        ("TEL/BTC 24h en baisse", lambda e: (e.get("ctx_TELBTC_24h") or 0) <= 0),
        ("ETH 24h en hausse", lambda e: (e.get("ctx_ETH_24h") or 0) > 0),
        ("regime neutre + BTC 24h en hausse",
         lambda e: (e.get("regime_30d") is not None and abs(e["regime_30d"]) < 0.05
                    and (e.get("ctx_BTC_24h") or 0) > 0)),
        ("regime neutre + BTC 24h en baisse",
         lambda e: (e.get("regime_30d") is not None and abs(e["regime_30d"]) < 0.05
                    and (e.get("ctx_BTC_24h") or 0) <= 0)),
        ("regime neutre + TEL/BTC 24h en baisse",
         lambda e: (e.get("regime_30d") is not None and abs(e["regime_30d"]) < 0.05
                    and (e.get("ctx_TELBTC_24h") or 0) <= 0)),
    ]
    results = {}
    for status in ("ALERTE_PRÉCOCE", "CONFIRMATION"):
        print(f"  --- {status} ---")
        for seg in ("NEW", "IS1", "IS2", "OOS"):
            rows = [report(label, seg, status, predicate) for label, predicate in conditions]
            results[f"{status}|{seg}"] = rows
            print(f"    [{seg}]")
            show(rows)

    payload = {
        "boundaries": {k: [datetime.fromtimestamp(v[0] / 1000, timezone.utc).isoformat(),
                           datetime.fromtimestamp(v[1] / 1000, timezone.utc).isoformat()]
                       for k, v in boundaries.items()},
        "round_trip": ROUND_TRIP,
        "random_reference": random_ref,
        "results": results,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

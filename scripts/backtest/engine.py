"""
Moteur d'évaluation : parcours chronologique, déduplication par événement,
mesure des faux positifs, des retournements manqués, du délai d'avance,
des invalidations et des confirmations, plus test de nullité.

Le détecteur de production n'est jamais modifié : il est appelé tel quel.
"""

from __future__ import annotations

import bisect
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest import history_store as store  # noqa: E402
from scripts.backtest.harness import (  # noqa: E402
    PROTOCOL,
    Bundle,
    call_detector,
    detection_state,
    fast_timeframe_state,
    horizons_in_bars,
)

TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800, "1M": 31 * 86400}


class TimeframeIndex:
    """Alignement temporel réel : pour un instant t, la dernière bougie clôturée à <= t."""

    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.close_times = [store.close_time_ms(row, bundle.timeframe) for row in bundle.rows]

    def index_at(self, t_ms: float) -> int | None:
        pos = bisect.bisect_right(self.close_times, t_ms) - 1
        return pos if pos >= 0 else None


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson à 95 % (taille d'échantillon faible : normale ici trompeuse)."""
    if total == 0:
        return (0.0, 0.0)
    phat = successes / total
    denom = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


# --------------------------------------------------------------------------
# Collecte des signaux
# --------------------------------------------------------------------------
def collect_signals(bundles: dict[str, Bundle], indexes: dict[str, TimeframeIndex],
                    target: str, detector=None) -> tuple[list[dict], dict[str, int]]:
    """Parcourt la cible chronologiquement et appelle le détecteur à chaque clôture.

    `detector` permet de rejouer un moteur antérieur (comparaison A/B) sans
    toucher au code de production.
    """
    target_bundle = bundles[target]
    rows = target_bundle.rows
    master_times = [store.close_time_ms(row, target) for row in rows]
    status_counts: dict[str, int] = {}
    signals: list[dict] = []

    for i in range(len(rows)):
        t_ms = master_times[i]
        timeframes: dict[str, Any] = {}
        for tf, bundle in bundles.items():
            k = indexes[tf].index_at(t_ms)
            if k is None:
                timeframes[tf] = {"status": "UNAVAILABLE", "reason": "aucune bougie clôturée avant t",
                                  "candle_count": 0, "trend": "INDETERMINE"}
            else:
                timeframes[tf] = fast_timeframe_state(bundle, k, t_ms)
        if target == "15m":
            series = detection_state(target_bundle, i)
        else:
            # le détecteur lit toujours l'unité 15m : c'est elle qui porte les preuves
            k15 = indexes["15m"].index_at(t_ms)
            series = detection_state(bundles["15m"], k15) if k15 is not None else {
                "price_series_15m": [], "rsi_series_15m": [], "macd_hist_15m": [],
                "ohlc_15m": []}
        detection = call_detector(timeframes, series, detector)
        status = detection["signal_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if status in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"):
            signals.append({
                "index": i,
                "time_ms": t_ms,
                "status": status,
                "direction": detection["direction"],
                "confidence": detection["confidence"],
                "families": detection.get("families", []),
                "setup": detection.get("setup"),
                "exploitable": detection.get("exploitable", False),
                "exploitable_reason": detection.get("exploitable_reason", ""),
                "regime": detection.get("regime", {}),
                "evidence": [e.get("type") for e in detection.get("evidence", [])],
                "contradictions": [c.get("type") for c in detection.get("contradictions", [])],
                "reason": detection.get("reason"),
                "price": target_bundle.closes[i],
            })
    return signals, status_counts


def group_episodes(signals: list[dict]) -> list[dict]:
    """Dedup par evenement : un episode = premier signal d'une rafale
    de meme direction a moins de dedup_window_minutes.

    Chaque statut est regroupé independamment : une ALERTE_PRÉCOCE et sa
    CONFIRMATION ulterieure appartiennent au meme scenario, mais elles sont
    mesurees separement (l'alerte est l'actionnable, la confirmation est
    l'information attendue plus tard). Les deux series se recouvrent donc
    partiellement : c'est documente et visible dans les comptes.
    """
    window_ms = PROTOCOL["dedup_window_minutes"] * 60 * 1000
    episodes: list[dict] = []
    last_by_status: dict[str, dict] = {}
    for signal in signals:
        status = signal.get("status", "ALERTE_PRÉCOCE")
        if status not in ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION"):
            continue
        last = last_by_status.get(status)
        if last is not None and last["direction"] == signal["direction"] \
                and signal["time_ms"] - last["time_ms"] <= window_ms:
            last["member_count"] += 1
            last["members"].append(signal["index"])
            continue
        episode = {
            "index": signal["index"], "time_ms": signal["time_ms"],
            "status": status,
            "direction": signal["direction"],
            "confidence": signal.get("confidence", 0),
            "families": signal.get("families", []),
            "setup": signal.get("setup"),
            "evidence": signal.get("evidence", []),
            "contradictions": signal.get("contradictions", []),
            "reason": signal.get("reason", ""),
            "price": signal.get("price"),
            "exploitable": signal.get("exploitable", False),
            "exploitable_reason": signal.get("exploitable_reason", ""),
            "regime": signal.get("regime", {}),
            "member_count": 1, "members": [signal["index"]],
        }
        episodes.append(episode)
        last_by_status[status] = episode
    return episodes


# --------------------------------------------------------------------------
# Évaluation d'un mouvement
# --------------------------------------------------------------------------
def threshold_for(bundle: Bundle, i: int, bars: int, criterion: str) -> float | None:
    """Seuil de mouvement significatif a l'horizon `bars`.

    criterion "sigma"    : k * sqrt(H) * ATR14 relatif  (v1)
    criterion "quantile" : quantile causal q90 des mouvements avant (v2)
    """
    if criterion == "sigma":
        atr_pct = bundle.atr_pct_at(i)
        if atr_pct is None or atr_pct <= 0:
            return None
        return PROTOCOL["sigma_multiplier"] * math.sqrt(bars) * atr_pct
    if criterion == "quantile":
        series = bundle.q90.get(bars)
        if not series or i >= len(series):
            return None
        return series[i]
    raise ValueError(f"critere inconnu : {criterion}")


def evaluate_episode(bundle: Bundle, episode: dict, criterion: str) -> dict[str, Any]:
    """Mesure les mouvements après un épisode (multiples de sigma, symétrique en direction)."""
    i = episode["index"]
    horizons = horizons_in_bars(bundle.timeframe)
    atr_pct = bundle.atr_pct_at(i)
    sign = 1.0 if episode["direction"] == "HAUSSIER" else (-1.0 if episode["direction"] == "BAISSIER" else 0.0)
    closes = bundle.closes
    details = []
    hits = 0
    available = 0
    for h in horizons:
        j = i + h
        if j >= len(closes):
            details.append({"bars": h, "move": None, "threshold": None, "hit": None})
            continue
        move = (closes[j] - closes[i]) / closes[i]
        thr = threshold_for(bundle, i, h, criterion)
        directional = sign * move if sign else move
        hit = (thr is not None) and (directional >= thr)
        available += 1
        hits += 1 if hit else 0
        details.append({"bars": h, "move": move, "directional": directional,
                        "threshold": thr, "hit": hit})
    evaluable = available >= PROTOCOL["min_horizons_hit"]
    significant = evaluable and hits >= PROTOCOL["min_horizons_hit"]
    return {
        "index": i, "time_ms": episode["time_ms"], "direction": episode["direction"],
        "price": episode["price"], "confidence": episode["confidence"],
        "atr_pct": atr_pct, "horizons": details, "hits": hits, "available": available,
        "evaluable": evaluable, "significant": significant,
        "outcome": ("SIGNIFICANT" if significant else ("NON_EVALUABLE" if not evaluable else "NON_SIGNIFICANT")),
        "evidence": episode["evidence"], "member_count": episode["member_count"],
    }


def base_rate(bundle: Bundle, indices: list[int], criterion: str) -> dict[str, Any]:
    """Fréquence de mouvements significatifs en l'absence de tout signal.
    Si elle est hors [base_rate_min, base_rate_max], la fenêtre n'est pas discriminante."""
    horizons = horizons_in_bars(bundle.timeframe)
    closes = bundle.closes
    hits_counts = []
    evaluable = 0
    significant = 0
    for i in indices:
        atr_pct = bundle.atr_pct_at(i)
        if atr_pct is None:
            continue
        hits = 0
        available = 0
        for h in horizons:
            j = i + h
            if j >= len(closes):
                continue
            available += 1
            thr = threshold_for(bundle, i, h, criterion)
            if thr is not None and (closes[j] - closes[i]) / closes[i] >= thr:
                hits += 1
        if available < PROTOCOL["min_horizons_hit"]:
            continue
        evaluable += 1
        hits_counts.append(hits)
        if hits >= PROTOCOL["min_horizons_hit"]:
            significant += 1
    rate = significant / evaluable if evaluable else 0.0
    mid = indices[len(indices) // 2] if indices else 0
    return {
        "criterion": criterion,
        "evaluable_bars": evaluable,
        "significant_bars": significant,
        "base_rate": rate,
        "discriminant": PROTOCOL["base_rate_min"] <= rate <= PROTOCOL["base_rate_max"],
        "thresholds": {str(h): threshold_for(bundle, mid, h, criterion) for h in horizons},
        "horizon_bars": horizons,
    }


# --------------------------------------------------------------------------
# Retournements de référence (définition ex nihilo, indépendante du détecteur)
# --------------------------------------------------------------------------
def directional_base_rate(bundle: Bundle, indices: list[int], criterion: str) -> dict[str, Any]:
    """Taux de base calculé séparément pour les mouvements haussiers et baissiers.

    Le taux global (base_rate) ne mesure que la hausse ; le test de nullité,
    lui, applique la direction de chaque signal. Comparer les deux sans cette
    décomposition serait trompeur.
    """
    horizons = horizons_in_bars(bundle.timeframe)
    closes = bundle.closes
    stats = {"HAUSSIER": [0, 0], "BAISSIER": [0, 0]}
    for i in indices:
        hits_up = hits_down = 0
        available = 0
        for h in horizons:
            j = i + h
            if j >= len(closes):
                continue
            thr = threshold_for(bundle, i, h, criterion)
            if thr is None:
                continue
            available += 1
            move = (closes[j] - closes[i]) / closes[i]
            if move >= thr:
                hits_up += 1
            if -move >= thr:
                hits_down += 1
        if available < PROTOCOL["min_horizons_hit"]:
            continue
        stats["HAUSSIER"][1] += 1
        stats["BAISSIER"][1] += 1
        if hits_up >= PROTOCOL["min_horizons_hit"]:
            stats["HAUSSIER"][0] += 1
        if hits_down >= PROTOCOL["min_horizons_hit"]:
            stats["BAISSIER"][0] += 1
    return {
        "bullish_rate": (stats["HAUSSIER"][0] / stats["HAUSSIER"][1]) if stats["HAUSSIER"][1] else None,
        "bearish_rate": (stats["BAISSIER"][0] / stats["BAISSIER"][1]) if stats["BAISSIER"][1] else None,
        "evaluable_bars": stats["HAUSSIER"][1],
        "bullish_significant": stats["HAUSSIER"][0],
        "bearish_significant": stats["BAISSIER"][0],
    }


def find_reference_reversals(bundle: Bundle, indices: list[int], criterion: str) -> list[dict]:
    """Retournement haussier de référence, défini AVANT l'exécution et sans
    regarder le détecteur : creux sous EMA50 avec EMA20 en baisse, suivi d'un
    mouvement au-delà du seuil de volatilité, avec première entrée plausible."""
    horizons = horizons_in_bars(bundle.timeframe)
    h_max = max(horizons)
    closes = bundle.closes
    n = len(closes)
    separation = max(1, int(h_max * PROTOCOL["reference_min_separation"]))
    found: list[dict] = []
    last_entry = -10 ** 9
    for i in indices:
        if i < 60 or i + h_max >= n:
            continue
        if closes[i] > closes[i - 1]:
            continue
        ema50 = bundle.ema50[i]
        ema20_now = bundle.ema20[i]
        ema20_prev = bundle.ema20[i - 5]
        if ema50 is None or ema20_now is None or ema20_prev is None:
            continue
        if closes[i] >= ema50:
            continue
        if ema20_now - ema20_prev >= 0:
            continue
        atr_pct = bundle.atr_pct_at(i)
        if atr_pct is None:
            continue
        thr = threshold_for(bundle, i, h_max, criterion)
        if thr is None:
            continue
        peak = max(closes[i + 1:i + 1 + h_max])
        if (peak - closes[i]) / closes[i] < thr:
            continue
        entry = None
        for j in range(i + 1, min(i + 1 + h_max, n)):
            r0 = bundle.rsi14[j - 2]
            r1 = bundle.rsi14[j - 1]
            r2 = bundle.rsi14[j]
            if closes[j] > closes[j - 1] and r0 is not None and r1 is not None and r2 is not None \
                    and r0 < r1 < r2:
                entry = j
                break
        if entry is None or entry - last_entry < separation:
            continue
        last_entry = entry
        found.append({
            "trough_index": i, "entry_index": entry,
            "trough_time_ms": store.close_time_ms(bundle.rows[i], bundle.timeframe),
            "entry_time_ms": store.close_time_ms(bundle.rows[entry], bundle.timeframe),
            "trough_price": closes[i], "entry_price": closes[entry],
            "amplitude": (peak - closes[i]) / closes[i],
            "atr_pct": atr_pct,
        })
    return found


def match_reversals(reversals: list[dict], episodes: list[dict], bundle: Bundle) -> dict[str, Any]:
    """Appaire chaque retournement de référence avec l'alerte haussière la plus
    récente située dans la FENETRE D'AVERTISSEMENT (2e horizon le plus court).

    Une fenêtre large saturerait : le détecteur émettant ~7 alertes/jour en 15m,
    toute fenêtre de plusieurs jours contiendrait une alerte par construction.
    """
    horizons = horizons_in_bars(bundle.timeframe)
    warning_bars = horizons[PROTOCOL["warning_window_horizon"]]
    h_max = max(horizons)
    by_time = sorted(episodes, key=lambda e: e["time_ms"])
    times = [e["time_ms"] for e in by_time]
    step_ms = TIMEFRAME_SECONDS.get(bundle.timeframe, 900) * 1000
    detected, missed = [], []
    for reversal in reversals:
        low = reversal["entry_time_ms"] - warning_bars * step_ms
        high = reversal["entry_time_ms"]
        left = bisect.bisect_left(times, low)
        right = bisect.bisect_right(times, high)
        candidates = [e for e in by_time[left:right] if e["direction"] == "HAUSSIER"]
        if candidates:
            best = max(candidates, key=lambda e: e["time_ms"])
            detected.append({
                **reversal,
                "alert_index": best["index"],
                "alert_time_ms": best["time_ms"],
                "lead_ms": reversal["entry_time_ms"] - best["time_ms"],
                "lead_bars": (reversal["entry_index"] - best["index"]),
                "alert_evidence": best["evidence"],
            })
        else:
            missed.append(reversal)
    return {"detected": detected, "missed": missed, "warning_bars": warning_bars, "max_horizon_bars": h_max}


# --------------------------------------------------------------------------
# Test de nullité
# --------------------------------------------------------------------------
def null_test(bundle: Bundle, episodes: list[dict], evaluated: list[dict],
              criterion: str, iterations: int | None = None) -> dict[str, Any]:
    """Permutation des instants de signal : distribution du taux de réussite
    sous l'hypothèse « aucun pouvoir prédictif »."""
    iterations = iterations or PROTOCOL["null_test_iterations"]
    if not evaluated:
        return {"iterations": 0, "observed_hit_rate": None, "null_hit_rate_median": None,
                "null_hit_rate_p95": None, "percentile": None, "significant": False}
    rng = random.Random(20261021)
    horizon_bars = horizons_in_bars(bundle.timeframe)
    n = len(bundle.closes)
    atr_cache = bundle.atr_pct_median
    valid_set = {k for k in range(len(bundle.closes))
                 if k + max(horizon_bars) < n and atr_cache[k] is not None}
    valid_range = sorted(valid_set)

    def hit_rate(indices: list[int], sign: list[float]) -> float:
        hits = 0
        evaluable = 0
        for k, direction in zip(indices, sign):
            if k not in valid_set:
                continue
            ok = 0
            avail = 0
            for h in horizon_bars:
                j = k + h
                if j >= n:
                    continue
                thr = threshold_for(bundle, k, h, criterion)
                if thr is None:
                    continue
                avail += 1
                if direction * (bundle.closes[j] - bundle.closes[k]) / bundle.closes[k] >= thr:
                    ok += 1
            if avail < PROTOCOL["min_horizons_hit"]:
                continue
            evaluable += 1
            if ok >= PROTOCOL["min_horizons_hit"]:
                hits += 1
        return hits / evaluable if evaluable else 0.0

    observed = hit_rate([e["index"] for e in evaluated],
                        [1.0 if e["direction"] == "HAUSSIER" else -1.0 for e in evaluated])
    rates = []
    for _ in range(iterations):
        picks = [rng.choice(valid_range) for _ in evaluated]
        signs = [1.0 if e["direction"] == "HAUSSIER" else -1.0 for e in evaluated]
        rates.append(hit_rate(picks, signs))
    rates.sort()
    median = statistics.median(rates) if rates else None
    p95 = rates[int(0.95 * (len(rates) - 1))] if rates else None
    percentile = (sum(1 for r in rates if r <= observed) / len(rates)) if rates else None
    return {
        "iterations": iterations,
        "observed_hit_rate": observed,
        "null_hit_rate_median": median,
        "null_hit_rate_p95": p95,
        "percentile": percentile,
        "significant": percentile is not None and percentile >= 0.95,
    }

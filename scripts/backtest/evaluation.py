"""
Evaluation par segment (conception / validation), par statut et par scenario de couts.

Regle de non-double-compte (cf. OOS_PROTOCOL.md section 3) :
pour un segment et un scenario de couts donnes, on calcule UN SEUL jeu de masques
(mask_up / mask_down : "un signal haussier / baissier emis en cette barre serait-il
significatif, net du cout ?"). Ce meme masque sert :
  - au taux de reussite du detecteur (evalue aux barres des episodes) ;
  - a la reference de comparaison (moyenne sur toutes les barres du segment) ;
  - au test de nullite (permutation des barres).
Le cout et le seuil ne peuvent donc pas etre comptes deux fois, ni diverger entre
le detecteur et la reference.
"""

from __future__ import annotations

import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.backtest.engine import (  # noqa: E402
    match_reversals,
    find_reference_reversals,
    wilson_interval,
)
from scripts.backtest.harness import Bundle, horizons_in_bars  # noqa: E402


class SegmentMasks:
    """Masques de significativite (net de cout) pour un segment et un critere."""

    def __init__(self, bundle: Bundle, indices: list[int], criterion: str) -> None:
        self.bundle = bundle
        self.indices = indices
        self.criterion = criterion
        self.horizons = horizons_in_bars(bundle.timeframe)
        self.closes = bundle.closes
        self.n = len(bundle.closes)
        self._thresholds: dict[int, list[float | None]] = {}
        self._cache: dict[float, tuple[dict[int, bool], dict[int, bool]]] = {}

    def thresholds_at(self, index: int) -> tuple[list[float | None], list[float | None]]:
        """Seuils (montant, baissier) a l'index donne.

        Le seuil "quantile" est specifique a la direction : le q90 des mouvements
        montants n'est pas le q90 des mouvements baissiers. Le seuil "sigma"
        (base sur l'ATR) est symetrique.
        """
        cached = self._thresholds.get(index)
        if cached is None:
            if self.criterion == "sigma":
                from scripts.backtest.engine import threshold_for
                values = [threshold_for(self.bundle, index, h, self.criterion)
                          for h in self.horizons]
                cached = (values, values)
            else:
                up_values = []
                down_values = []
                for h in self.horizons:
                    up_series = self.bundle.q90.get(h)
                    down_series = self.bundle.q90_down.get(h)
                    up_values.append(up_series[index] if up_series and index < len(up_series) else None)
                    down_values.append(down_series[index] if down_series and index < len(down_series) else None)
                cached = (up_values, down_values)
            self._thresholds[index] = cached
        return cached

    def masks(self, cost: float) -> tuple[dict[int, bool], dict[int, bool]]:
        """(mask_up, mask_down) : significatif net du cout pour chaque barre."""
        cached = self._cache.get(cost)
        if cached is not None:
            return cached
        up: dict[int, bool] = {}
        down: dict[int, bool] = {}
        closes = self.closes
        horizons = self.horizons
        for index in self.indices:
            up_thresholds, down_thresholds = self.thresholds_at(index)
            base = closes[index]
            hits_up = hits_down = 0
            available = 0
            for position, h in enumerate(horizons):
                target = index + h
                if target >= self.n:
                    continue
                threshold_up = up_thresholds[position]
                threshold_down = down_thresholds[position]
                if threshold_up is None or threshold_down is None:
                    continue
                available += 1
                move = (closes[target] - base) / base
                # Protocole v1.2 : le seuil est une propriete du MARCHE (q90 des
                # mouvements anterieurs) : il se compare au mouvement BRUT. Le cout
                # est une propriete du TRADE : il sert uniquement a exiger que la
                # performance nette soit positive. L'appliquer aux deux endroits
                # le compterait deux fois (et, avec un seuil negatif, le rendrait
                # plus facile a franchir au lieu de plus dur).
                if move >= threshold_up and move - cost > 0:
                    hits_up += 1
                if -move >= threshold_down and -move - cost > 0:
                    hits_down += 1
            if available >= 2:
                up[index] = hits_up >= 2
                down[index] = hits_down >= 2
            else:
                up[index] = False
                down[index] = False
        self._cache[cost] = (up, down)
        return up, down


def direction_mix(episodes: list[dict]) -> tuple[float, float]:
    """Part des episodes haussiers et baissiers (les INDETERMINE sont exclus)."""
    up = sum(1 for e in episodes if e["direction"] == "HAUSSIER")
    down = sum(1 for e in episodes if e["direction"] == "BAISSIER")
    total = up + down
    if total == 0:
        return 0.5, 0.5
    return up / total, down / total


def _hit_rate(episodes: list[dict], up: dict[int, bool], down: dict[int, bool],
              inverted: bool = False) -> tuple[int, int]:
    hits = 0
    evaluated = 0
    for episode in episodes:
        index = episode["index"]
        direction = episode["direction"]
        if direction == "HAUSSIER":
            value = down[index] if inverted else up[index]
        elif direction == "BAISSIER":
            value = up[index] if inverted else down[index]
        else:
            continue
        evaluated += 1
        hits += 1 if value else 0
    return hits, evaluated


def _reference_rate(indices: list[int], up: dict[int, bool], down: dict[int, bool],
                    mix_up: float, mix_down: float, inverted: bool = False) -> float:
    """Taux de base : probabilite qu'un signal emis au hasard (meme melange de
    directions que les episodes observes) soit significatif."""
    if not indices:
        return 0.0
    total = 0.0
    for index in indices:
        if inverted:
            value = mix_up * down.get(index, False) + mix_down * up.get(index, False)
        else:
            value = mix_up * up.get(index, False) + mix_down * down.get(index, False)
        total += value
    return total / len(indices)


def null_test(up: dict[int, bool], down: dict[int, bool], indices: list[int],
              mix_up: float, mix_down: float, sample_size: int, iterations: int,
              seed: int = 20261021, inverted: bool = False) -> dict[str, Any]:
    """Permutation des instants de signal : distribution du taux de reussite sous
    l'hypothese « aucun pouvoir predictif »."""
    if not indices or sample_size <= 0:
        return {"iterations": 0, "median": None, "p95": None, "rates": [],
                "percentile": None, "significant": False}
    pool = list(indices)
    rng = random.Random(seed)
    rates = []
    for _ in range(iterations):
        total = 0
        for _ in range(sample_size):
            index = pool[rng.randrange(len(pool))]
            if rng.random() < mix_up:
                value = down[index] if inverted else up[index]
            else:
                value = up[index] if inverted else down[index]
            total += 1 if value else 0
        rates.append(total / sample_size)
    ordered = sorted(rates)
    return {"iterations": iterations,
            "median": statistics.median(ordered),
            "p95": ordered[int(0.95 * (len(ordered) - 1))],
            "rates": rates,
            "percentile": None, "significant": False}


def evaluate_status(episodes: list[dict], up: dict[int, bool], down: dict[int, bool],
                    indices: list[int], cost: float, inverted: bool,
                    null_iterations: int) -> dict[str, Any]:
    """Metriques d'un statut pour un segment et un scenario de couts."""
    mix_up, mix_down = direction_mix(episodes)
    hits, evaluated = _hit_rate(episodes, up, down, inverted)
    rate = hits / evaluated if evaluated else None
    low, high = wilson_interval(hits, evaluated)
    reference = _reference_rate(indices, up, down, mix_up, mix_down, inverted)
    null = null_test(up, down, indices, mix_up, mix_down, max(evaluated, 1),
                     null_iterations, inverted=inverted)
    percentile = None
    if rate is not None and null["rates"]:
        percentile = sum(1 for value in null["rates"] if value <= rate) / len(null["rates"])
    lift = (rate / reference) if (rate is not None and reference) else None
    return {
        "episodes": len(episodes),
        "evaluated": evaluated,
        "hits": hits,
        "hit_rate": rate,
        "hit_rate_wilson95": [low, high],
        "false_positives": evaluated - hits,
        "false_positive_rate": ((evaluated - hits) / evaluated) if evaluated else None,
        "reference_rate": reference,
        "lift": lift,
        "direction_mix": {"HAUSSIER": mix_up, "BAISSIER": mix_down},
        "null_median": null["median"],
        "null_p95": null["p95"],
        "null_percentile": percentile,
        "null_significant": bool(percentile is not None and percentile >= 0.95),
        "null_iterations": null["iterations"],
        "cost": cost,
    }


def reference_reversals_for_segment(bundle: Bundle, indices: list[int],
                                    criterion: str) -> list[dict]:
    """Retournements de reference d'un segment, sans regarder au-dela du segment."""
    if not indices:
        return []
    horizons = horizons_in_bars(bundle.timeframe)
    h_max = max(horizons)
    last = max(indices)
    # on ne retient que les barres dont l'horizon long reste dans le segment
    bounded = [i for i in indices if i + h_max <= last]
    if len(bounded) < 20:
        return []
    return find_reference_reversals(bundle, bounded, criterion)


def summarise_segment(bundle: Bundle, indices: list[int], episodes: list[dict],
                      criterion: str, cost_scenarios: dict[str, float],
                      null_iterations: int) -> dict[str, Any]:
    """Evaluation complete d'un segment : par statut, par scenario de couts,
    plus les retournements de reference (independants des couts)."""
    masks = SegmentMasks(bundle, indices, criterion)
    status_groups = {
        "ALERTE_PRÉCOCE": [e for e in episodes if e["status"] == "ALERTE_PRÉCOCE"],
        "CONFIRMATION": [e for e in episodes if e["status"] == "CONFIRMATION"],
        "INVALIDATION": [e for e in episodes if e["status"] == "INVALIDATION"],
        "EXPLOITABLE": [e for e in episodes if e.get("exploitable")],
    }
    combined = status_groups["ALERTE_PRÉCOCE"] + status_groups["CONFIRMATION"]

    scenarios: dict[str, Any] = {}
    for name, cost in cost_scenarios.items():
        up, down = masks.masks(cost)
        per_status = {}
        for status, group in status_groups.items():
            inverted = status == "INVALIDATION"
            per_status[status] = evaluate_status(group, up, down, indices, cost,
                                                 inverted, null_iterations)
        all_metrics = evaluate_status(combined, up, down, indices, cost, False, null_iterations)
        per_status["TOUS_SIGNALUX"] = all_metrics
        scenarios[name] = per_status

    # Retournements de reference : independants des couts (phenomene de marche).
    # L'appairage se fait sur les ALERTES PRECOCES : c'est l'avertissement
    # precoce qui compte pour le delai d'avance, pas la confirmation ulterieure.
    reversals = reference_reversals_for_segment(bundle, indices, criterion)
    alert_episodes = status_groups["ALERTE_PRÉCOCE"]
    matching = match_reversals(reversals, alert_episodes, bundle)
    leads = [m["lead_ms"] / 60000.0 for m in matching["detected"]]
    positive = [l for l in leads if l > 0]

    return {
        "bars": len(indices),
        "episodes": len(episodes),
        "density": (len(episodes) / len(indices)) if indices else None,
        "scenarios": scenarios,
        "reference_reversals": {
            "total": len(reversals),
            "detected_in_advance": len(matching["detected"]),
            "missed": len(matching["missed"]),
            "detection_rate": (len(matching["detected"]) / len(reversals)) if reversals else None,
            "median_lead_minutes": statistics.median(leads) if leads else None,
            "mean_lead_minutes": statistics.fmean(leads) if leads else None,
            "pct_before_entry": (100 * len(positive) / len(leads)) if leads else None,
            "warning_window_bars": matching["warning_bars"],
        },
    }

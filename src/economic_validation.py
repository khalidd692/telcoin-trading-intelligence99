"""Validation économique en direct d'un signal de retournement.

Rôle
----
Un signal directionnel n'a de sens économique que si le mouvement structurel
visé couvre le coût aller-retour réel : spread observé, profondeur du carnet,
frais. Ce module mesure ce coût sur les données publiques déjà collectées et le
compare à l'objectif structurel du détecteur. Il ne produit aucun ordre et ne
change pas la sémantique du détecteur : il ajoute une qualification explicite.

Règles
------
- Aucune valeur n'est inventée : sans carnet lisible, le coût est un simple
  minorant (spread seul) et le statut le dit (`PARTIEL`).
- Les frais ne sont appliqués que s'ils sont authentifiés par la provenance
  HMAC du collecteur (`normalize_fees`). Sinon le coût publié est un
  **minorant** : le coût réel est supérieur ou égal.
- Trois verdicts seulement, jamais une probabilité :
  `COUVERT`, `COUVERT_MINORANT`, `NON_COUVERT`, `INDETERMINE`.
- Le seuil de couverture est un critère *nécessaire* (`couverture >= 1`), pas
  une règle de trading validée : il n'a pas été calibré sur des résultats.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from collector.tel_collector import normalize_fees, round_trip_scenarios, verify_fees_provenance

#: Montant de référence pour l'estimation A/R, aligné sur le collecteur.
DEFAULT_NOTIONAL_USDT = 300.0

#: Couverture minimale : l'objectif doit au moins payer le coût mesuré.
MIN_COVERAGE_RATIO = 1.0

#: Directions pour lesquelles un objectif directionnel existe.
DIRECTIONAL = ("HAUSSIER", "BAISSIER")


def _number(value: Any) -> Optional[float]:
    """Convertit en flottant fini, sinon None. Ne devine jamais une valeur."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _levels(value: Any) -> list[list[float]]:
    """Normalise des niveaux [[prix, quantité], ...] en écartant l'illisible."""
    levels: list[list[float]] = []
    if not isinstance(value, list):
        return levels
    for level in value:
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            continue
        price = _number(level[0])
        quantity = _number(level[1])
        if price is None or quantity is None or price <= 0 or quantity <= 0:
            continue
        levels.append([price, quantity])
    return levels


def resolve_source(payload: Any) -> dict:
    """Retourne la source de marché MEXC d'un instantané, ou la charge utile elle-même."""
    if not isinstance(payload, dict):
        return {}
    sources = payload.get("sources")
    if isinstance(sources, dict):
        mexc = sources.get("mexc")
        if isinstance(mexc, dict):
            return mexc
        for source in sources.values():
            if isinstance(source, dict):
                return source
    return payload


def _best_scenario(scenarios: Any, notional: float) -> Optional[dict]:
    """Scénario complet le plus proche du montant demandé (jamais d'extrapolation)."""
    if not isinstance(scenarios, list):
        return None
    complete = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or scenario.get("execution_status") != "COMPLET":
            continue
        round_trip = scenario.get("round_trip")
        if not isinstance(round_trip, dict):
            continue
        cost_pct = _number(round_trip.get("cost_pct"))
        if cost_pct is None:
            continue
        complete.append((scenario, cost_pct))
    if not complete:
        return None
    scenario, cost_pct = min(
        complete,
        key=lambda item: abs((_number(item[0].get("amount_usdt")) or 0.0) - notional))
    return {"scenario": scenario, "cost_pct": cost_pct}


def _spread_pct(source: dict, scenario: Optional[dict]) -> Optional[float]:
    """Spread initial observé, en pourcentage du mid."""
    spread = source.get("spread")
    if isinstance(spread, dict):
        value = _number(spread.get("pct_mid"))
        if value is not None and value >= 0:
            return value
    best = source.get("best")
    if isinstance(best, dict):
        bid, ask = _number(best.get("bid")), _number(best.get("ask"))
        if bid and ask and bid > 0 and ask >= bid:
            mid = (bid + ask) / 2
            if mid > 0:
                return (ask - bid) / mid * 100
    if isinstance(scenario, dict):
        value = _number(scenario.get("initial_spread_pct"))
        if value is not None and value >= 0:
            return value
    liquidity = source.get("liquidity_cost")
    if isinstance(liquidity, dict):
        initial = liquidity.get("initial_spread")
        if isinstance(initial, dict):
            value = _number(initial.get("pct_mid"))
            if value is not None and value >= 0:
                return value
    return None


def measure_round_trip(source: dict, notional: float = DEFAULT_NOTIONAL_USDT) -> Optional[dict]:
    """Coût aller-retour mesuré hors frais, avec sa méthode et sa provenance.

    Ordre de préférence :
      1. `liquidity_cost` déjà calculé par le collecteur (si `usable`) ;
      2. carnet observé (`book.bids`/`book.asks`) rejoué sur le montant demandé ;
      3. spread seul, explicitement marqué comme minorant (`spread_only`).
    """
    liquidity = source.get("liquidity_cost")
    if isinstance(liquidity, dict) and liquidity.get("usable") is True:
        selected = _best_scenario(liquidity.get("scenarios"), notional)
        if selected is not None:
            return {
                "cost_pct": selected["cost_pct"],
                "method": "liquidity_cost",
                "depth_complete": True,
                "scenario_amount_usdt": _number(selected["scenario"].get("amount_usdt")),
                "fees": liquidity.get("fees"),
                "scenario": selected["scenario"],
            }

    book = source.get("book")
    bids = _levels(book.get("bids")) if isinstance(book, dict) else []
    asks = _levels(book.get("asks")) if isinstance(book, dict) else []
    depth_failure = None
    if bids and asks:
        report = round_trip_scenarios(bids, asks, [notional], fees=None)
        selected = _best_scenario(report.get("scenarios"), notional)
        if selected is not None:
            return {
                "cost_pct": selected["cost_pct"],
                "method": "order_book",
                "depth_complete": True,
                "scenario_amount_usdt": _number(selected["scenario"].get("amount_usdt")),
                "fees": source.get("fees"),
                "scenario": selected["scenario"],
            }
        scenarios = report.get("scenarios")
        if isinstance(scenarios, list) and scenarios and isinstance(scenarios[0], dict):
            depth_failure = {
                "execution_status": scenarios[0].get("execution_status"),
                "reason": scenarios[0].get("reason"),
            }

    spread_pct = _spread_pct(source, None)
    if spread_pct is not None:
        return {
            "cost_pct": spread_pct,
            "method": "spread_only",
            "depth_complete": False,
            "scenario_amount_usdt": None,
            "fees": source.get("fees"),
            "scenario": None,
            "depth_failure": depth_failure,
        }
    return None


def objective_move(early: Any) -> Optional[dict]:
    """Objectif structurel le plus proche, en pourcentage depuis le prix courant.

    `distance_pct` est déjà signé dans le sens du signal par le détecteur : une
    valeur positive est un objectif devant le prix.
    """
    if not isinstance(early, dict):
        return None
    objectives = early.get("objectives")
    if not isinstance(objectives, dict):
        return None
    for key in ("short_term", "swing"):
        item = objectives.get(key)
        if not isinstance(item, dict):
            continue
        move = _number(item.get("distance_pct"))
        if move is None:
            continue
        return {"move_pct": move, "level": _number(item.get("level")),
                "kind": item.get("kind"), "source": key}
    return None


def _fee_component(fees: Any) -> tuple[Optional[float], str]:
    """Frais A/R en pourcentage, uniquement si la provenance est authentifiée.

    Accepte une enveloppe brute (`pct` + provenance) comme un bloc déjà
    normalisé par le collecteur (`pct_per_side` + provenance). Dans les deux cas
    la signature HMAC est revérifiée : un simple drapeau `verified` ne suffit pas.
    """
    if not isinstance(fees, dict) or fees.get("verified") is not True:
        return None, "NOT_VERIFIED"
    side = _number(fees.get("pct_per_side"))
    if side is not None:
        if verify_fees_provenance(fees) == "VERIFIED":
            return 2.0 * side, "VERIFIED"
        return None, "NOT_VERIFIED"
    info = normalize_fees(fees)
    side = _number(info.get("pct_per_side"))
    if info.get("verified") is True and side is not None:
        return 2.0 * side, "VERIFIED"
    return None, "NOT_VERIFIED"


def _indeterminate(direction: Any, reason: str, notional: float) -> dict:
    return {
        "schema_version": 1,
        "read_only": True,
        "orders_sent": 0,
        "status": "INDETERMINE",
        "direction": direction,
        "notional_usdt": notional,
        "cost": None,
        "objective": None,
        "coverage_ratio": None,
        "net_edge_pct": None,
        "economic_validity": "INDETERMINE",
        "reason": reason,
        "provenance": [],
        "limits": _LIMITS,
    }


_LIMITS = [
    "Estimation statique sur des données publiques observées ; aucun ordre n'est envoyé.",
    "Le coût mesuré est un minorant tant que les frais ne sont pas authentifiés par provenance HMAC.",
    "Latence, rejets et changements de carnet entre collecte et exécution ne sont pas modélisés.",
    "Le seuil de couverture (>= 1) est un critère nécessaire, non une règle validée hors échantillon.",
    "Aucune probabilité de succès n'est déduite de la confiance du détecteur.",
]


def validate_economics(early: Any, payload: Any,
                       notional: Optional[float] = None) -> dict:
    """Compare le coût A/R mesuré au mouvement structurel visé.

    `payload` peut être la source MEXC seule ou l'instantané complet.
    Retourne toujours un bloc explicite ; jamais de valeur inventée.
    """
    source = resolve_source(payload)
    amount = _number(notional)
    if amount is None or amount <= 0:
        amount = DEFAULT_NOTIONAL_USDT
    direction = early.get("direction") if isinstance(early, dict) else None

    measured = measure_round_trip(source, amount)
    if measured is None:
        return _indeterminate(direction, "carnet et spread absents : coût non mesurable", amount)

    measured_cost = float(measured["cost_pct"])
    fees_pct, fees_status = _fee_component(measured.get("fees") or source.get("fees"))
    is_lower_bound = fees_pct is None or measured["method"] == "spread_only"

    total_cost = measured_cost + (fees_pct or 0.0)
    spread_pct = _spread_pct(source, measured.get("scenario"))
    # Décomposition exacte : le coût d'un aller-retour au sommet du carnet est
    # (ask - bid) / ask, alors que le spread publié est rapporté au mid. La
    # différence entre le coût mesuré et ce coût au sommet est l'impact de taille.
    slippage_pct = None
    if measured["method"] != "spread_only" and spread_pct is not None:
        best = source.get("best")
        top_cost = None
        if isinstance(best, dict):
            bid, ask = _number(best.get("bid")), _number(best.get("ask"))
            if bid and ask and ask > 0 and ask >= bid:
                top_cost = (ask - bid) / ask * 100
        if top_cost is None:
            top_cost = spread_pct / (1.0 + spread_pct / 200.0)
        if top_cost is not None:
            slippage_pct = max(0.0, measured_cost - top_cost)

    objective = objective_move(early)
    coverage: Optional[float] = None
    net_edge: Optional[float] = None
    validity = "INDETERMINE"
    reason = "objectif structurel absent : couverture non calculable"
    if direction not in DIRECTIONAL:
        reason = "aucune direction de signal : le coût est mesuré, l'objectif n'est pas directionnel"
    elif objective is None:
        reason = "objectif structurel absent : couverture non calculable"
    elif objective["move_pct"] <= 0:
        validity = "NON_COUVERT"
        reason = ("objectif structurel déjà atteint ou situé derrière le prix : "
                  "aucun mouvement à couvrir")
    elif total_cost <= 0:
        coverage = None
        reason = "coût mesuré nul : couverture non calculable sans hypothèse"
    else:
        coverage = objective["move_pct"] / total_cost
        net_edge = objective["move_pct"] - total_cost
        if coverage < MIN_COVERAGE_RATIO:
            validity = "NON_COUVERT"
            reason = (f"le mouvement visé ({objective['move_pct']:.3f} %) ne couvre pas "
                      f"le coût A/R ({total_cost:.3f} %) : couverture {coverage:.2f}x")
        elif is_lower_bound:
            validity = "COUVERT_MINORANT"
            reason = (f"le mouvement visé couvre le minorant de coût ({coverage:.2f}x) ; "
                      "le coût réel (frais non vérifiés ou profondeur non mesurée) "
                      "peut réduire cette marge")
        else:
            validity = "COUVERT"
            reason = (f"le mouvement visé couvre le coût A/R mesuré ({coverage:.2f}x), "
                      "frais vérifiés inclus")

    provenance = [
        f"coût: {measured['method']}" + (
            f" (scénario {measured['scenario_amount_usdt']:.0f} USDT)"
            if measured.get("scenario_amount_usdt") else ""),
        "profondeur: carnet public observé" if measured["depth_complete"]
        else ("profondeur: insuffisante pour le montant demandé "
              f"({measured.get('depth_failure', {}).get('reason') or 'non mesurée'})"
              if measured.get("depth_failure")
              else "profondeur: non mesurée (coût = spread seul, minorant)"),
        f"frais: {fees_status}" + ("" if fees_status == "VERIFIED"
                                   else " (exclus ; coût réel >= coût publié)"),
        "objectif: objectives." + objective["source"] if objective else "objectif: absent",
    ]

    return {
        "schema_version": 1,
        "read_only": True,
        "orders_sent": 0,
        "status": "OK" if measured["depth_complete"] else "PARTIEL",
        "direction": direction,
        "notional_usdt": amount,
        "cost": {
            "round_trip_pct": total_cost,
            "measured_ex_fees_pct": measured_cost,
            "spread_pct": spread_pct,
            "slippage_pct": slippage_pct,
            "fees_pct": fees_pct,
            "fees_status": fees_status,
            "method": measured["method"],
            "is_lower_bound": is_lower_bound,
            "depth_complete": measured["depth_complete"],
            "depth_failure": measured.get("depth_failure"),
        },
        "objective": objective,
        "coverage_ratio": coverage,
        "net_edge_pct": net_edge,
        "economic_validity": validity,
        "reason": reason,
        "provenance": provenance,
        "limits": _LIMITS,
    }

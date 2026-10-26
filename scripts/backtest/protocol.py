"""
Protocole d'evaluation hors echantillon : parametres figes.

Ce module est la source de verite unique du protocole. Il est lu par
`run_oos.py` et ne doit pas etre modifie apres l'examen des resultats
hors echantillon (cf. OOS_PROTOCOL.md).

Nothing here is tuned on the outcome: the significance criterion, the horizons,
the cost scenarios and the split are frozen before the out-of-sample run.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# 1. Separation chronologique
# --------------------------------------------------------------------------
IS_SHARE = 0.60           # part chronologique de conception (avant)
# --------------------------------------------------------------------------
# 2. Criteres de significatif (identiques au protocole v1.1 deja valide)
# --------------------------------------------------------------------------
CRITERION = "quantile"    # "quantile" (primaire) ou "sigma" (comparatif)
SECONDARY_CRITERION = "sigma"
MIN_HORIZONS_HIT = 2
# --------------------------------------------------------------------------
# 3. Scenarios de couts (figes)  -- cf. OOS_PROTOCOL.md section 3
# --------------------------------------------------------------------------
# Slippage observe sur le carnet du snapshot (300 USDT) :
#   MEXC 0,285 % (4 niveaux), KuCoin 0,185 % (3 niveaux).
# Frais NON verifies par le collecteur : traites en hypotheses, jamais affirmes.
SLIPPAGE_ONE_WAY = 0.00285
FEE_HYPOTHESES = (0.0010, 0.0015)

COST_SCENARIOS: dict[str, float] = {
    "S0_brut": 0.0,
    "S1_slippage_AR": 2 * SLIPPAGE_ONE_WAY,                 # 0,57 %
    "S2_frais_0.10_AR": 2 * SLIPPAGE_ONE_WAY + 2 * 0.0010,  # 0,77 %
    "S3_frais_0.15_AR": 2 * SLIPPAGE_ONE_WAY + 2 * 0.0015,  # 0,87 %
}
# --------------------------------------------------------------------------
# 4. Metriques
# --------------------------------------------------------------------------
DEDUP_WINDOW_MINUTES = 90
WARNING_WINDOW_HORIZON = 1     # index de l'horizon servant de fenetre d'avertissement
NULL_TEST_ITERATIONS = 2000
SIGNAL_STATUSES = ("ALERTE_PRÉCOCE", "CONFIRMATION", "INVALIDATION")
REFERENCE_REVERSAL_CRITERION = "quantile"   # phenomenon de marche : hors cout

#: Choix des horizons presentes par unite de temps (status_timeframe_matrix.py).
#: Pour chaque TF, on utilise les horizons d'indices 1 et 2 de la grille
#: (horizons_in_bars). C'est une CONVENTION DE PRESENTATION : elle ne vise pas
#: un optimum statistique et n'a pas ete validée par test. Les horizons retenus
#: sont (valeurs reelles de horizons_in_bars) :
#:   15m -> 6h (24 barres) et 24h (96 barres)
#:   1h  -> 6h (6 barres) et 24h (24 barres)
#:   4h  -> 72h (18 barres) et 168h (42 barres)
#:   1d  -> 120h (5 barres) et 240h (10 barres)
#: Le 1er horizon (indice 0) n'est pas utilises car trop proche du signal
#: pour mesurer un mouvement dirige fiable.
#: Aucun de ces horizons n'a ete choisi pour maximiser un score : ce sont les
#: memes valeurs que celles du tableau de reference du protocole OOS-1.2.
HORIZON_PRESENTATION_INDICES = (1, 2)

PROTOCOL: dict[str, Any] = {
    "version": "OOS-1.2",
    "frozen": True,
    "is_share": IS_SHARE,
    "criterion": CRITERION,
    "secondary_criterion": SECONDARY_CRITERION,
    "min_horizons_hit": MIN_HORIZONS_HIT,
    "require_positive_net_move": True,
    "cost_applied_once": True,
    "cost_scenarios": COST_SCENARIOS,
    "slippage_one_way": SLIPPAGE_ONE_WAY,
    "fee_hypotheses": list(FEE_HYPOTHESES),
    "dedup_window_minutes": DEDUP_WINDOW_MINUTES,
    "null_test_iterations": NULL_TEST_ITERATIONS,
    "signal_statuses": list(SIGNAL_STATUSES),
    "revision_note": (
        "Revision v1.0 -> v1.1, appliquee AVANT toute lecture de resultat hors "
        "echantillon et avant le run unique. Motif : le seuil q90 des mouvements "
        "avant peut etre NEGATIF en regime baissier ; sans condition de "
        "positivite, un mouvement baissier pouvait etre qualifie de "
        "'significatif haussier' et les deux directions pouvaient etre "
        "significatives simultanement, ce qui faussait la reference. "
        "Revision v1.1 -> v1.2, appliquee apres la lecture des resultats de "
        "CONCEPTION (IS) uniquement, et NON pour ameliorer une performance : "
        "le cout etait applique deux fois (comparaison au seuil ET test de "
        "positivite), ce que la regle de non-double-compte du protocole "
        "interdit. Le seuil est une propriete du marche et se compare au "
        "mouvement BRUT ; le cout est une propriete du trade et sert a exiger "
        "que la performance nette soit positive. La correction s'applique "
        "IDENTIQUEMENT aux deux moteurs : elle ne favorise aucun des deux."
    ),
    "note": ("Regle de non-double-compte : le meme jeu de seuils sert au "
             "detecteur et a la reference de comparaison, pour un segment donne ; "
             "le cout n'entre qu'une fois, dans la condition de performance "
             "nette. Les retournements de reference sont mesures HORS cout "
             "(phenomene de marche)."),
}

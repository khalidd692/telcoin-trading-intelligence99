# ÉVALUATION HORS ÉCHANTILLON — ANCIEN MOTEUR vs MOTEUR v2

**Protocole** : OOS-1.2 (figé) · **coupure** : 2026-04-16T11:36:00Z (conception = 60% chronologique)
**Données** : kucoin TEL-USDT · axe 15m 2024-03-27T11:45:00Z → 2026-10-20T23:30:00Z
**Généré** : 2026-10-21T13:23:41+00:00

> Les chiffres ci-dessous proviennent exclusivement de `oos_results.json`. La séparation conception / validation est stricte : aucun paramètre n'a été modifié après lecture des résultats de validation.

## 0. Révision du protocole

Revision v1.0 -> v1.1, appliquee AVANT toute lecture de resultat hors echantillon et avant le run unique. Motif : le seuil q90 des mouvements avant peut etre NEGATIF en regime baissier ; sans condition de positivite, un mouvement baissier pouvait etre qualifie de 'significatif haussier' et les deux directions pouvaient etre significatives simultanement, ce qui faussait la reference. Revision v1.1 -> v1.2, appliquee apres la lecture des resultats de CONCEPTION (IS) uniquement, et NON pour ameliorer une performance : le cout etait applique deux fois (comparaison au seuil ET test de positivite), ce que la regle de non-double-compte du protocole interdit. Le seuil est une propriete du marche et se compare au mouvement BRUT ; le cout est une propriete du trade et sert a exiger que la performance nette soit positive. La correction s'applique IDENTIQUEMENT aux deux moteurs : elle ne favorise aucun des deux.

## 1. Répartition

| Moteur | Unité | Segment | Barres | Épisodes | Densité | Exploitables |
|---|---|---|---|---|---|---|
| ancien | 15m | NEW | 44977 | 7184 | 15.97 % | 0 |
| ancien | 15m | IS1 | 13536 | 1747 | 12.91 % | 0 |
| ancien | 15m | IS2 | 13440 | 1718 | 12.78 % | 0 |
| ancien | 15m | OOS | 18047 | 2715 | 15.04 % | 0 |
| ancien | 1h | NEW | 0 | 0 | n/a | 0 |
| ancien | 1h | IS1 | 0 | 0 | n/a | 0 |
| ancien | 1h | IS2 | 1487 | 273 | 18.36 % | 0 |
| ancien | 1h | OOS | 4513 | 1090 | 24.15 % | 0 |
| ancien | 4h | NEW | 2814 | 892 | 31.70 % | 0 |
| ancien | 4h | IS1 | 846 | 214 | 25.30 % | 0 |
| ancien | 4h | IS2 | 840 | 180 | 21.43 % | 0 |
| ancien | 4h | OOS | 1129 | 326 | 28.88 % | 0 |
| ancien | 1d | NEW | 469 | 130 | 27.72 % | 0 |
| ancien | 1d | IS1 | 141 | 33 | 23.40 % | 0 |
| ancien | 1d | IS2 | 140 | 26 | 18.57 % | 0 |
| ancien | 1d | OOS | 189 | 38 | 20.11 % | 0 |
| ancien | 1w | NEW | 67 | 18 | 26.87 % | 0 |
| ancien | 1w | IS1 | 20 | 5 | 25.00 % | 0 |
| ancien | 1w | IS2 | 20 | 3 | 15.00 % | 0 |
| ancien | 1w | OOS | 27 | 4 | 14.81 % | 0 |
| ancien | 1M | NEW | 16 | 4 | 25.00 % | 0 |
| ancien | 1M | IS1 | 4 | 2 | 50.00 % | 0 |
| ancien | 1M | IS2 | 5 | 0 | 0.00 % | 0 |
| ancien | 1M | OOS | 6 | 0 | 0.00 % | 0 |
| v2 | 15m | NEW | 44977 | 2540 | 5.65 % | 62 |
| v2 | 15m | IS1 | 13536 | 967 | 7.14 % | 24 |
| v2 | 15m | IS2 | 13440 | 867 | 6.45 % | 23 |
| v2 | 15m | OOS | 18047 | 1127 | 6.24 % | 78 |
| v2 | 1h | NEW | 0 | 0 | n/a | 0 |
| v2 | 1h | IS1 | 0 | 0 | n/a | 0 |
| v2 | 1h | IS2 | 1487 | 240 | 16.14 % | 5 |
| v2 | 1h | OOS | 4513 | 792 | 17.55 % | 61 |
| v2 | 4h | NEW | 2814 | 663 | 23.56 % | 17 |
| v2 | 4h | IS1 | 846 | 248 | 29.31 % | 4 |
| v2 | 4h | IS2 | 840 | 222 | 26.43 % | 7 |
| v2 | 4h | OOS | 1129 | 299 | 26.48 % | 24 |
| v2 | 1d | NEW | 469 | 104 | 22.17 % | 5 |
| v2 | 1d | IS1 | 141 | 35 | 24.82 % | 0 |
| v2 | 1d | IS2 | 140 | 38 | 27.14 % | 0 |
| v2 | 1d | OOS | 189 | 44 | 23.28 % | 4 |
| v2 | 1w | NEW | 67 | 16 | 23.88 % | 0 |
| v2 | 1w | IS1 | 20 | 5 | 25.00 % | 0 |
| v2 | 1w | IS2 | 20 | 11 | 55.00 % | 0 |
| v2 | 1w | OOS | 27 | 7 | 25.93 % | 0 |
| v2 | 1M | NEW | 16 | 4 | 25.00 % | 0 |
| v2 | 1M | IS1 | 4 | 2 | 50.00 % | 0 |
| v2 | 1M | IS2 | 5 | 2 | 40.00 % | 0 |
| v2 | 1M | OOS | 6 | 0 | 0.00 % | 0 |

## 2.15m — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 4636 | 26.88 % | 27.93 % | 0.96 | [25.6 % ; 28.2 %] | 3390 | 0.054 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 4636 | 25.86 % | 26.67 % | 0.97 | [24.6 % ; 27.1 %] | 3437 | 0.101 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 4636 | 25.32 % | 26.04 % | 0.97 | [24.1 % ; 26.6 %] | 3462 | 0.140 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 4636 | 24.98 % | 25.70 % | 0.97 | [23.8 % ; 26.2 %] | 3478 | 0.141 |
| CONFIRMATION | brut | 0 | n/a | 27.92 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 26.66 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 26.03 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 25.68 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 898 | 31.51 % | 27.90 % | 1.13 | [28.6 % ; 34.6 %] | 615 | 0.993 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 898 | 29.29 % | 26.64 % | 1.10 | [26.4 % ; 32.3 %] | 635 | 0.968 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 898 | 27.95 % | 26.00 % | 1.08 | [25.1 % ; 31.0 %] | 647 | 0.911 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 898 | 27.17 % | 25.65 % | 1.06 | [24.4 % ; 30.2 %] | 654 | 0.857 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 27.92 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 26.66 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 26.03 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 25.68 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 4636 | 26.88 % | 27.93 % | 0.96 | [25.6 % ; 28.2 %] | 3390 | 0.054 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 4636 | 25.86 % | 26.67 % | 0.97 | [24.6 % ; 27.1 %] | 3437 | 0.101 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 4636 | 25.32 % | 26.04 % | 0.97 | [24.1 % ; 26.6 %] | 3462 | 0.140 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 4636 | 24.98 % | 25.70 % | 0.97 | [23.8 % ; 26.2 %] | 3478 | 0.141 |

- **Retournements de référence** : 229 au total, **139 détectés à l'avance**, **90 manqués** (détection 60.70 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 135.0 min · 78.4 % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1531 | 25.67 % | 26.99 % | 0.95 | [23.5 % ; 27.9 %] | 1138 | 0.126 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1531 | 24.30 % | 25.71 % | 0.95 | [22.2 % ; 26.5 %] | 1159 | 0.104 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1531 | 23.97 % | 25.02 % | 0.96 | [21.9 % ; 26.2 %] | 1164 | 0.167 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1531 | 23.71 % | 24.71 % | 0.96 | [21.6 % ; 25.9 %] | 1168 | 0.172 |
| CONFIRMATION | brut | 0 | n/a | 26.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 25.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 26.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 25.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 26.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 25.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.56 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 1531 | 25.67 % | 26.99 % | 0.95 | [23.5 % ; 27.9 %] | 1138 | 0.126 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 1531 | 24.30 % | 25.71 % | 0.95 | [22.2 % ; 26.5 %] | 1159 | 0.104 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 1531 | 23.97 % | 25.02 % | 0.96 | [21.9 % ; 26.2 %] | 1164 | 0.167 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 1531 | 23.71 % | 24.71 % | 0.96 | [21.6 % ; 25.9 %] | 1168 | 0.172 |

- **Retournements de référence** : 66 au total, **45 détectés à l'avance**, **21 manqués** (détection 68.18 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 75.0 min · 71.1 % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1486 | 24.02 % | 27.80 % | 0.86 | [21.9 % ; 26.3 %] | 1129 | 0.000 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1486 | 22.48 % | 26.04 % | 0.86 | [20.4 % ; 24.7 %] | 1152 | 0.001 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1486 | 21.47 % | 25.03 % | 0.86 | [19.5 % ; 23.6 %] | 1167 | 0.001 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1486 | 21.00 % | 24.53 % | 0.86 | [19.0 % ; 23.1 %] | 1174 | 0.001 |
| CONFIRMATION | brut | 0 | n/a | 27.74 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 25.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.83 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 27.74 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 25.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.83 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 27.74 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 25.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.83 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 1486 | 24.02 % | 27.80 % | 0.86 | [21.9 % ; 26.3 %] | 1129 | 0.000 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 1486 | 22.48 % | 26.04 % | 0.86 | [20.4 % ; 24.7 %] | 1152 | 0.001 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 1486 | 21.47 % | 25.03 % | 0.86 | [19.5 % ; 23.6 %] | 1167 | 0.001 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 1486 | 21.00 % | 24.53 % | 0.86 | [19.0 % ; 23.1 %] | 1174 | 0.001 |

- **Retournements de référence** : 70 au total, **47 détectés à l'avance**, **23 manqués** (détection 67.14 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 75.0 min · 72.3 % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1791 | 26.47 % | 28.51 % | 0.93 | [24.5 % ; 28.6 %] | 1317 | 0.037 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1791 | 24.90 % | 26.59 % | 0.94 | [23.0 % ; 27.0 %] | 1345 | 0.062 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1791 | 24.23 % | 25.48 % | 0.95 | [22.3 % ; 26.3 %] | 1357 | 0.131 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1791 | 23.62 % | 24.74 % | 0.95 | [21.7 % ; 25.6 %] | 1368 | 0.153 |
| CONFIRMATION | brut | 0 | n/a | 28.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 26.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 25.16 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 281 | 28.47 % | 28.26 % | 1.01 | [23.5 % ; 34.0 %] | 201 | 0.553 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 281 | 24.91 % | 26.23 % | 0.95 | [20.2 % ; 30.3 %] | 211 | 0.317 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 281 | 23.84 % | 25.07 % | 0.95 | [19.2 % ; 29.2 %] | 214 | 0.327 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 281 | 22.42 % | 24.32 % | 0.92 | [17.9 % ; 27.6 %] | 218 | 0.226 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 28.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 26.31 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 25.16 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 1791 | 26.47 % | 28.51 % | 0.93 | [24.5 % ; 28.6 %] | 1317 | 0.037 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 1791 | 24.90 % | 26.59 % | 0.94 | [23.0 % ; 27.0 %] | 1345 | 0.062 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 1791 | 24.23 % | 25.48 % | 0.95 | [22.3 % ; 26.3 %] | 1357 | 0.131 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 1791 | 23.62 % | 24.74 % | 0.95 | [21.7 % ; 25.6 %] | 1368 | 0.153 |

- **Retournements de référence** : 93 au total, **50 détectés à l'avance**, **43 manqués** (détection 53.76 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 37.5 min · 60.0 % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1146 | 25.92 % | 27.89 % | 0.93 | [23.5 % ; 28.5 %] | 849 | 0.085 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1146 | 24.96 % | 26.61 % | 0.94 | [22.5 % ; 27.5 %] | 860 | 0.117 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1146 | 24.43 % | 25.97 % | 0.94 | [22.0 % ; 27.0 %] | 866 | 0.140 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1146 | 23.73 % | 25.62 % | 0.93 | [21.4 % ; 26.3 %] | 874 | 0.087 |
| CONFIRMATION | brut | 964 | 29.15 % | 27.88 % | 1.05 | [26.4 % ; 32.1 %] | 683 | 0.809 |
| CONFIRMATION | A/R slippage 0,57 % | 964 | 27.80 % | 26.60 % | 1.05 | [25.1 % ; 30.7 %] | 696 | 0.797 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 964 | 27.28 % | 25.96 % | 1.05 | [24.6 % ; 30.2 %] | 701 | 0.824 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 964 | 26.97 % | 25.61 % | 1.05 | [24.3 % ; 29.9 %] | 704 | 0.834 |
| INVALIDATION (mesuré en sens inverse) | brut | 430 | 25.35 % | 27.98 % | 0.91 | [21.5 % ; 29.7 %] | 321 | 0.130 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 430 | 24.65 % | 26.77 % | 0.92 | [20.8 % ; 28.9 %] | 324 | 0.185 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 430 | 24.42 % | 26.14 % | 0.93 | [20.6 % ; 28.7 %] | 325 | 0.234 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 430 | 24.42 % | 25.81 % | 0.95 | [20.6 % ; 28.7 %] | 325 | 0.283 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 62 | 33.87 % | 27.90 % | 1.21 | [23.3 % ; 46.3 %] | 41 | 0.886 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 62 | 33.87 % | 26.63 % | 1.27 | [23.3 % ; 46.3 %] | 41 | 0.921 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 62 | 33.87 % | 25.99 % | 1.30 | [23.3 % ; 46.3 %] | 41 | 0.935 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 62 | 33.87 % | 25.64 % | 1.32 | [23.3 % ; 46.3 %] | 41 | 0.945 |
| TOUS (alerte + confirmation) | brut | 2110 | 27.39 % | 27.89 % | 0.98 | [25.5 % ; 29.3 %] | 1532 | 0.314 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 2110 | 26.26 % | 26.61 % | 0.99 | [24.4 % ; 28.2 %] | 1556 | 0.360 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 2110 | 25.73 % | 25.96 % | 0.99 | [23.9 % ; 27.6 %] | 1567 | 0.412 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 2110 | 25.21 % | 25.61 % | 0.98 | [23.4 % ; 27.1 %] | 1578 | 0.350 |

- **Retournements de référence** : 229 au total, **75 détectés à l'avance**, **154 manqués** (détection 32.75 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 75.0 min · 89.3 % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 422 | 24.64 % | 26.58 % | 0.93 | [20.8 % ; 29.0 %] | 318 | 0.199 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 422 | 23.22 % | 25.26 % | 0.92 | [19.4 % ; 27.5 %] | 324 | 0.181 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 422 | 21.80 % | 24.56 % | 0.89 | [18.1 % ; 26.0 %] | 330 | 0.102 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 422 | 21.33 % | 24.25 % | 0.88 | [17.7 % ; 25.5 %] | 332 | 0.086 |
| CONFIRMATION | brut | 366 | 26.23 % | 26.55 % | 0.99 | [22.0 % ; 31.0 %] | 270 | 0.452 |
| CONFIRMATION | A/R slippage 0,57 % | 366 | 24.04 % | 25.22 % | 0.95 | [19.9 % ; 28.7 %] | 278 | 0.303 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 366 | 23.77 % | 24.53 % | 0.97 | [19.7 % ; 28.4 %] | 279 | 0.381 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 366 | 23.50 % | 24.21 % | 0.97 | [19.4 % ; 28.1 %] | 280 | 0.386 |
| INVALIDATION (mesuré en sens inverse) | brut | 179 | 20.11 % | 27.50 % | 0.73 | [14.9 % ; 26.6 %] | 143 | 0.013 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 179 | 19.55 % | 26.27 % | 0.74 | [14.4 % ; 26.0 %] | 144 | 0.026 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 179 | 19.55 % | 25.60 % | 0.76 | [14.4 % ; 26.0 %] | 144 | 0.043 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 179 | 19.55 % | 25.30 % | 0.77 | [14.4 % ; 26.0 %] | 144 | 0.049 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 24 | 45.83 % | 27.17 % | 1.69 | [27.9 % ; 64.9 %] | 13 | 0.985 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 24 | 37.50 % | 25.91 % | 1.45 | [21.2 % ; 57.3 %] | 15 | 0.929 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 24 | 37.50 % | 25.22 % | 1.49 | [21.2 % ; 57.3 %] | 15 | 0.940 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 24 | 37.50 % | 24.92 % | 1.50 | [21.2 % ; 57.3 %] | 15 | 0.944 |
| TOUS (alerte + confirmation) | brut | 788 | 25.38 % | 26.56 % | 0.96 | [22.5 % ; 28.5 %] | 588 | 0.236 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 788 | 23.60 % | 25.24 % | 0.94 | [20.8 % ; 26.7 %] | 602 | 0.145 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 788 | 22.72 % | 24.55 % | 0.93 | [19.9 % ; 25.8 %] | 609 | 0.111 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 788 | 22.34 % | 24.23 % | 0.92 | [19.6 % ; 25.4 %] | 612 | 0.102 |

- **Retournements de référence** : 66 au total, **30 détectés à l'avance**, **36 manqués** (détection 45.45 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 75.0 min · 83.3 % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 380 | 23.68 % | 27.70 % | 0.86 | [19.7 % ; 28.2 %] | 290 | 0.043 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 380 | 23.16 % | 25.77 % | 0.90 | [19.2 % ; 27.7 %] | 292 | 0.138 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 380 | 22.89 % | 24.70 % | 0.93 | [19.0 % ; 27.4 %] | 293 | 0.235 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 380 | 22.37 % | 24.17 % | 0.93 | [18.5 % ; 26.8 %] | 295 | 0.235 |
| CONFIRMATION | brut | 314 | 24.84 % | 27.70 % | 0.90 | [20.4 % ; 29.9 %] | 236 | 0.144 |
| CONFIRMATION | A/R slippage 0,57 % | 314 | 22.61 % | 25.77 % | 0.88 | [18.3 % ; 27.6 %] | 243 | 0.112 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 314 | 21.34 % | 24.69 % | 0.86 | [17.2 % ; 26.2 %] | 247 | 0.089 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 314 | 21.02 % | 24.16 % | 0.87 | [16.9 % ; 25.9 %] | 248 | 0.108 |
| INVALIDATION (mesuré en sens inverse) | brut | 173 | 26.59 % | 27.89 % | 0.95 | [20.6 % ; 33.6 %] | 127 | 0.376 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 173 | 24.28 % | 26.27 % | 0.92 | [18.5 % ; 31.2 %] | 131 | 0.302 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 173 | 23.12 % | 25.32 % | 0.91 | [17.5 % ; 29.9 %] | 133 | 0.274 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 173 | 22.54 % | 24.84 % | 0.91 | [17.0 % ; 29.3 %] | 134 | 0.262 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 23 | 26.09 % | 27.84 % | 0.94 | [12.5 % ; 46.5 %] | 17 | 0.530 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 23 | 26.09 % | 26.13 % | 1.00 | [12.5 % ; 46.5 %] | 17 | 0.591 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 23 | 26.09 % | 25.14 % | 1.04 | [12.5 % ; 46.5 %] | 17 | 0.633 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 23 | 26.09 % | 24.65 % | 1.06 | [12.5 % ; 46.5 %] | 17 | 0.657 |
| TOUS (alerte + confirmation) | brut | 694 | 24.21 % | 27.70 % | 0.87 | [21.2 % ; 27.5 %] | 526 | 0.018 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 694 | 22.91 % | 25.77 % | 0.89 | [19.9 % ; 26.2 %] | 535 | 0.043 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 694 | 22.19 % | 24.70 % | 0.90 | [19.3 % ; 25.4 %] | 540 | 0.069 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 694 | 21.76 % | 24.16 % | 0.90 | [18.8 % ; 25.0 %] | 543 | 0.074 |

- **Retournements de référence** : 70 au total, **23 détectés à l'avance**, **47 manqués** (détection 32.86 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 75.0 min · 91.3 % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 464 | 25.22 % | 28.07 % | 0.90 | [21.5 % ; 29.4 %] | 347 | 0.095 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 464 | 22.63 % | 25.97 % | 0.87 | [19.1 % ; 26.7 %] | 359 | 0.058 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 464 | 20.91 % | 24.77 % | 0.84 | [17.5 % ; 24.8 %] | 367 | 0.032 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 464 | 20.69 % | 24.02 % | 0.86 | [17.3 % ; 24.6 %] | 368 | 0.053 |
| CONFIRMATION | brut | 457 | 23.85 % | 28.04 % | 0.85 | [20.2 % ; 28.0 %] | 348 | 0.021 |
| CONFIRMATION | A/R slippage 0,57 % | 457 | 21.66 % | 25.93 % | 0.84 | [18.1 % ; 25.7 %] | 358 | 0.017 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 457 | 20.13 % | 24.72 % | 0.81 | [16.7 % ; 24.0 %] | 365 | 0.015 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 457 | 19.47 % | 23.97 % | 0.81 | [16.1 % ; 23.4 %] | 368 | 0.013 |
| INVALIDATION (mesuré en sens inverse) | brut | 206 | 33.50 % | 28.70 % | 1.17 | [27.4 % ; 40.2 %] | 137 | 0.949 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 206 | 30.58 % | 26.86 % | 1.14 | [24.7 % ; 37.2 %] | 143 | 0.901 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 206 | 29.13 % | 25.78 % | 1.13 | [23.3 % ; 35.7 %] | 146 | 0.882 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 206 | 27.67 % | 25.06 % | 1.10 | [22.0 % ; 34.1 %] | 149 | 0.821 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 78 | 33.33 % | 27.91 % | 1.19 | [23.9 % ; 44.4 %] | 52 | 0.885 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 78 | 32.05 % | 25.74 % | 1.25 | [22.7 % ; 43.0 %] | 53 | 0.919 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 78 | 30.77 % | 24.51 % | 1.26 | [21.6 % ; 41.7 %] | 54 | 0.918 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 78 | 30.77 % | 23.75 % | 1.30 | [21.6 % ; 41.7 %] | 54 | 0.940 |
| TOUS (alerte + confirmation) | brut | 921 | 24.54 % | 28.06 % | 0.87 | [21.9 % ; 27.4 %] | 695 | 0.011 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 921 | 22.15 % | 25.95 % | 0.85 | [19.6 % ; 24.9 %] | 717 | 0.004 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 921 | 20.52 % | 24.74 % | 0.83 | [18.0 % ; 23.2 %] | 732 | 0.002 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 921 | 20.09 % | 23.99 % | 0.84 | [17.6 % ; 22.8 %] | 736 | 0.003 |

- **Retournements de référence** : 93 au total, **33 détectés à l'avance**, **60 manqués** (détection 35.48 %) — fenêtre d'avertissement : 24 bougies.
- **Délai d'avance** : médiane 60.0 min · 87.9 % des détections précèdent l'entrée plausible.

## 2.1h — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 239 | 5.44 % | 10.61 % | 0.51 | [3.2 % ; 9.1 %] | 226 | 0.003 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 239 | 5.44 % | 10.53 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.004 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 239 | 5.44 % | 10.48 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.004 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 239 | 5.44 % | 10.45 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.005 |
| CONFIRMATION | brut | 0 | n/a | 10.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 10.69 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 10.63 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 10.59 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 10.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 10.69 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 10.63 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 10.59 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 10.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 10.69 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 10.63 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 10.59 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 239 | 5.44 % | 10.61 % | 0.51 | [3.2 % ; 9.1 %] | 226 | 0.003 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 239 | 5.44 % | 10.53 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.004 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 239 | 5.44 % | 10.48 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.004 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 239 | 5.44 % | 10.45 % | 0.52 | [3.2 % ; 9.1 %] | 226 | 0.005 |

- **Retournements de référence** : 20 au total, **4 détectés à l'avance**, **16 manqués** (détection 20.00 %) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane 60.0 min · 75.0 % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 737 | 15.33 % | 15.36 % | 1.00 | [12.9 % ; 18.1 %] | 624 | 0.526 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 737 | 15.20 % | 15.18 % | 1.00 | [12.8 % ; 18.0 %] | 625 | 0.543 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 737 | 15.06 % | 15.06 % | 1.00 | [12.7 % ; 17.8 %] | 626 | 0.531 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 737 | 14.93 % | 14.93 % | 1.00 | [12.5 % ; 17.7 %] | 627 | 0.529 |
| CONFIRMATION | brut | 0 | n/a | 15.34 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 15.13 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 15.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 14.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 92 | 18.48 % | 15.35 % | 1.20 | [11.9 % ; 27.6 %] | 75 | 0.833 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 92 | 18.48 % | 15.14 % | 1.22 | [11.9 % ; 27.6 %] | 75 | 0.847 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 92 | 18.48 % | 15.01 % | 1.23 | [11.9 % ; 27.6 %] | 75 | 0.855 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 92 | 18.48 % | 14.88 % | 1.24 | [11.9 % ; 27.6 %] | 75 | 0.865 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 15.34 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 15.13 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 15.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 14.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 737 | 15.33 % | 15.36 % | 1.00 | [12.9 % ; 18.1 %] | 624 | 0.526 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 737 | 15.20 % | 15.18 % | 1.00 | [12.8 % ; 18.0 %] | 625 | 0.543 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 737 | 15.06 % | 15.06 % | 1.00 | [12.7 % ; 17.8 %] | 626 | 0.531 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 737 | 14.93 % | 14.93 % | 1.00 | [12.5 % ; 17.7 %] | 627 | 0.529 |

- **Retournements de référence** : 51 au total, **19 détectés à l'avance**, **32 manqués** (détection 37.25 %) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane 180.0 min · 63.2 % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 93 | 9.68 % | 10.73 % | 0.90 | [5.2 % ; 17.4 %] | 84 | 0.454 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 93 | 9.68 % | 10.64 % | 0.91 | [5.2 % ; 17.4 %] | 84 | 0.468 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 93 | 9.68 % | 10.57 % | 0.92 | [5.2 % ; 17.4 %] | 84 | 0.474 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 93 | 9.68 % | 10.54 % | 0.92 | [5.2 % ; 17.4 %] | 84 | 0.477 |
| CONFIRMATION | brut | 98 | 7.14 % | 10.88 % | 0.66 | [3.5 % ; 14.0 %] | 91 | 0.157 |
| CONFIRMATION | A/R slippage 0,57 % | 98 | 7.14 % | 10.77 % | 0.66 | [3.5 % ; 14.0 %] | 91 | 0.163 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 98 | 7.14 % | 10.69 % | 0.67 | [3.5 % ; 14.0 %] | 91 | 0.167 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 98 | 7.14 % | 10.66 % | 0.67 | [3.5 % ; 14.0 %] | 91 | 0.172 |
| INVALIDATION (mesuré en sens inverse) | brut | 49 | 18.37 % | 10.54 % | 1.74 | [10.0 % ; 31.4 %] | 40 | 0.969 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 49 | 18.37 % | 10.47 % | 1.75 | [10.0 % ; 31.4 %] | 40 | 0.970 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 49 | 18.37 % | 10.42 % | 1.76 | [10.0 % ; 31.4 %] | 40 | 0.971 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 49 | 18.37 % | 10.40 % | 1.77 | [10.0 % ; 31.4 %] | 40 | 0.971 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 5 | 0.00 % | 11.30 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.567 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 5 | 0.00 % | 11.14 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.574 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 5 | 0.00 % | 11.03 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.577 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 5 | 0.00 % | 10.98 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.581 |
| TOUS (alerte + confirmation) | brut | 191 | 8.38 % | 10.81 % | 0.78 | [5.2 % ; 13.2 %] | 175 | 0.173 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 191 | 8.38 % | 10.70 % | 0.78 | [5.2 % ; 13.2 %] | 175 | 0.183 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 191 | 8.38 % | 10.64 % | 0.79 | [5.2 % ; 13.2 %] | 175 | 0.192 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 191 | 8.38 % | 10.60 % | 0.79 | [5.2 % ; 13.2 %] | 175 | 0.197 |

- **Retournements de référence** : 20 au total, **2 détectés à l'avance**, **18 manqués** (détection 10.00 %) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane 240.0 min · 100.0 % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 303 | 14.19 % | 15.32 % | 0.93 | [10.7 % ; 18.6 %] | 260 | 0.329 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 303 | 13.86 % | 15.08 % | 0.92 | [10.4 % ; 18.2 %] | 261 | 0.316 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 303 | 13.86 % | 14.92 % | 0.93 | [10.4 % ; 18.2 %] | 261 | 0.338 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 303 | 13.86 % | 14.78 % | 0.94 | [10.4 % ; 18.2 %] | 261 | 0.368 |
| CONFIRMATION | brut | 345 | 12.17 % | 15.32 % | 0.79 | [9.1 % ; 16.0 %] | 303 | 0.069 |
| CONFIRMATION | A/R slippage 0,57 % | 345 | 11.88 % | 15.08 % | 0.79 | [8.9 % ; 15.7 %] | 304 | 0.067 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 345 | 11.88 % | 14.93 % | 0.80 | [8.9 % ; 15.7 %] | 304 | 0.074 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 345 | 11.88 % | 14.78 % | 0.80 | [8.9 % ; 15.7 %] | 304 | 0.079 |
| INVALIDATION (mesuré en sens inverse) | brut | 144 | 19.44 % | 15.38 % | 1.26 | [13.8 % ; 26.7 %] | 116 | 0.930 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 144 | 19.44 % | 15.22 % | 1.28 | [13.8 % ; 26.7 %] | 116 | 0.938 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 144 | 19.44 % | 15.12 % | 1.29 | [13.8 % ; 26.7 %] | 116 | 0.944 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 144 | 19.44 % | 15.01 % | 1.30 | [13.8 % ; 26.7 %] | 116 | 0.948 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 61 | 22.95 % | 15.30 % | 1.50 | [14.2 % ; 34.9 %] | 47 | 0.964 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 61 | 22.95 % | 15.03 % | 1.53 | [14.2 % ; 34.9 %] | 47 | 0.970 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 61 | 22.95 % | 14.86 % | 1.54 | [14.2 % ; 34.9 %] | 47 | 0.971 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 61 | 22.95 % | 14.70 % | 1.56 | [14.2 % ; 34.9 %] | 47 | 0.975 |
| TOUS (alerte + confirmation) | brut | 648 | 13.12 % | 15.32 % | 0.86 | [10.7 % ; 15.9 %] | 563 | 0.073 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 648 | 12.81 % | 15.08 % | 0.85 | [10.5 % ; 15.6 %] | 565 | 0.066 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 648 | 12.81 % | 14.92 % | 0.86 | [10.5 % ; 15.6 %] | 565 | 0.076 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 648 | 12.81 % | 14.78 % | 0.87 | [10.5 % ; 15.6 %] | 565 | 0.093 |

- **Retournements de référence** : 51 au total, **9 détectés à l'avance**, **42 manqués** (détection 17.65 %) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane 180.0 min · 88.9 % des détections précèdent l'entrée plausible.

## 2.4h — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 559 | 24.51 % | 23.03 % | 1.06 | [21.1 % ; 28.2 %] | 422 | 0.808 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 559 | 24.33 % | 22.90 % | 1.06 | [21.0 % ; 28.1 %] | 423 | 0.799 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 559 | 24.33 % | 22.85 % | 1.06 | [21.0 % ; 28.1 %] | 423 | 0.809 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 559 | 24.33 % | 22.83 % | 1.07 | [21.0 % ; 28.1 %] | 423 | 0.812 |
| CONFIRMATION | brut | 0 | n/a | 23.05 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 22.92 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 22.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 22.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 83 | 22.89 % | 23.01 % | 0.99 | [15.2 % ; 33.0 %] | 64 | 0.564 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 83 | 22.89 % | 22.89 % | 1.00 | [15.2 % ; 33.0 %] | 64 | 0.575 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 83 | 22.89 % | 22.84 % | 1.00 | [15.2 % ; 33.0 %] | 64 | 0.579 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 83 | 22.89 % | 22.82 % | 1.00 | [15.2 % ; 33.0 %] | 64 | 0.580 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 23.05 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 22.92 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 22.87 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 22.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 559 | 24.51 % | 23.03 % | 1.06 | [21.1 % ; 28.2 %] | 422 | 0.808 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 559 | 24.33 % | 22.90 % | 1.06 | [21.0 % ; 28.1 %] | 423 | 0.799 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 559 | 24.33 % | 22.85 % | 1.06 | [21.0 % ; 28.1 %] | 423 | 0.809 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 559 | 24.33 % | 22.83 % | 1.07 | [21.0 % ; 28.1 %] | 423 | 0.812 |

- **Retournements de référence** : 18 au total, **13 détectés à l'avance**, **5 manqués** (détection 72.22 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 720.0 min · 69.2 % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 196 | 18.37 % | 25.14 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.011 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 196 | 18.37 % | 25.08 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.012 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 196 | 18.37 % | 25.02 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.013 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 196 | 18.37 % | 25.02 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.013 |
| CONFIRMATION | brut | 0 | n/a | 25.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 24.94 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 25.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 24.94 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 25.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 24.94 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 24.88 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 196 | 18.37 % | 25.14 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.011 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 196 | 18.37 % | 25.08 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.012 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 196 | 18.37 % | 25.02 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.013 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 196 | 18.37 % | 25.02 % | 0.73 | [13.6 % ; 24.4 %] | 160 | 0.013 |

- **Retournements de référence** : 6 au total, **2 détectés à l'avance**, **4 manqués** (détection 33.33 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 2040.0 min · 100.0 % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 164 | 22.56 % | 17.87 % | 1.26 | [16.8 % ; 29.5 %] | 127 | 0.944 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 164 | 22.56 % | 17.70 % | 1.27 | [16.8 % ; 29.5 %] | 127 | 0.950 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 164 | 22.56 % | 17.53 % | 1.29 | [16.8 % ; 29.5 %] | 127 | 0.957 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 164 | 22.56 % | 17.48 % | 1.29 | [16.8 % ; 29.5 %] | 127 | 0.961 |
| CONFIRMATION | brut | 0 | n/a | 17.08 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 16.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 16.61 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 16.55 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 17.08 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 16.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 16.61 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 16.55 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 17.08 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 16.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 16.61 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 16.55 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 164 | 22.56 % | 17.87 % | 1.26 | [16.8 % ; 29.5 %] | 127 | 0.944 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 164 | 22.56 % | 17.70 % | 1.27 | [16.8 % ; 29.5 %] | 127 | 0.950 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 164 | 22.56 % | 17.53 % | 1.29 | [16.8 % ; 29.5 %] | 127 | 0.957 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 164 | 22.56 % | 17.48 % | 1.29 | [16.8 % ; 29.5 %] | 127 | 0.961 |

- **Retournements de référence** : 6 au total, **5 détectés à l'avance**, **1 manqués** (détection 83.33 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 2400.0 min · 80.0 % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 200 | 27.50 % | 22.83 % | 1.20 | [21.8 % ; 34.1 %] | 145 | 0.953 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 200 | 27.50 % | 22.66 % | 1.21 | [21.8 % ; 34.1 %] | 145 | 0.958 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 200 | 27.50 % | 22.41 % | 1.23 | [21.8 % ; 34.1 %] | 145 | 0.966 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 200 | 27.50 % | 22.41 % | 1.23 | [21.8 % ; 34.1 %] | 145 | 0.966 |
| CONFIRMATION | brut | 0 | n/a | 22.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 22.67 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 22.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 22.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 20 | 15.00 % | 22.77 % | 0.66 | [5.2 % ; 36.0 %] | 17 | 0.292 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 20 | 15.00 % | 22.62 % | 0.66 | [5.2 % ; 36.0 %] | 17 | 0.298 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 20 | 15.00 % | 22.41 % | 0.67 | [5.2 % ; 36.0 %] | 17 | 0.310 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 20 | 15.00 % | 22.41 % | 0.67 | [5.2 % ; 36.0 %] | 17 | 0.310 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 22.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 22.67 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 22.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 22.41 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 200 | 27.50 % | 22.83 % | 1.20 | [21.8 % ; 34.1 %] | 145 | 0.953 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 200 | 27.50 % | 22.66 % | 1.21 | [21.8 % ; 34.1 %] | 145 | 0.958 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 200 | 27.50 % | 22.41 % | 1.23 | [21.8 % ; 34.1 %] | 145 | 0.966 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 200 | 27.50 % | 22.41 % | 1.23 | [21.8 % ; 34.1 %] | 145 | 0.966 |

- **Retournements de référence** : 8 au total, **3 détectés à l'avance**, **5 manqués** (détection 37.50 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 1440.0 min · 66.7 % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 288 | 21.53 % | 23.07 % | 0.93 | [17.2 % ; 26.6 %] | 226 | 0.287 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 288 | 21.53 % | 22.94 % | 0.94 | [17.2 % ; 26.6 %] | 226 | 0.303 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 288 | 21.53 % | 22.89 % | 0.94 | [17.2 % ; 26.6 %] | 226 | 0.312 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 288 | 21.53 % | 22.87 % | 0.94 | [17.2 % ; 26.6 %] | 226 | 0.315 |
| CONFIRMATION | brut | 280 | 22.14 % | 23.10 % | 0.96 | [17.7 % ; 27.4 %] | 218 | 0.392 |
| CONFIRMATION | A/R slippage 0,57 % | 280 | 21.79 % | 22.97 % | 0.95 | [17.4 % ; 27.0 %] | 219 | 0.354 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 280 | 21.79 % | 22.91 % | 0.95 | [17.4 % ; 27.0 %] | 219 | 0.363 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 280 | 21.79 % | 22.89 % | 0.95 | [17.4 % ; 27.0 %] | 219 | 0.368 |
| INVALIDATION (mesuré en sens inverse) | brut | 95 | 20.00 % | 22.93 % | 0.87 | [13.2 % ; 29.1 %] | 76 | 0.300 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 95 | 20.00 % | 22.81 % | 0.88 | [13.2 % ; 29.1 %] | 76 | 0.311 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 95 | 20.00 % | 22.76 % | 0.88 | [13.2 % ; 29.1 %] | 76 | 0.316 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 95 | 20.00 % | 22.75 % | 0.88 | [13.2 % ; 29.1 %] | 76 | 0.317 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 17 | 35.29 % | 23.34 % | 1.51 | [17.3 % ; 58.7 %] | 11 | 0.923 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 17 | 35.29 % | 23.19 % | 1.52 | [17.3 % ; 58.7 %] | 11 | 0.925 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 17 | 35.29 % | 23.13 % | 1.53 | [17.3 % ; 58.7 %] | 11 | 0.926 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 17 | 35.29 % | 23.11 % | 1.53 | [17.3 % ; 58.7 %] | 11 | 0.926 |
| TOUS (alerte + confirmation) | brut | 568 | 21.83 % | 23.08 % | 0.95 | [18.6 % ; 25.4 %] | 444 | 0.256 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 568 | 21.65 % | 22.95 % | 0.94 | [18.5 % ; 25.2 %] | 445 | 0.246 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 568 | 21.65 % | 22.90 % | 0.95 | [18.5 % ; 25.2 %] | 445 | 0.255 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 568 | 21.65 % | 22.88 % | 0.95 | [18.5 % ; 25.2 %] | 445 | 0.260 |

- **Retournements de référence** : 18 au total, **14 détectés à l'avance**, **4 manqués** (détection 77.78 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 2160.0 min · 100.0 % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 95 | 27.37 % | 24.83 % | 1.10 | [19.4 % ; 37.1 %] | 69 | 0.742 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 95 | 27.37 % | 24.76 % | 1.11 | [19.4 % ; 37.1 %] | 69 | 0.747 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 95 | 27.37 % | 24.71 % | 1.11 | [19.4 % ; 37.1 %] | 69 | 0.750 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 95 | 27.37 % | 24.71 % | 1.11 | [19.4 % ; 37.1 %] | 69 | 0.750 |
| CONFIRMATION | brut | 108 | 25.00 % | 24.89 % | 1.00 | [17.8 % ; 33.9 %] | 81 | 0.560 |
| CONFIRMATION | A/R slippage 0,57 % | 108 | 25.00 % | 24.83 % | 1.01 | [17.8 % ; 33.9 %] | 81 | 0.566 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 108 | 25.00 % | 24.77 % | 1.01 | [17.8 % ; 33.9 %] | 81 | 0.572 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 108 | 25.00 % | 24.77 % | 1.01 | [17.8 % ; 33.9 %] | 81 | 0.572 |
| INVALIDATION (mesuré en sens inverse) | brut | 45 | 22.22 % | 25.62 % | 0.87 | [12.5 % ; 36.3 %] | 35 | 0.361 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 45 | 22.22 % | 25.59 % | 0.87 | [12.5 % ; 36.3 %] | 35 | 0.363 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 45 | 22.22 % | 25.51 % | 0.87 | [12.5 % ; 36.3 %] | 35 | 0.371 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 45 | 22.22 % | 25.51 % | 0.87 | [12.5 % ; 36.3 %] | 35 | 0.371 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 4 | 25.00 % | 25.00 % | 1.00 | [4.6 % ; 69.9 %] | 3 | 0.737 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 4 | 25.00 % | 24.94 % | 1.00 | [4.6 % ; 69.9 %] | 3 | 0.737 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 4 | 25.00 % | 24.88 % | 1.00 | [4.6 % ; 69.9 %] | 3 | 0.738 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 4 | 25.00 % | 24.88 % | 1.00 | [4.6 % ; 69.9 %] | 3 | 0.738 |
| TOUS (alerte + confirmation) | brut | 203 | 26.11 % | 24.86 % | 1.05 | [20.5 % ; 32.6 %] | 150 | 0.698 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 203 | 26.11 % | 24.80 % | 1.05 | [20.5 % ; 32.6 %] | 150 | 0.705 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 203 | 26.11 % | 24.74 % | 1.06 | [20.5 % ; 32.6 %] | 150 | 0.709 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 203 | 26.11 % | 24.74 % | 1.06 | [20.5 % ; 32.6 %] | 150 | 0.709 |

- **Retournements de référence** : 6 au total, **3 détectés à l'avance**, **3 manqués** (détection 50.00 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 480.0 min · 100.0 % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 94 | 19.15 % | 17.08 % | 1.12 | [12.5 % ; 28.3 %] | 76 | 0.749 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 94 | 19.15 % | 16.85 % | 1.14 | [12.5 % ; 28.3 %] | 76 | 0.766 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 94 | 18.09 % | 16.61 % | 1.09 | [11.6 % ; 27.1 %] | 77 | 0.710 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 94 | 18.09 % | 16.55 % | 1.09 | [11.6 % ; 27.1 %] | 77 | 0.714 |
| CONFIRMATION | brut | 90 | 17.78 % | 16.77 % | 1.06 | [11.2 % ; 26.9 %] | 74 | 0.656 |
| CONFIRMATION | A/R slippage 0,57 % | 90 | 17.78 % | 16.51 % | 1.08 | [11.2 % ; 26.9 %] | 74 | 0.678 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 90 | 17.78 % | 16.24 % | 1.09 | [11.2 % ; 26.9 %] | 74 | 0.702 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 90 | 17.78 % | 16.18 % | 1.10 | [11.2 % ; 26.9 %] | 74 | 0.709 |
| INVALIDATION (mesuré en sens inverse) | brut | 38 | 26.32 % | 18.85 % | 1.40 | [15.0 % ; 42.0 %] | 28 | 0.922 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 38 | 26.32 % | 18.76 % | 1.40 | [15.0 % ; 42.0 %] | 28 | 0.924 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 38 | 26.32 % | 18.67 % | 1.41 | [15.0 % ; 42.0 %] | 28 | 0.926 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 38 | 26.32 % | 18.65 % | 1.41 | [15.0 % ; 42.0 %] | 28 | 0.926 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 7 | 28.57 % | 16.68 % | 1.71 | [8.2 % ; 64.1 %] | 5 | 0.893 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 7 | 28.57 % | 16.41 % | 1.74 | [8.2 % ; 64.1 %] | 5 | 0.899 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 7 | 28.57 % | 16.14 % | 1.77 | [8.2 % ; 64.1 %] | 5 | 0.904 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 7 | 28.57 % | 16.07 % | 1.78 | [8.2 % ; 64.1 %] | 5 | 0.905 |
| TOUS (alerte + confirmation) | brut | 184 | 18.48 % | 16.93 % | 1.09 | [13.5 % ; 24.7 %] | 150 | 0.756 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 184 | 18.48 % | 16.68 % | 1.11 | [13.5 % ; 24.7 %] | 150 | 0.779 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 184 | 17.93 % | 16.43 % | 1.09 | [13.1 % ; 24.1 %] | 151 | 0.750 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 184 | 17.93 % | 16.37 % | 1.10 | [13.1 % ; 24.1 %] | 151 | 0.755 |

- **Retournements de référence** : 6 au total, **4 détectés à l'avance**, **2 manqués** (détection 66.67 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 960.0 min · 100.0 % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 111 | 15.32 % | 22.89 % | 0.67 | [9.8 % ; 23.2 %] | 94 | 0.036 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 111 | 15.32 % | 22.70 % | 0.67 | [9.8 % ; 23.2 %] | 94 | 0.040 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 111 | 15.32 % | 22.41 % | 0.68 | [9.8 % ; 23.2 %] | 94 | 0.045 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 111 | 15.32 % | 22.41 % | 0.68 | [9.8 % ; 23.2 %] | 94 | 0.045 |
| CONFIRMATION | brut | 136 | 17.65 % | 22.91 % | 0.77 | [12.2 % ; 24.9 %] | 112 | 0.080 |
| CONFIRMATION | A/R slippage 0,57 % | 136 | 17.65 % | 22.71 % | 0.78 | [12.2 % ; 24.9 %] | 112 | 0.089 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 136 | 17.65 % | 22.41 % | 0.79 | [12.2 % ; 24.9 %] | 112 | 0.100 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 136 | 17.65 % | 22.41 % | 0.79 | [12.2 % ; 24.9 %] | 112 | 0.100 |
| INVALIDATION (mesuré en sens inverse) | brut | 52 | 23.08 % | 22.77 % | 1.01 | [13.7 % ; 36.1 %] | 40 | 0.608 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 52 | 23.08 % | 22.62 % | 1.02 | [13.7 % ; 36.1 %] | 40 | 0.615 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 52 | 23.08 % | 22.41 % | 1.03 | [13.7 % ; 36.1 %] | 40 | 0.630 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 52 | 23.08 % | 22.41 % | 1.03 | [13.7 % ; 36.1 %] | 40 | 0.630 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 24 | 29.17 % | 22.96 % | 1.27 | [14.9 % ; 49.2 %] | 17 | 0.844 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 24 | 29.17 % | 22.75 % | 1.28 | [14.9 % ; 49.2 %] | 17 | 0.851 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 24 | 29.17 % | 22.41 % | 1.30 | [14.9 % ; 49.2 %] | 17 | 0.860 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 24 | 29.17 % | 22.41 % | 1.30 | [14.9 % ; 49.2 %] | 17 | 0.860 |
| TOUS (alerte + confirmation) | brut | 247 | 16.60 % | 22.90 % | 0.72 | [12.5 % ; 21.7 %] | 206 | 0.011 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 247 | 16.60 % | 22.71 % | 0.73 | [12.5 % ; 21.7 %] | 206 | 0.013 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 247 | 16.60 % | 22.41 % | 0.74 | [12.5 % ; 21.7 %] | 206 | 0.017 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 247 | 16.60 % | 22.41 % | 0.74 | [12.5 % ; 21.7 %] | 206 | 0.017 |

- **Retournements de référence** : 8 au total, **3 détectés à l'avance**, **5 manqués** (détection 37.50 %) — fenêtre d'avertissement : 18 bougies.
- **Délai d'avance** : médiane 960.0 min · 100.0 % des détections précèdent l'entrée plausible.

## 2.1d — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| CONFIRMATION | brut | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 14 | 0.00 % | 10.77 % | 0.00 | [0.0 % ; 21.5 %] | 14 | 0.201 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 14 | 0.00 % | 10.77 % | 0.00 | [0.0 % ; 21.5 %] | 14 | 0.201 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 14 | 0.00 % | 10.77 % | 0.00 | [0.0 % ; 21.5 %] | 14 | 0.201 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 14 | 0.00 % | 10.77 % | 0.00 | [0.0 % ; 21.5 %] | 14 | 0.201 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 10.77 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 83 | 12.05 % | 10.76 % | 1.12 | [6.7 % ; 20.8 %] | 73 | 0.732 |

- **Retournements de référence** : 3 au total, **0 détectés à l'avance**, **3 manqués** (détection 0.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| CONFIRMATION | brut | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 31 | 3.23 % | 7.16 % | 0.45 | [0.6 % ; 16.2 %] | 30 | 0.357 |

- **Retournements de référence** : 1 au total, **1 détectés à l'avance**, **0 manqués** (détection 100.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane 1440.0 min · 100.0 % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| CONFIRMATION | brut | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 24 | 8.33 % | 9.46 % | 0.88 | [2.3 % ; 25.8 %] | 22 | 0.591 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| CONFIRMATION | brut | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 4 | 25.00 % | 13.36 % | 1.87 | [4.6 % ; 69.9 %] | 3 | 0.910 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 4 | 25.00 % | 13.36 % | 1.87 | [4.6 % ; 69.9 %] | 3 | 0.910 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 4 | 25.00 % | 13.36 % | 1.87 | [4.6 % ; 69.9 %] | 3 | 0.910 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 4 | 25.00 % | 13.36 % | 1.87 | [4.6 % ; 69.9 %] | 3 | 0.910 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 14.02 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 21 | 14.29 % | 14.21 % | 1.01 | [5.0 % ; 34.6 %] | 18 | 0.668 |

- **Retournements de référence** : 6 au total, **2 détectés à l'avance**, **4 manqués** (détection 33.33 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane 2880.0 min · 50.0 % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 46 | 8.70 % | 10.79 % | 0.81 | [3.4 % ; 20.3 %] | 42 | 0.447 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 46 | 8.70 % | 10.79 % | 0.81 | [3.4 % ; 20.3 %] | 42 | 0.447 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 46 | 8.70 % | 10.79 % | 0.81 | [3.4 % ; 20.3 %] | 42 | 0.447 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 46 | 8.70 % | 10.79 % | 0.81 | [3.4 % ; 20.3 %] | 42 | 0.447 |
| CONFIRMATION | brut | 47 | 8.51 % | 10.73 % | 0.79 | [3.4 % ; 19.9 %] | 43 | 0.448 |
| CONFIRMATION | A/R slippage 0,57 % | 47 | 8.51 % | 10.73 % | 0.79 | [3.4 % ; 19.9 %] | 43 | 0.448 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 47 | 8.51 % | 10.73 % | 0.79 | [3.4 % ; 19.9 %] | 43 | 0.448 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 47 | 8.51 % | 10.73 % | 0.79 | [3.4 % ; 19.9 %] | 43 | 0.448 |
| INVALIDATION (mesuré en sens inverse) | brut | 11 | 9.09 % | 10.78 % | 0.84 | [1.6 % ; 37.7 %] | 10 | 0.672 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 11 | 9.09 % | 10.78 % | 0.84 | [1.6 % ; 37.7 %] | 10 | 0.672 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 11 | 9.09 % | 10.78 % | 0.84 | [1.6 % ; 37.7 %] | 10 | 0.672 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 11 | 9.09 % | 10.78 % | 0.84 | [1.6 % ; 37.7 %] | 10 | 0.672 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 5 | 20.00 % | 10.70 % | 1.87 | [3.6 % ; 62.4 %] | 4 | 0.913 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 5 | 20.00 % | 10.70 % | 1.87 | [3.6 % ; 62.4 %] | 4 | 0.913 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 5 | 20.00 % | 10.70 % | 1.87 | [3.6 % ; 62.4 %] | 4 | 0.913 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 5 | 20.00 % | 10.70 % | 1.87 | [3.6 % ; 62.4 %] | 4 | 0.913 |
| TOUS (alerte + confirmation) | brut | 93 | 8.60 % | 10.76 % | 0.80 | [4.4 % ; 16.1 %] | 85 | 0.323 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 93 | 8.60 % | 10.76 % | 0.80 | [4.4 % ; 16.1 %] | 85 | 0.323 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 93 | 8.60 % | 10.76 % | 0.80 | [4.4 % ; 16.1 %] | 85 | 0.323 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 93 | 8.60 % | 10.76 % | 0.80 | [4.4 % ; 16.1 %] | 85 | 0.323 |

- **Retournements de référence** : 3 au total, **1 détectés à l'avance**, **2 manqués** (détection 33.33 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane 4320.0 min · 100.0 % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 11 | 0.00 % | 8.06 % | 0.00 | [0.0 % ; 25.9 %] | 11 | 0.407 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 11 | 0.00 % | 8.06 % | 0.00 | [0.0 % ; 25.9 %] | 11 | 0.407 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 11 | 0.00 % | 8.06 % | 0.00 | [0.0 % ; 25.9 %] | 11 | 0.407 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 11 | 0.00 % | 8.06 % | 0.00 | [0.0 % ; 25.9 %] | 11 | 0.407 |
| CONFIRMATION | brut | 19 | 0.00 % | 9.44 % | 0.00 | [0.0 % ; 16.8 %] | 19 | 0.151 |
| CONFIRMATION | A/R slippage 0,57 % | 19 | 0.00 % | 9.44 % | 0.00 | [0.0 % ; 16.8 %] | 19 | 0.151 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 19 | 0.00 % | 9.44 % | 0.00 | [0.0 % ; 16.8 %] | 19 | 0.151 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 19 | 0.00 % | 9.44 % | 0.00 | [0.0 % ; 16.8 %] | 19 | 0.151 |
| INVALIDATION (mesuré en sens inverse) | brut | 5 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.722 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 5 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.722 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 5 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.722 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 5 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.722 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 9.22 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 30 | 0.00 % | 8.94 % | 0.00 | [0.0 % ; 11.4 %] | 30 | 0.067 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 30 | 0.00 % | 8.94 % | 0.00 | [0.0 % ; 11.4 %] | 30 | 0.067 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 30 | 0.00 % | 8.94 % | 0.00 | [0.0 % ; 11.4 %] | 30 | 0.067 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 30 | 0.00 % | 8.94 % | 0.00 | [0.0 % ; 11.4 %] | 30 | 0.067 |

- **Retournements de référence** : 1 au total, **0 détectés à l'avance**, **1 manqués** (détection 0.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 13 | 7.69 % | 9.67 % | 0.80 | [1.4 % ; 33.3 %] | 12 | 0.624 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 13 | 7.69 % | 9.67 % | 0.80 | [1.4 % ; 33.3 %] | 12 | 0.624 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 13 | 7.69 % | 9.67 % | 0.80 | [1.4 % ; 33.3 %] | 12 | 0.624 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 13 | 7.69 % | 9.67 % | 0.80 | [1.4 % ; 33.3 %] | 12 | 0.624 |
| CONFIRMATION | brut | 17 | 11.76 % | 6.47 % | 1.82 | [3.3 % ; 34.3 %] | 15 | 0.907 |
| CONFIRMATION | A/R slippage 0,57 % | 17 | 11.76 % | 6.47 % | 1.82 | [3.3 % ; 34.3 %] | 15 | 0.907 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 17 | 11.76 % | 6.47 % | 1.82 | [3.3 % ; 34.3 %] | 15 | 0.907 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 17 | 11.76 % | 6.47 % | 1.82 | [3.3 % ; 34.3 %] | 15 | 0.907 |
| INVALIDATION (mesuré en sens inverse) | brut | 8 | 12.50 % | 6.79 % | 1.84 | [2.2 % ; 47.1 %] | 7 | 0.898 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 8 | 12.50 % | 6.79 % | 1.84 | [2.2 % ; 47.1 %] | 7 | 0.898 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 8 | 12.50 % | 6.79 % | 1.84 | [2.2 % ; 47.1 %] | 7 | 0.898 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 8 | 12.50 % | 6.79 % | 1.84 | [2.2 % ; 47.1 %] | 7 | 0.898 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 6.79 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 30 | 10.00 % | 7.86 % | 1.27 | [3.5 % ; 25.6 %] | 27 | 0.794 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 30 | 10.00 % | 7.86 % | 1.27 | [3.5 % ; 25.6 %] | 27 | 0.794 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 30 | 10.00 % | 7.86 % | 1.27 | [3.5 % ; 25.6 %] | 27 | 0.794 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 30 | 10.00 % | 7.86 % | 1.27 | [3.5 % ; 25.6 %] | 27 | 0.794 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 18 | 16.67 % | 14.32 % | 1.16 | [5.8 % ; 39.2 %] | 15 | 0.774 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 18 | 16.67 % | 14.32 % | 1.16 | [5.8 % ; 39.2 %] | 15 | 0.774 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 18 | 16.67 % | 14.32 % | 1.16 | [5.8 % ; 39.2 %] | 15 | 0.774 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 18 | 16.67 % | 14.32 % | 1.16 | [5.8 % ; 39.2 %] | 15 | 0.774 |
| CONFIRMATION | brut | 23 | 30.43 % | 13.96 % | 2.18 | [15.6 % ; 50.9 %] | 16 | 0.992 |
| CONFIRMATION | A/R slippage 0,57 % | 23 | 30.43 % | 13.96 % | 2.18 | [15.6 % ; 50.9 %] | 16 | 0.992 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 23 | 30.43 % | 13.96 % | 2.18 | [15.6 % ; 50.9 %] | 16 | 0.992 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 23 | 30.43 % | 13.96 % | 2.18 | [15.6 % ; 50.9 %] | 16 | 0.992 |
| INVALIDATION (mesuré en sens inverse) | brut | 3 | 0.00 % | 12.70 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.678 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 3 | 0.00 % | 12.70 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.678 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 12.70 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.678 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 12.70 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.678 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 4 | 25.00 % | 14.02 % | 1.78 | [4.6 % ; 69.9 %] | 3 | 0.909 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 4 | 25.00 % | 14.02 % | 1.78 | [4.6 % ; 69.9 %] | 3 | 0.909 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 4 | 25.00 % | 14.02 % | 1.78 | [4.6 % ; 69.9 %] | 3 | 0.909 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 4 | 25.00 % | 14.02 % | 1.78 | [4.6 % ; 69.9 %] | 3 | 0.909 |
| TOUS (alerte + confirmation) | brut | 41 | 24.39 % | 14.12 % | 1.73 | [13.8 % ; 39.3 %] | 31 | 0.979 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 41 | 24.39 % | 14.12 % | 1.73 | [13.8 % ; 39.3 %] | 31 | 0.979 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 41 | 24.39 % | 14.12 % | 1.73 | [13.8 % ; 39.3 %] | 31 | 0.979 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 41 | 24.39 % | 14.12 % | 1.73 | [13.8 % ; 39.3 %] | 31 | 0.979 |

- **Retournements de référence** : 6 au total, **3 détectés à l'avance**, **3 manqués** (détection 50.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane 7200.0 min · 100.0 % des détections précèdent l'entrée plausible.

## 2.1w — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| CONFIRMATION | brut | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 3 | 33.33 % | 9.45 % | 3.53 | [6.1 % ; 79.2 %] | 2 | 0.977 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 3 | 33.33 % | 9.45 % | 3.53 | [6.1 % ; 79.2 %] | 2 | 0.977 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 3 | 33.33 % | 9.45 % | 3.53 | [6.1 % ; 79.2 %] | 2 | 0.977 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 3 | 33.33 % | 9.45 % | 3.53 | [6.1 % ; 79.2 %] | 2 | 0.977 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 11 | 9.09 % | 8.55 % | 1.06 | [1.6 % ; 37.7 %] | 10 | 0.753 |

- **Retournements de référence** : 1 au total, **0 détectés à l'avance**, **1 manqués** (détection 0.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| CONFIRMATION | brut | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 5 | 0.00 % | 3.00 % | 0.00 | [0.0 % ; 43.4 %] | 5 | 0.858 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| CONFIRMATION | brut | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 6.67 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.807 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| CONFIRMATION | brut | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 7 | 14.29 % | 6.61 % | 2.16 | [2.6 % ; 51.3 %] | 6 | 0.922 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 7 | 14.29 % | 6.61 % | 2.16 | [2.6 % ; 51.3 %] | 6 | 0.922 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 7 | 14.29 % | 6.61 % | 2.16 | [2.6 % ; 51.3 %] | 6 | 0.922 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 7 | 14.29 % | 6.61 % | 2.16 | [2.6 % ; 51.3 %] | 6 | 0.922 |
| CONFIRMATION | brut | 7 | 14.29 % | 9.81 % | 1.46 | [2.6 % ; 51.3 %] | 6 | 0.850 |
| CONFIRMATION | A/R slippage 0,57 % | 7 | 14.29 % | 9.81 % | 1.46 | [2.6 % ; 51.3 %] | 6 | 0.850 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 7 | 14.29 % | 9.81 % | 1.46 | [2.6 % ; 51.3 %] | 6 | 0.850 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 7 | 14.29 % | 9.81 % | 1.46 | [2.6 % ; 51.3 %] | 6 | 0.850 |
| INVALIDATION (mesuré en sens inverse) | brut | 2 | 0.00 % | 4.48 % | 0.00 | [0.0 % ; 65.8 %] | 2 | 0.917 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 2 | 0.00 % | 4.48 % | 0.00 | [0.0 % ; 65.8 %] | 2 | 0.917 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 2 | 0.00 % | 4.48 % | 0.00 | [0.0 % ; 65.8 %] | 2 | 0.917 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 2 | 0.00 % | 4.48 % | 0.00 | [0.0 % ; 65.8 %] | 2 | 0.917 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 8.21 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 14 | 14.29 % | 8.21 % | 1.74 | [4.0 % ; 39.9 %] | 12 | 0.907 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 14 | 14.29 % | 8.21 % | 1.74 | [4.0 % ; 39.9 %] | 12 | 0.907 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 14 | 14.29 % | 8.21 % | 1.74 | [4.0 % ; 39.9 %] | 12 | 0.907 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 14 | 14.29 % | 8.21 % | 1.74 | [4.0 % ; 39.9 %] | 12 | 0.907 |

- **Retournements de référence** : 1 au total, **0 détectés à l'avance**, **1 manqués** (détection 0.00 %) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 3 | 0.00 % | 3.33 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.900 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 3 | 0.00 % | 3.33 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.900 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 3.33 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.900 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 3.33 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.900 |
| CONFIRMATION | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | brut | 1 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.945 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 1 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.945 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.945 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.945 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 2.50 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 4 | 0.00 % | 2.50 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.904 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 4 | 0.00 % | 2.50 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.904 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 4 | 0.00 % | 2.50 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.904 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 4 | 0.00 % | 2.50 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.904 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| CONFIRMATION | brut | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| CONFIRMATION | A/R slippage 0,57 % | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 4 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 49.0 %] | 4 | 0.805 |
| INVALIDATION (mesuré en sens inverse) | brut | 3 | 33.33 % | 6.67 % | 5.00 | [6.1 % ; 79.2 %] | 2 | 0.984 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 3 | 33.33 % | 6.67 % | 5.00 | [6.1 % ; 79.2 %] | 2 | 0.984 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 3 | 33.33 % | 6.67 % | 5.00 | [6.1 % ; 79.2 %] | 2 | 0.984 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 3 | 33.33 % | 6.67 % | 5.00 | [6.1 % ; 79.2 %] | 2 | 0.984 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 5.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 8 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 32.4 %] | 8 | 0.656 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 8 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 32.4 %] | 8 | 0.656 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 8 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 32.4 %] | 8 | 0.656 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 8 | 0.00 % | 5.00 % | 0.00 | [0.0 % ; 32.4 %] | 8 | 0.656 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 2.47 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.926 |
| CONFIRMATION | brut | 3 | 0.00 % | 1.23 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.959 |
| CONFIRMATION | A/R slippage 0,57 % | 3 | 0.00 % | 1.23 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.959 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 3 | 0.00 % | 1.23 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.959 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 3 | 0.00 % | 1.23 % | 0.00 | [0.0 % ; 56.2 %] | 3 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | brut | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 3.70 % | 0.00 | [0.0 % ; 79.3 %] | 1 | 0.959 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 1.85 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 6 | 0.00 % | 1.85 % | 0.00 | [0.0 % ; 39.0 %] | 6 | 0.894 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 6 | 0.00 % | 1.85 % | 0.00 | [0.0 % ; 39.0 %] | 6 | 0.894 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 6 | 0.00 % | 1.85 % | 0.00 | [0.0 % ; 39.0 %] | 6 | 0.894 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 6 | 0.00 % | 1.85 % | 0.00 | [0.0 % ; 39.0 %] | 6 | 0.894 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 5 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

## 2.1M — résultats

### ancien · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### ancien · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · NEW — NEW (période vierge, collectée pour cette phase)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 4 | 0.00 % | 0.00 % | n/a | [0.0 % ; 49.0 %] | 4 | 1.000 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS1 — IS1 (conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · IS2 — IS2 (validation de conception)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | brut | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R slippage 0,57 % | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 1 | 0.00 % | 0.00 % | n/a | [0.0 % ; 79.3 %] | 1 | 1.000 |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 2 | 0.00 % | 0.00 % | n/a | [0.0 % ; 65.8 %] | 2 | 1.000 |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

### v2 · OOS — OOS (déjà consulté : usage exploratoire)

| Statut | Scénario de coûts | n | Taux | Référence | Écart | IC 95 % | Faux positifs | Percentile nul |
|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| ALERTE PRÉCOCE | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| CONFIRMATION | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| INVALIDATION (mesuré en sens inverse) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | brut | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R slippage 0,57 % | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,10 %/côté (0,77 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |
| TOUS (alerte + confirmation) | A/R + frais 0,15 %/côté (0,87 %) | 0 | n/a | 0.00 % | n/a | [0.0 % ; 0.0 %] | 0 | n/a |

- **Retournements de référence** : 0 au total, **0 détectés à l'avance**, **0 manqués** (détection n/a) — fenêtre d'avertissement : 6 bougies.
- **Délai d'avance** : médiane n/a min · n/a % des détections précèdent l'entrée plausible.

## 3. Profil gains / pertes — le résultat économique qui compte

Segment de validation (OOS), cible 15m, horizons [96, 288] bougies (24 h et 72 h).

| Statut | Horizon | n | Espérance | Médiane | Pire | Meilleur | Gains (moy.) | Pertes (moy.) | Ratio gain/perte |
|---|---|---|---|---|---|---|---|---|---|---|
| ALERTE PRÉCOCE | 96 | 464 | **-0.406 %** | -0.572 % | -25.25 % | +36.28 % | 196 (+4.15 %) | 266 (-3.76 %) | 1.10 |
| ALERTE PRÉCOCE | 288 | 464 | **-0.305 %** | -0.480 % | -35.09 % | +48.16 % | 207 (+6.37 %) | 249 (-5.86 %) | 1.09 |
| CONFIRMATION | 96 | 457 | **-0.324 %** | -0.681 % | -20.51 % | +42.73 % | 205 (+3.69 %) | 251 (-3.60 %) | 1.02 |
| CONFIRMATION | 288 | 457 | **-0.357 %** | -0.844 % | -33.99 % | +39.86 % | 202 (+6.19 %) | 248 (-5.69 %) | 1.09 |
| INVALIDATION (mesuré en sens inverse) | 96 | 208 | **-0.456 %** | -0.668 % | -21.36 % | +22.60 % | 90 (+4.13 %) | 118 (-3.96 %) | 1.04 |
| INVALIDATION (mesuré en sens inverse) | 288 | 208 | **-0.143 %** | -0.207 % | -43.05 % | +50.31 % | 100 (+6.67 %) | 103 (-6.75 %) | 0.99 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | 96 | 78 | **+0.792 %** | +0.000 % | -8.60 % | +42.73 % | 38 (+4.46 %) | 39 (-2.78 %) | 1.60 |
| **EXPLOITABLE** (confirmation + régime 1j neutre) | 288 | 78 | **+0.641 %** | -0.000 % | -28.27 % | +31.20 % | 37 (+5.53 %) | 38 (-4.12 %) | 1.34 |

**Lecture** : le gain moyen ne compense que marginalement la perte moyenne (ratio ≈ 1,0 à 1,1) alors que les pertes sont **plus fréquentes** que les gains. L'**espérance des signaux est négative, avant même les frais** (≈ −0,2 % à −0,5 % par signal). Avec un aller-retour de 0,57 %, l'espérance tombe à environ −1 %. Un taux de réussite mesuré contre une référence *relative* (quantile empirique) ne dit donc rien de l'exploitabilité : c'est l'espérance qui la dit.

**Cas particulier de l'invalidation** : l'espérance y est mesurée **dans le sens du setup invalidé**. Une espérance négative y signifie donc que le prix est allé **contre** le setup après son invalidation — c'est-à-dire que l'invalidation a été **juste** (mais de façon ténue : ratio ≈ 1,0, magnitude −0,2 % à −0,5 %). Ce constat **n'est pas stable** (sur le segment de conception, le même indicateur vaut 0,84 avec un percentile nul de 0,04) : il n'est donc pas présenté comme une amélioration.

## 4. Diagnostic — pourquoi aucune règle ne se généralise

Les combinaisons de familles de preuves ont été passées au crible sur le segment de **conception**, puis validées sur une zone **intacte** de ce même segment (`scripts/backtest/analyse_families.py --segment IS1` puis `--segment IS2`).

| Combinaison de familles | IS1 (conception) | IS2 (validation intacte) |
|---|---|---|
| context + momentum + structure + volume | **1,447** (n=211, percentile nul 1,000) | 0,748 (n=229, 0,008) |
| context + momentum + volume | 0,813 (n=165, 0,092) | **1,400** (n=213, 1,000) |
| momentum + structure + volume | 1,138 (n=223, 0,893) | 0,697 (n=109, 0,029) |
| momentum + volume | 0,819 (n=161, 0,092) | 0,462 (n=124, 0,000) |
| context + momentum | 0,871 (n=67, 0,311) | 0,925 (n=67, 0,407) |
| momentum + structure | 0,676 (n=48, 0,130) | 0,721 (n=70, 0,088) |
| context + momentum + structure | 0,413 (n=78, 0,001) | 0,956 (n=57, 0,492) |

**Lecture** :

1. **Les classements s'inversent** entre les deux moitiés. La combinaison qui paraît la meilleure sur la zone de conception est la **pire** sur la zone de validation intacte, et réciproquement. C'est la signature d'un **artefact de sélection** : choisir une combinaison sur des données historiques ne produit rien de généralisable.
2. **Un seul constat est stable sur les trois échantillons** (IS1, IS2, IS complet) : **sans la famille `volume`, les signaux sont au niveau du hasard ou en dessous** (écarts 0,41 à 0,96). La capitulation de volume porte l'information ; mais le choix de ce qu'on lui associe n'est pas stable.
3. Conséquence : **aucune modification de la règle de décision n'est justifiée** par ces mesures. Régler la règle pour améliorer le score reviendrait à du surapustement ; le moteur v2 est donc **conservé tel quel**.

## 5. Conclusion

* **Les signaux bruts, sans qualification, ne battent pas le hasard.** Sur 15m, l'écart à la référence est inférieur à 1 dans la quasi-totalité des cas, et l'espérance économique des signaux est **négative** (≈ −0,3 % à 24 h), soit pire qu'une entrée aléatoire (≈ −0,06 %). Avec l'aller-retour observé de 0,57 %, elle tombe à ≈ −0,9 %.
* **Une qualification change le résultat** : la combinaison `CONFIRMATION` + **régime 1j 30 j neutre** (variation ±5 %) donne une espérance brute **positive dans les quatre segments** (+0,68 % · +1,91 % · +1,80 % · +0,79 %) et **nette après 0,57 %** dans les quatre (+0,11 % · +1,34 % · +1,23 % · +0,22 %). L'estimation sur les segments **non utilisés pour la conception** (NEW vierge + IS2) vaut **+0,98 %** (IC 95 % [−0,03 ; +1,96]), nette +0,41 %.
* **Cette qualification est un modificateur d'intensité, pas une preuve de rentabilité** : l'intervalle de confiance touche zéro, la marge sur les coûts est mince (coût d'équilibre 0,68 % à 1,91 % selon le segment) et les frais réels ne sont pas vérifiés.
* **Le moteur v2 est mieux instrumenté** : densité d'alerte divisée par 2,4, invalidation structurelle au lieu d'un niveau de prix figé, statuts cohérents, cause racine documentée.
* **Aucun profit n'est établi, et aucun n'est revendiqué.** Le signal exploitable est de surcroît **lent** (positif à 24 h et 72 h, négatif à 6 h, 15 min et 45 min).

### Recommandation d'usage

Le détecteur peut rester publié **comme observation descriptive**, à condition que le panneau n'affiche jamais de cible de prix présentée comme atteignable, que le score de convergence ne soit jamais présenté comme une probabilité, et que le champ `exploitable` soit pris en compte. **Il ne doit pas être utilisé comme déclencheur de position sans validation complémentaire.**


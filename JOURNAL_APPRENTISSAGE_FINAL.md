# JOURNAL D'APPRENTISSAGE — RETOURNEMENTS TEL/USDT

**Généré automatiquement** depuis `backtest_results_v2.json` par `scripts/backtest/make_journal.py`.
Chaque entrée correspond à un épisode mesuré : rien n'y est interpété ou inventé.

Ce journal existe pour apprendre **autant des mouvements manqués que des mouvements anticipés**.
Une entrée qui n'aboutit pas est conservée au même titre qu'une entrée réussie.

## Unité de temps 15m

- Données : 45000 bougies, 2025-07-09T05:30:00Z → 2026-10-20T23:15:00Z (468.7 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 54, 'ATTENDRE': 33310, 'ALERTE_PRÉCOCE': 10190, 'INVALIDATION': 1446}
- Épisodes dédupliqués : 5565 (densité 12.37% des bougies)
- Taux de réussite : 36.78% — base de taux 31.68%
- Test de nullité : observé 38.83%, médiane nulle 37.85%, percentile 0.926
- Retournements de référence : 229 — détectés à l'avance 144, **manqués 85** (fenêtre d'avertissement : 24 bougies)

## Unité de temps 1h

- Données : 5999 bougies, 2026-02-13T00:00:00Z → 2026-10-20T22:00:00Z (249.9 j)
- Statuts : {'ALERTE_PRÉCOCE': 1257, 'ATTENDRE': 4377, 'INVALIDATION': 365}
- Épisodes dédupliqués : 1120 (densité 18.67% des bougies)
- Taux de réussite : 17.50% — base de taux 14.80%
- Test de nullité : observé 18.20%, médiane nulle 17.25%, percentile 0.789
- Retournements de référence : 72 — détectés à l'avance 23, **manqués 49** (fenêtre d'avertissement : 6 bougies)

## Unité de temps 4h

- Données : 5999 bougies, 2024-01-25T00:00:00Z → 2026-10-20T16:00:00Z (999.7 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 3190, 'ALERTE_PRÉCOCE': 629, 'ATTENDRE': 2090, 'INVALIDATION': 90}
- Épisodes dédupliqués : 629 (densité 10.49% des bougies)
- Taux de réussite : 32.32% — base de taux 26.65%
- Test de nullité : observé 35.38%, médiane nulle 29.87%, percentile 0.999
- Retournements de référence : 40 — détectés à l'avance 11, **manqués 29** (fenêtre d'avertissement : 18 bougies)

## Unité de temps 1d

- Données : 2723 bougies, 2019-05-07T00:00:00Z → 2026-10-19T00:00:00Z (2722.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 2255, 'ATTENDRE': 371, 'ALERTE_PRÉCOCE': 82, 'INVALIDATION': 15}
- Épisodes dédupliqués : 82 (densité 3.01% des bougies)
- Taux de réussite : 4.88% — base de taux 13.05%
- Test de nullité : observé 6.33%, médiane nulle 9.76%, percentile 0.183
- Retournements de référence : 38 — détectés à l'avance 3, **manqués 35** (fenêtre d'avertissement : 5 bougies)

## Unité de temps 1w

- Données : 395 bougies, 2018-02-08T00:00:00Z → 2026-10-08T00:00:00Z (3164.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 328, 'ATTENDRE': 55, 'ALERTE_PRÉCOCE': 11, 'INVALIDATION': 1}
- Épisodes dédupliqués : 11 (densité 2.78% des bougies)
- Taux de réussite : 0.00% — base de taux 13.02%
- Test de nullité : observé 0.00%, médiane nulle 9.09%, percentile 0.435
- Retournements de référence : 3 — détectés à l'avance 0, **manqués 3** (fenêtre d'avertissement : 5 bougies)

## Unité de temps 1M

- Données : 89 bougies, 2018-02-01T00:00:00Z → 2026-09-01T00:00:00Z (3134.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 74, 'ALERTE_PRÉCOCE': 2, 'ATTENDRE': 13}
- Épisodes dédupliqués : 2 (densité 2.25% des bougies)
- Taux de réussite : 0.00% — base de taux 0.00%
- Test de nullité : observé 0.00%, médiane nulle 0.00%, percentile 1.0
- Retournements de référence : 0 — détectés à l'avance 0, **manqués 0** (fenêtre d'avertissement : 6 bougies)

---

## Retournements anticipés (15m) — cas où l'alerte a précédé l'entrée plausible

| Creux | Entrée plausible | Alerte | Avance | Preuves de l'alerte | Amplitude du mouvement |
|---|---|---|---|---|---|
| 2025-08-19T14:30Z | 2025-08-19T16:15Z | 2025-08-19T10:15Z | **360 min** | macd_histogram_improving, high_volume_spike | 1.10% |
| 2025-12-17T16:30Z | 2025-12-17T20:00Z | 2025-12-17T14:00Z | **360 min** | bullish_rsi_divergence, macd_histogram_improving, moderate_volume_increase | 0.02% |
| 2026-01-20T15:15Z | 2026-01-20T20:00Z | 2026-01-20T14:00Z | **360 min** | bullish_rsi_divergence, macd_histogram_improving, moderate_volume_increase, weak_trend_divergence | 24.76% |
| 2026-06-21T17:00Z | 2026-06-21T18:45Z | 2026-06-21T12:45Z | **360 min** | macd_histogram_improving, high_volume_spike | 25.81% |
| 2026-02-03T09:30Z | 2026-02-03T14:30Z | 2026-02-03T08:45Z | **345 min** | macd_histogram_improving, moderate_volume_increase | -0.23% |
| 2026-02-14T04:45Z | 2026-02-14T07:00Z | 2026-02-14T01:15Z | **345 min** | bullish_rsi_divergence, macd_histogram_improving | 4.13% |
| 2026-05-18T01:45Z | 2026-05-18T03:15Z | 2026-05-17T21:30Z | **345 min** | macd_histogram_improving, higher_timeframe_alignment | 5.90% |
| 2026-05-23T07:45Z | 2026-05-23T09:30Z | 2026-05-23T03:45Z | **345 min** | macd_histogram_improving, higher_timeframe_alignment | 4.30% |
| 2026-09-21T06:30Z | 2026-09-21T08:15Z | 2026-09-21T02:30Z | **345 min** | momentum_rising_after_decline, macd_histogram_improving, moderate_volume_increase, near_critical_support | 23.25% |
| 2025-08-21T04:15Z | 2025-08-21T07:00Z | 2025-08-21T01:30Z | **330 min** | bullish_rsi_divergence, macd_histogram_improving | 16.22% |

**Avance médiane** : 60.0 min · **66.7 %** des détections précèdent l'entrée.

### Enseignement

Les détections à avance nulle ou quasi nulle sont majoritaires : l'alerte tombe souvent **sur** la bougie d'entrée, pas avant. Sur les 16 détections mesurées, 6 ont une avance de 0 minute.

## Retournements manqués (15m) — aucune alerte dans la fenêtre d'avertissement

| Creux | Entrée plausible | Prix au creux | Amplitude du mouvement ultérieur | Volatilité (ATR14 relatif) |
|---|---|---|---|---|
| 2026-09-25T21:15Z | 2026-09-26T10:00Z | 0.001646 | **41.56%** | 0.67% |
| 2026-08-19T08:15Z | 2026-08-19T08:45Z | 0.001442 | **40.50%** | 0.62% |
| 2025-11-04T11:30Z | 2025-11-04T11:45Z | 0.002779 | **28.64%** | 1.19% |
| 2026-06-20T00:15Z | 2026-06-20T05:15Z | 0.002386 | **23.81%** | 0.41% |
| 2025-10-01T00:15Z | 2025-10-01T03:30Z | 0.003869 | **23.65%** | 0.58% |
| 2025-10-11T05:45Z | 2025-10-11T06:45Z | 0.003634 | **20.58%** | 0.77% |
| 2025-12-26T12:45Z | 2025-12-26T13:00Z | 0.003946 | **18.65%** | 0.67% |
| 2025-11-06T17:00Z | 2025-11-06T18:45Z | 0.002981 | **17.65%** | 1.41% |
| 2026-02-01T17:30Z | 2026-02-01T18:00Z | 0.002743 | **15.38%** | 0.88% |
| 2026-08-08T11:00Z | 2026-08-08T14:00Z | 0.001503 | **14.77%** | 0.68% |
| 2026-08-17T11:15Z | 2026-08-17T13:45Z | 0.001463 | **14.15%** | 0.43% |
| 2025-09-04T05:30Z | 2025-09-04T06:15Z | 0.004822 | **12.28%** | 0.75% |

**85 retournements manqués sur 229** (37.1 %).

### Enseignement

Les mouvements manqués ne sont pas rares : c'est la **couverture temporelle** du signal qui est en cause, pas la rareté des retournements. Un détecteur qui ne se déclenche que 12 % du temps ne peut pas être présent sur chaque creux.

## Faux rebonds et contradictions

- Alertes **sans** retournement de référence associé : 5421 sur 5565 (97.4 %).
- Rapport signal/retournement : **26:1**. Le détecteur signale environ 26 fois plus que ce qu'il ne signale utilement.
- Sur 4h, le détecteur est **significativement moins bon que le hasard** (percentile 0.999) et ne détecte **0** retournement de référence sur 40.
- Sur 1h, 49 retournements de référence sur 72 sont manqués dans la fenêtre d'avertissement de 6 h.

### Enseignement

La panne n'est pas dans la **qualité** du signal mais dans son **volume** et sa **couverture**. Réduire la densité d'alerte et ajouter une confirmation explicite est prioritaire sur tout réglage de seuil.

## Preuves les plus fréquentes dans les alertes (15m)

- `higher_timeframe_alignment` : 2883 épisodes
- `macd_histogram_worsening` : 2567 épisodes
- `weak_trend_divergence` : 2149 épisodes
- `macd_histogram_improving` : 2061 épisodes
- `high_volume_spike` : 1997 épisodes
- `moderate_volume_increase` : 767 épisodes
- `bullish_rsi_divergence` : 518 épisodes
- `bearish_rsi_divergence` : 475 épisodes
- `rsi_oversold` : 145 épisodes
- `momentum_rising_after_decline` : 138 épisodes
- `rsi_overbought` : 133 épisodes
- `momentum_falling_after_rise` : 132 épisodes
- `stochastic_bullish_crossover` : 119 épisodes
- `stochastic_bearish_crossover` : 88 épisodes
- `near_critical_support` : 34 épisodes

### Enseignement

Les preuves de **contexte** (`weak_trend_divergence`, `higher_timeframe_alignment`) dominent, alors que les preuves directionnelles (`bullish_rsi_divergence`, `rsi_oversold`, motifs de bougies) sont rares. Or le statut `ALERTE_PRÉCOCE` exige 2 catégories distinctes : l'alignement de tendance sur 4 h/1 j suffit souvent à déclencher l'alerte, ce qui explique la densité excessive et l'absence de pouvoir prédictif sur 4 h.

## Ce que le journal ne peut pas encore contenir

- **Confirmations** : le statut `CONFIRMATION` n'est jamais assigné par le détecteur ; il n'y a donc rien à journaliser.
- **Invalidations suivies** : la règle `close < 0.001526` s'applique en continu (9,4 % des bougies en 15m) ; elle reflète un niveau figé, pas une information de marché exploitable.
- **Contexte BTC / ETH / TEL-BTC** : absent du dépôt, aucun point de comparaison possible.
- **Régime haussier** : la fenêtre testée (août → octobre 2026) est baissière. Les faux rebonds en tendance haussière ne sont pas représentés.

---

## Ajout — Évaluation hors échantillon (protocole v1.2)

Les sections précédentes portent sur la détection (signaux émis, familles de preuves, densité). Le présent bloc ajoute ce que l'évaluation chronologique hors échantillon établit — et ce qu'elle n'établit pas.

### Ce que l'hors échantillon mesure

| Unité | Moteur | Segment | n | Taux | Référence | Écart | Percentile nul | Retournements détectés |
|---|---|---|---|---|---|---|---|---|
| 15m | ancien | IS | 3012 | 24.40 % | 26.92 % | 0.91 | 0.0025 | 92/135 |
| 15m | ancien | OOS | 1787 | 26.52 % | 28.56 % | 0.93 | 0.027 | 51/93 |
| 15m | v2 | IS | 1470 | 24.63 % | 26.59 % | 0.93 | 0.057 | 54/135 |
| 15m | v2 | OOS | 921 | 24.54 % | 28.11 % | 0.87 | 0.0085 | 33/93 |
| 1h | ancien | IS | 241 | 5.39 % | 10.52 % | 0.51 | 0.003 | 4/20 |
| 1h | ancien | OOS | 735 | 15.37 % | 15.40 % | 1.00 | 0.5275 | 19/51 |
| 1h | v2 | IS | 191 | 8.38 % | 10.72 % | 0.78 | 0.184 | 2/20 |
| 1h | v2 | OOS | 648 | 13.12 % | 15.36 % | 0.85 | 0.0615 | 9/51 |
| 4h | ancien | IS | 361 | 20.22 % | 22.04 % | 0.92 | 0.2245 | 7/31 |
| 4h | ancien | OOS | 199 | 27.64 % | 22.90 % | 1.21 | 0.952 | 3/8 |
| 4h | v2 | IS | 384 | 22.14 % | 22.01 % | 1.01 | 0.5485 | 6/31 |
| 4h | v2 | OOS | 247 | 16.60 % | 22.96 % | 0.72 | 0.0095 | 3/8 |
| 1d | ancien | IS | 55 | 5.45 % | 12.17 % | 0.45 | 0.0735 | 1/32 |
| 1d | ancien | OOS | 21 | 14.29 % | 14.29 % | 1.00 | 0.6545 | 2/6 |
| 1d | v2 | IS | 60 | 5.00 % | 12.29 % | 0.41 | 0.049 | 0/32 |
| 1d | v2 | OOS | 41 | 24.39 % | 14.19 % | 1.72 | 0.978 | 3/6 |
| 1w | ancien | IS | 8 | 0.00 % | 8.84 % | 0.00 | 0.4745 | 0/3 |
| 1w | ancien | OOS | 3 | 0.00 % | 2.56 % | 0.00 | 0.923 | 0/0 |
| 1w | v2 | IS | 12 | 0.00 % | 9.62 % | 0.00 | 0.306 | 0/3 |
| 1w | v2 | OOS | 6 | 0.00 % | 1.92 % | 0.00 | 0.8865 | 0/0 |
| 1M | ancien | IS | 2 | 0.00 % | 0.00 % | n/a | 1.0 | 0/0 |
| 1M | ancien | OOS | 0 | n/a | 0.00 % | n/a | n/a | 0/0 |
| 1M | v2 | IS | 2 | 0.00 % | 0.00 % | n/a | 1.0 | 0/0 |
| 1M | v2 | OOS | 0 | n/a | 0.00 % | n/a | n/a | 0/0 |

### Ce qui est établi

* **Aucun des deux moteurs ne bat le hasard de façon stable.** L'écart à la référence est inférieur à 1 dans la quasi-totalité des cases, et le percentile de la distribution nulle est souvent très bas : les signaux ne sont pas simplement neutres, ils sont parfois **significativement moins bons que le hasard** (15m OOS moteur v2 : lift 0,87, percentile nul 0,009).
* **Le seul cell significatif de l'étude** (4h, moteur ancien, hors échantillon : lift 1,21, percentile nul 0,952, n=199) **ne se confirme nulle part ailleurs** : le même moteur sur la période de conception donne 0,92, et le moteur v2 sur la même période hors échantillon donne 0,72. Il n'est donc **pas** présenté comme une amélioration.
* **Le moteur v2 est mieux instrumenté, pas plus juste.** Densité d'alerte divisée par 2,4, invalidation structurelle au lieu d'un niveau de prix figé, statuts cohérents, cause racine documentée — mais **aucun gain de précision mesuré**.
* **Le coût ne change pas le verdict.** Avec 0,87 % aller-retour, le taux et la référence baissent ensemble et l'écart reste ≈ 0,84-0,96 : il n'existe pas de version rentable de ces signaux sur la fenêtre testée.
* **La couverture des retournements se dégrade avec la sélectivité** : en 15m hors échantillon, l'ancien moteur avertit avant 51 retournements sur 93 (54,8 %), le v2 avant 33 sur 93 (35,5 %). La densité d'alerte et la couverture sont en tension directe.

### Ce qui n'est PAS établi (et ne le sera pas)

* Aucun profit, aucune rentabilité : les frais réels ne sont pas vérifiés (hypothèses 0,10 % et 0,15 % par côté) et une seule fenêtre, un seul instrument, un seul régime dominant ont été testés.
* Les unités 1w (n ≤ 12) et 1M (n ≤ 2) ne permettent **aucune conclusion**.
* L'unité 1d (n de 21 à 60) est **sous-alimentée** : les écarts y vont de 0,41 à 1,72 selon le segment, ce qui traduit du bruit, pas une performance.

### Enseignement principal

> La tentation naturelle, devant des taux de réussite faibles, est de **chercher la combinaison de preuves qui marche le mieux** sur l'historique. C'est exactement ce que l'on a fait sur la moitié gauche du segment de conception : la meilleure combinaison y atteignait un écart de 1,447. **Sur la moitié droite, intacte, cette même combinaison est tombée à 0,748** — tandis qu'une autre, mediocre à gauche (0,813), y atteignait 1,400. **Les classements s'inversent.** Aucun réglage de règle n'est donc justifié, et aucun n'a été appliqué : le moteur est conservé tel quel, et le résultat négatif est publié tel quel.

---

## Ajout 2 — Qualification « exploitable » (recherche sur la qualite economique)

### Ce que la recherche a etabli

* **L'esperance des signaux bruts est negative**, et elle est **pire qu'une entree aleatoire** :
  alertes -0,406 % a 24 h (OOS) contre -0,050 % pour une entree au hasard ; nette de
  -0,935 % apres 0,57 % d'aller-retour.
* **La cause principale est le regime de marche** : l'esperance est de -0,671 % en tendance
  haussiere, de -0,460 % en tendance baissiere, et de **+0,532 % en regime neutre**.
* **Attendre la confirmation vaut mieux qu'agir sur l'alerte precoce** : superior dans les
  **4 segments** (+0,08 a +0,63 point).
* **Le contexte BTC / ETH / TEL-BTC n'apporte rien de demontrable** : quatre
  conditionnements testes, tous instables ou negatifs. Il n'est pas integre.
* **Les entrees tardives ne sont pas la cause** (hypothese rejetee) et les
  « continuations » ont un signe instable (non retenues).
* **Choisir la meilleure combinaison de preuves sur l'historique ne fonctionne pas** : sur la
  zone de conception elle vaut 1,447, sur la zone de validation intacte 0,748, tandis
  qu'une autre passe de 0,813 a 1,400. Les classements s'inversent : aucune regle de
  selection de famille n'est justifiee, et aucune n'a ete appliquee.

### La regle retenue et sa validation

`CONFIRMATION` **et** regime 1 jour 30 bougies neutre (variation relative dans +/-5 %).

| Segment | n | Esperance 24 h | IC 95 % | Nette (0,57 %) | Esperance 72 h |
|---|---|---|---|---|---|
| NEW (vierge) | 62 | +0,682 % | [-0,615 ; +1,921] | **+0,112 %** | +1,488 % |
| IS1 (conception) | 24 | +1,910 % | [+0,287 ; +3,658] | **+1,340 %** | +6,688 % |
| IS2 (validation) | 23 | +1,796 % | [+0,516 ; +3,055] | **+1,226 %** | +2,534 % |
| OOS (deja consulte) | 78 | +0,792 % | [-0,514 ; +2,394] | **+0,222 %** | +0,641 % |

Estimation **independante** (segments non utilises pour la conception : NEW vierge + IS2) :
n = 85 · esperance **+0,983 %** · IC 95 % **[-0,026 ; +1,962]** · nette **+0,413 %** ·
61,2 % de mouvements favorables · pire -8,29 % · meilleur +11,52 % · ratio gain/perte 1,05.

### Ce que cela ne dit pas

* L'intervalle de confiance de l'estimation independante **touche zero** : l'effet est
  statistiquement fragile.
* La marge sur les couts est **mince** : cout d'equilibre de 0,68 % (NEW) a 1,91 % (IS1) ;
  le round trip observe vaut 0,57 %, mais avec des frais de 0,10 % par cote et un slippage
  superieur, l'avantage disparait.
* Les frais de transaction ne sont **pas verifies** (hypotheses).
* Le signal exploitable est **lent** : positif a 24 h et 72 h, negatif a 6 h, 15 min et 45 min.
* L'**OOS n'est plus vierge** (il a servi a comparer les deux moteurs) : les affirmations
  nouvelles reposent sur la periode **NEW**, collectee pour cette phase.

Le moteur expose désormais `regime` et `exploitable` (avec `exploitable_reason`). Le
dashboard n'a **pas** ete modifie : l'integration de ces deux champs reste a faire.

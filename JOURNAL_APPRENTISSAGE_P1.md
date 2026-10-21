# JOURNAL D'APPRENTISSAGE — RETOURNEMENTS TEL/USDT

**Généré automatiquement** depuis `backtest_results_v2.json` par `scripts/backtest/make_journal.py`.
Chaque entrée correspond à un épisode mesuré : rien n'y est interpété ou inventé.

Ce journal existe pour apprendre **autant des mouvements manqués que des mouvements anticipés**.
Une entrée qui n'aboutit pas est conservée au même titre qu'une entrée réussie.

## Unité de temps 15m

- Données : 45000 bougies, 2025-07-09T05:30:00Z → 2026-10-20T23:15:00Z (468.7 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 54, 'ATTENDRE': 33308, 'ALERTE_PRÉCOCE': 10192, 'INVALIDATION': 1446}
- Épisodes dédupliqués : 5567 (densité 12.37% des bougies)
- Taux de réussite : 36.82% — base de taux 31.68%
- Test de nullité : observé 38.87%, médiane nulle 37.83%, percentile 0.955
- Retournements de référence : 229 — détectés à l'avance 144, **manqués 85** (fenêtre d'avertissement : 24 bougies)

## Unité de temps 1h

- Données : 5999 bougies, 2026-02-13T00:00:00Z → 2026-10-20T22:00:00Z (249.9 j)
- Statuts : {'ALERTE_PRÉCOCE': 1260, 'ATTENDRE': 4374, 'INVALIDATION': 365}
- Épisodes dédupliqués : 1122 (densité 18.70% des bougies)
- Taux de réussite : 17.47% — base de taux 14.80%
- Test de nullité : observé 18.17%, médiane nulle 17.26%, percentile 0.77
- Retournements de référence : 72 — détectés à l'avance 23, **manqués 49** (fenêtre d'avertissement : 6 bougies)

## Unité de temps 4h

- Données : 5999 bougies, 2024-01-25T00:00:00Z → 2026-10-20T16:00:00Z (999.7 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 3190, 'ALERTE_PRÉCOCE': 630, 'ATTENDRE': 2089, 'INVALIDATION': 90}
- Épisodes dédupliqués : 630 (densité 10.50% des bougies)
- Taux de réussite : 32.43% — base de taux 26.65%
- Test de nullité : observé 35.49%, médiane nulle 29.99%, percentile 1.0
- Retournements de référence : 40 — détectés à l'avance 11, **manqués 29** (fenêtre d'avertissement : 18 bougies)

## Unité de temps 1d

- Données : 2723 bougies, 2019-05-07T00:00:00Z → 2026-10-19T00:00:00Z (2722.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 2255, 'ATTENDRE': 371, 'ALERTE_PRÉCOCE': 82, 'INVALIDATION': 15}
- Épisodes dédupliqués : 82 (densité 3.01% des bougies)
- Taux de réussite : 4.88% — base de taux 13.05%
- Test de nullité : observé 6.33%, médiane nulle 9.88%, percentile 0.19
- Retournements de référence : 38 — détectés à l'avance 3, **manqués 35** (fenêtre d'avertissement : 5 bougies)

## Unité de temps 1w

- Données : 395 bougies, 2018-02-08T00:00:00Z → 2026-10-08T00:00:00Z (3164.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 328, 'ATTENDRE': 55, 'ALERTE_PRÉCOCE': 11, 'INVALIDATION': 1}
- Épisodes dédupliqués : 11 (densité 2.78% des bougies)
- Taux de réussite : 0.00% — base de taux 13.02%
- Test de nullité : observé 0.00%, médiane nulle 9.09%, percentile 0.465
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

- Alertes **sans** retournement de référence associé : 5423 sur 5567 (97.4 %).
- Rapport signal/retournement : **26:1**. Le détecteur signale environ 26 fois plus que ce qu'il ne signale utilement.
- Sur 4h, le détecteur est **significativement moins bon que le hasard** (percentile 1.0) et ne détecte **0** retournement de référence sur 40.
- Sur 1h, 49 retournements de référence sur 72 sont manqués dans la fenêtre d'avertissement de 6 h.

### Enseignement

La panne n'est pas dans la **qualité** du signal mais dans son **volume** et sa **couverture**. Réduire la densité d'alerte et ajouter une confirmation explicite est prioritaire sur tout réglage de seuil.

## Preuves les plus fréquentes dans les alertes (15m)

- `higher_timeframe_alignment` : 2885 épisodes
- `macd_histogram_worsening` : 2568 épisodes
- `weak_trend_divergence` : 2149 épisodes
- `macd_histogram_improving` : 2061 épisodes
- `high_volume_spike` : 1999 épisodes
- `moderate_volume_increase` : 768 épisodes
- `bullish_rsi_divergence` : 517 épisodes
- `bearish_rsi_divergence` : 473 épisodes
- `rsi_oversold` : 145 épisodes
- `momentum_rising_after_decline` : 138 épisodes
- `rsi_overbought` : 133 épisodes
- `momentum_falling_after_rise` : 133 épisodes
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


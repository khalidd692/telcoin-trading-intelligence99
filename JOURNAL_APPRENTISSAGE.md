# JOURNAL D'APPRENTISSAGE — RETOURNEMENTS TEL/USDT

**Généré automatiquement** depuis `backtest_results_v2.json` par `scripts/backtest/make_journal.py`.
Chaque entrée correspond à un épisode mesuré : rien n'y est interpété ou inventé.

Ce journal existe pour apprendre **autant des mouvements manqués que des mouvements anticipés**.
Une entrée qui n'aboutit pas est conservée au même titre qu'une entrée réussie.

## Unité de temps 15m

- Données : 6000 bougies, 2026-08-19T11:30:00Z → 2026-10-20T23:15:00Z (62.5 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 54, 'ATTENDRE': 4045, 'ALERTE_PRÉCOCE': 1337, 'INVALIDATION': 564}
- Épisodes dédupliqués : 724 (densité 12.07% des bougies)
- Taux de réussite : 38.40% — base de taux 31.92%
- Test de nullité : observé 40.83%, médiane nulle 38.03%, percentile 0.955
- Retournements de référence : 28 — détectés à l'avance 16, **manqués 12** (fenêtre d'avertissement : 24 bougies)

## Unité de temps 1h

- Données : 5999 bougies, 2026-02-13T00:00:00Z → 2026-10-20T22:00:00Z (249.9 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 4513, 'ATTENDRE': 1002, 'ALERTE_PRÉCOCE': 341, 'INVALIDATION': 143}
- Épisodes dédupliqués : 298 (densité 4.97% des bougies)
- Taux de réussite : 18.79% — base de taux 14.80%
- Test de nullité : observé 17.41%, médiane nulle 17.15%, percentile 0.565
- Retournements de référence : 72 — détectés à l'avance 6, **manqués 66** (fenêtre d'avertissement : 6 bougies)

## Unité de temps 4h

- Données : 5999 bougies, 2024-01-25T00:00:00Z → 2026-10-20T16:00:00Z (999.7 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 5628, 'ATTENDRE': 260, 'ALERTE_PRÉCOCE': 76, 'INVALIDATION': 35}
- Épisodes dédupliqués : 76 (densité 1.27% des bougies)
- Taux de réussite : 20.00% — base de taux 26.65%
- Test de nullité : observé 21.88%, médiane nulle 29.73%, percentile 0.06
- Retournements de référence : 40 — détectés à l'avance 0, **manqués 40** (fenêtre d'avertissement : 18 bougies)

## Unité de temps 1d

- Données : 2723 bougies, 2019-05-07T00:00:00Z → 2026-10-19T00:00:00Z (2722.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 2662, 'ALERTE_PRÉCOCE': 7, 'ATTENDRE': 48, 'INVALIDATION': 6}
- Épisodes dédupliqués : 7 (densité 0.26% des bougies)
- Taux de réussite : 14.29% — base de taux 13.05%
- Test de nullité : observé 25.00%, médiane nulle 14.29%, percentile 0.89
- Retournements de référence : 38 — détectés à l'avance 0, **manqués 38** (fenêtre d'avertissement : 5 bougies)

## Unité de temps 1w

- Données : 395 bougies, 2018-02-08T00:00:00Z → 2026-10-08T00:00:00Z (3164.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 387, 'ATTENDRE': 7, 'INVALIDATION': 1}
- Épisodes dédupliqués : 0 (densité 0.00% des bougies)
- Taux de réussite : n/a — base de taux 13.02%
- Test de nullité : observé n/a, médiane nulle n/a, percentile None
- Retournements de référence : 3 — détectés à l'avance 0, **manqués 3** (fenêtre d'avertissement : 5 bougies)

## Unité de temps 1M

- Données : 89 bougies, 2018-02-01T00:00:00Z → 2026-09-01T00:00:00Z (3134.0 j)
- Statuts : {'DONNÉES_INSUFFISANTES': 87, 'ATTENDRE': 2}
- Épisodes dédupliqués : 0 (densité 0.00% des bougies)
- Taux de réussite : n/a — base de taux 0.00%
- Test de nullité : observé n/a, médiane nulle n/a, percentile None
- Retournements de référence : 0 — détectés à l'avance 0, **manqués 0** (fenêtre d'avertissement : 6 bougies)

---

## Retournements anticipés (15m) — cas où l'alerte a précédé l'entrée plausible

| Creux | Entrée plausible | Alerte | Avance | Preuves de l'alerte | Amplitude du mouvement |
|---|---|---|---|---|---|
| 2026-09-21T06:30Z | 2026-09-21T08:15Z | 2026-09-21T02:30Z | **345 min** | momentum_rising_after_decline, macd_histogram_improving, moderate_volume_increase, near_critical_support | 23.25% |
| 2026-10-13T09:45Z | 2026-10-13T10:15Z | 2026-10-13T04:45Z | **330 min** | macd_histogram_improving, weak_trend_divergence | 3.89% |
| 2026-09-19T12:00Z | 2026-09-19T13:45Z | 2026-09-19T08:30Z | **315 min** | macd_histogram_improving, moderate_volume_increase | 8.47% |
| 2026-10-17T08:15Z | 2026-10-17T08:30Z | 2026-10-17T03:30Z | **300 min** | bullish_rsi_divergence, rsi_oversold, stochastic_bullish_crossover, macd_histogram_improving | 0.47% |
| 2026-10-08T12:15Z | 2026-10-08T13:15Z | 2026-10-08T09:45Z | **210 min** | macd_histogram_improving, high_volume_spike | 4.45% |
| 2026-09-03T10:30Z | 2026-09-03T13:45Z | 2026-09-03T11:00Z | **165 min** | bullish_rsi_divergence, stochastic_bullish_crossover, macd_histogram_improving | 4.48% |
| 2026-10-05T17:15Z | 2026-10-05T20:30Z | 2026-10-05T17:45Z | **165 min** | stochastic_bullish_crossover, macd_histogram_improving, weak_trend_divergence, higher_timeframe_alignment | 12.95% |
| 2026-10-15T02:30Z | 2026-10-15T04:45Z | 2026-10-15T02:00Z | **165 min** | bullish_rsi_divergence, macd_histogram_improving | 5.96% |
| 2026-09-24T15:45Z | 2026-09-24T17:00Z | 2026-09-24T14:30Z | **150 min** | macd_histogram_improving, high_volume_spike | 13.35% |
| 2026-08-25T07:00Z | 2026-08-25T09:45Z | 2026-08-25T08:45Z | **60 min** | bullish_rsi_divergence, macd_histogram_improving | 5.72% |

**Avance médiane** : 157.5 min · **62.5 %** des détections précèdent l'entrée.

### Enseignement

Les détections à avance nulle ou quasi nulle sont majoritaires : l'alerte tombe souvent **sur** la bougie d'entrée, pas avant. Sur les 16 détections mesurées, 6 ont une avance de 0 minute.

## Retournements manqués (15m) — aucune alerte dans la fenêtre d'avertissement

| Creux | Entrée plausible | Prix au creux | Amplitude du mouvement ultérieur | Volatilité (ATR14 relatif) |
|---|---|---|---|---|
| 2026-09-25T21:15Z | 2026-09-26T10:00Z | 0.001646 | **41.56%** | 0.67% |
| 2026-09-16T12:00Z | 2026-09-16T15:45Z | 0.001461 | **11.77%** | 0.65% |
| 2026-09-08T04:00Z | 2026-09-08T07:30Z | 0.001706 | **8.38%** | 0.47% |
| 2026-08-23T20:15Z | 2026-08-23T21:00Z | 0.001770 | **8.36%** | 0.66% |
| 2026-08-27T05:30Z | 2026-08-27T09:00Z | 0.001820 | **7.69%** | 0.56% |
| 2026-09-06T13:15Z | 2026-09-06T16:15Z | 0.001708 | **6.91%** | 0.39% |
| 2026-09-05T00:30Z | 2026-09-05T01:45Z | 0.001712 | **6.66%** | 0.52% |
| 2026-09-01T00:00Z | 2026-09-01T03:45Z | 0.001717 | **4.66%** | 0.56% |
| 2026-08-30T07:30Z | 2026-08-30T13:00Z | 0.001692 | **4.02%** | 0.49% |
| 2026-09-12T15:30Z | 2026-09-12T21:45Z | 0.001671 | **2.39%** | 0.53% |
| 2026-09-14T23:30Z | 2026-09-15T00:45Z | 0.001637 | **1.41%** | 0.54% |
| 2026-10-02T12:45Z | 2026-10-02T16:00Z | 0.002136 | **1.31%** | 0.85% |

**12 retournements manqués sur 28** (42.9 %).

### Enseignement

Les mouvements manqués ne sont pas rares : c'est la **couverture temporelle** du signal qui est en cause, pas la rareté des retournements. Un détecteur qui ne se déclenche que 12 % du temps ne peut pas être présent sur chaque creux.

## Faux rebonds et contradictions

- Alertes **sans** retournement de référence associé : 708 sur 724 (97.8 %).
- Rapport signal/retournement : **26:1**. Le détecteur signale environ 26 fois plus que ce qu'il ne signale utilement.
- Sur 4h, le détecteur est **significativement moins bon que le hasard** (percentile 0.06) et ne détecte **0** retournement de référence sur 40.
- Sur 1h, 66 retournements de référence sur 72 sont manqués dans la fenêtre d'avertissement de 6 h.

### Enseignement

La panne n'est pas dans la **qualité** du signal mais dans son **volume** et sa **couverture**. Réduire la densité d'alerte et ajouter une confirmation explicite est prioritaire sur tout réglage de seuil.

## Preuves les plus fréquentes dans les alertes (15m)

- `weak_trend_divergence` : 335 épisodes
- `higher_timeframe_alignment` : 317 épisodes
- `macd_histogram_worsening` : 289 épisodes
- `macd_histogram_improving` : 280 épisodes
- `high_volume_spike` : 257 épisodes
- `moderate_volume_increase` : 115 épisodes
- `bullish_rsi_divergence` : 61 épisodes
- `bearish_rsi_divergence` : 57 épisodes
- `rsi_overbought` : 28 épisodes
- `momentum_rising_after_decline` : 25 épisodes
- `stochastic_bullish_crossover` : 23 épisodes
- `near_critical_support` : 21 épisodes
- `rsi_oversold` : 19 épisodes
- `momentum_falling_after_rise` : 14 épisodes
- `stochastic_bearish_crossover` : 9 épisodes

### Enseignement

Les preuves de **contexte** (`weak_trend_divergence`, `higher_timeframe_alignment`) dominent, alors que les preuves directionnelles (`bullish_rsi_divergence`, `rsi_oversold`, motifs de bougies) sont rares. Or le statut `ALERTE_PRÉCOCE` exige 2 catégories distinctes : l'alignement de tendance sur 4 h/1 j suffit souvent à déclencher l'alerte, ce qui explique la densité excessive et l'absence de pouvoir prédictif sur 4 h.

## Ce que le journal ne peut pas encore contenir

- **Confirmations** : le statut `CONFIRMATION` n'est jamais assigné par le détecteur ; il n'y a donc rien à journaliser.
- **Invalidations suivies** : la règle `close < 0.001526` s'applique en continu (9,4 % des bougies en 15m) ; elle reflète un niveau figé, pas une information de marché exploitable.
- **Contexte BTC / ETH / TEL-BTC** : absent du dépôt, aucun point de comparaison possible.
- **Régime haussier** : la fenêtre testée (août → octobre 2026) est baissière. Les faux rebonds en tendance haussière ne sont pas représentés.


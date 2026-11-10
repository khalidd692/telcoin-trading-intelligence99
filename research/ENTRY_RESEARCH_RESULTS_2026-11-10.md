# Exécution Kraken et études d’événements — 10 novembre 2026

## Reproduction

```sh
python -m scripts.strategy_backtest.run_validation
python -m scripts.strategy_backtest.entry_study
python -m unittest tests.test_entry_study tests.test_strategy_engine tests.test_strategy_phase_continuity tests.test_strategy_phase_risk tests.test_kraken_history_quality
python -m unittest discover -s tests
```

## Replay du protocole figé

Le runner conserve son CSV historique : 1 741 lignes source, 1 740 bougies retenues après exclusion de la mèche 4h, segments de 1 et 1 739 bougies. Chargement par le validateur, marché déclaré KRAKEN:TELUSD, source TradingView MCP, hash source `96b50ad431ff3c78cefc2a18b37d6cc3224ec82e9a67d7812a0e172535674aa4`. Aucun téléchargement ni interpolation.

| Phase | Candidats | Rejets RR | Trades (brut/central/prudent) | Capital initial → final USD |
|---|---:|---:|---|---|
| IS | 39 | 39 | 0 / 0 / 0 | 1000.00 → 1000.00 |
| VAL | 7 | 7 | 0 / 0 / 0 | 1000.00 → 1000.00 |
| OOS | 7 | 7 | 0 / 0 / 0 | 1000.00 → 1000.00 |

Branches exclusives : A (EMA20) 42, B (retest) 10, A+B 1 ; total 53. Maximum RR brut : 0,8010878084. Tous rejetés par `rejet:rr_inferieur_au_minimum`. Les règles restent inchangées.

Absence de position : variation du capital 0 %, frais et slippage effectivement simulés 0 USD, aucun drawdown du capital sans position. Expectancy par trade, win rate et profit factor : non calculables (n=0). Ne pas publier de performance de stratégie validée.

Coûts hypothétiques par côté : brut 0/0 ; central frais 0,25 % et slippage 0,10 % ; prudent frais 0,40 % et slippage 0,30 %. Aucun spread historique mesuré, frais personnels et liquidité historique inconnus. Ces scénarios ne constituent pas une attestation du coût Kraken.

Le journal des candidats contient les 53 motifs et phases ; le journal des trades contient son en-tête et aucune transaction. Les anciens résultats restent accessibles au commit 9ea45ae5 ; les fichiers results/strategy_validation sont régénérés explicitement. Le fichier historique config_phases.json n’a pas été réécrit : les phases et effectifs réellement utilisés sont dans results.json.

La concordance simulation continue/phases est vérifiée dans le runner pour chaque scénario. Avec zéro trade cette vérification est nécessaire mais peu informative ; les tests synthétiques existants couvrent les traversées de position, le capital, le cooldown et la perte quotidienne avec des transactions non nulles.

## Comparaison prédictive, sans admission paper

Le registre research/ENTRY_STUDY_PROTOCOL.json a été écrit avant cette exécution locale, sans scellement externe. Il reprend trois hypothèses documentées, sans nouvelle optimisation. Les historiques ont déjà été explorés : IS/VAL/OOS sont des descriptions chronologiques exposées, pas un test final vierge.

- Divergence : réutilisation exacte de agent_analysis.has_rsi_divergence sur deux fenêtres passées de cinq clôtures.
- Survente : RSI14 < 30 et clôture sous EMA50, piste déjà documentée.
- Repli : condition de la branche EMA20 existante, sans filtre RR.

Le RSI réutilisé est celui de agent_analysis.rsi_series, calculé sur les variations arithmétiques des 14 dernières barres ; il n’est pas le RSI Wilder de certaines anciennes explorations. Ce résultat ne reproduit donc pas à l’identique leurs statistiques. Le détecteur complet v2 d’alerte/confirmation n’est pas remplacé ni présenté comme évalué ici ; la divergence est un de ses composants.

Indicateurs précalculés une fois par segment ; amorçage minimum 50 observations. Pas de combinaison de signaux ou de jointure multitimeframe. Mesure depuis l’ouverture suivante jusqu’à la clôture de la H-ième bougie, MFE/MAE sur la même fenêtre. Fenêtres complètes dans un même segment et une même phase ; déduplication des fenêtres chevauchantes par hypothèse et horizon. Aucun ordre, stop, objectif ou sizing inventé.

Référence descriptive : toutes les observations admissibles du même segment, phase et régime EMA20>EMA50. Elle inclut les événements ; elle n’est pas un groupe de contrôle causal indépendant. Excès = mouvement après signal moins moyenne de cette référence. Les mesures restent brutes et ne sont pas des P&L.

| TF | Hypothèse | Horizon h | Épisodes | Mouvement moyen % | Excès moyen points % | Holm p |
|---|---|---:|---:|---:|---:|---:|
| 15m | divergence | 6 | 3 | -0.809 | +0.339 | 1.000 |
| 15m | oversold | 6 | 3 | +0.825 | +1.973 | 1.000 |
| 15m | pullback | 6 | 3 | -1.023 | +0.126 | 1.000 |
| 15m | divergence | 24 | 0 | N/A | N/A | 1.000 |
| 15m | oversold | 24 | 0 | N/A | N/A | 1.000 |
| 15m | pullback | 24 | 0 | N/A | N/A | 1.000 |
| 15m | divergence | 72 | 0 | N/A | N/A | 1.000 |
| 15m | oversold | 72 | 0 | N/A | N/A | 1.000 |
| 15m | pullback | 72 | 0 | N/A | N/A | 1.000 |
| 1h | divergence | 6 | 152 | -0.283 | -0.262 | 1.000 |
| 1h | oversold | 6 | 121 | -0.071 | +0.042 | 1.000 |
| 1h | pullback | 6 | 55 | +0.473 | +0.524 | 1.000 |
| 1h | divergence | 24 | 64 | -0.674 | -0.466 | 1.000 |
| 1h | oversold | 24 | 54 | +0.334 | +0.764 | 1.000 |
| 1h | pullback | 24 | 27 | +2.223 | +2.362 | 1.000 |
| 1h | divergence | 72 | 19 | -0.949 | -2.030 | 1.000 |
| 1h | oversold | 72 | 18 | +0.954 | +0.283 | 1.000 |
| 1h | pullback | 72 | 10 | +5.883 | +4.631 | 1.000 |
| 4h | divergence | 6 | 194 | +0.099 | +0.119 | 1.000 |
| 4h | oversold | 6 | 158 | +0.131 | +0.146 | 1.000 |
| 4h | pullback | 6 | 37 | -0.040 | +0.041 | 1.000 |
| 4h | divergence | 24 | 100 | +0.771 | +0.841 | 1.000 |
| 4h | oversold | 24 | 65 | +0.528 | +0.570 | 1.000 |
| 4h | pullback | 24 | 25 | +0.572 | +0.890 | 1.000 |
| 4h | divergence | 72 | 57 | -0.281 | -0.164 | 1.000 |
| 4h | oversold | 72 | 43 | +2.328 | +2.471 | 0.675 |
| 4h | pullback | 72 | 16 | -0.344 | -0.234 | 1.000 |

Les journaux CSV conservent horaires de signal, référence, issue, segment, phase, régime, MFE/MAE et référence. Les JSON conservent comptages bruts, exclusions de fenêtre/phase et chevauchement, détails par phase, intervalles et empreintes du protocole et du code.

## Incertitude et contrôles

Bootstrap à 999 tirages, graine 99, grappes par semaine civile communes aux segments et phases afin de ne pas traiter chaque petit segment comme indépendant. Test unilatéral de moyenne excédentaire sous nullité recentrée ; intervalles en unités de rendement décimal dans le JSON. Correction de Holm sur les 27 comparaisons globales. Pas d’inférence avec moins de 30 épisodes ou 10 grappes ; p manquante traitée comme 1 pour la correction, sans devenir une mesure de preuve.

Aucun résultat significatif corrigé (minimum Holm p = 0.675). Les semaines adjacentes peuvent rester dépendantes ; le bootstrap est une approximation exploratoire, pas une certification d’indépendance ni une nouvelle preuve OOS. Les comparaisons par phase restent descriptives et les effectifs entre timeframes/horizons ne sont pas additionnés.

Qualité des sources pour la découverte : 15m 5 590 bougies/802 segments ; 1h 6 796/167 ; 4h 1 746/2. Aucune observation 15m à 24h ou 72h après amorçage : un horizon de 24h nécessite 96 bougies futures, au-delà de ce qui reste disponible aux signaux retenus. À 6h : trois épisodes par hypothèse, deux grappes seulement, donc aucune inférence.

Sensibilité à l’amorçage : sur le dernier point du plus long segment, redémarrage depuis 100/200/400 observations quand disponibles. À 100 : écart relatif EMA50 15m +0,2454 %, 1h +0,3280 %, 4h −0,0974 %. Aucun des trois états de signal au dernier point ne change. Cela ne prouve pas la stabilité sur tous les événements, et ne justifie pas de raccourcir l’amorçage.

Les tests ajoutés vérifient la référence suivante et les excursions sur un cas manuel, le rejet des trous, l’invariance des signaux au futur et aux préfixes, les exclusions de phase/chevauchement, Holm, et le comportement nul/positif et reproductible du bootstrap. Les tests existants couvrent les règles du simulateur et la quarantaine.

## Décision

**AUCUNE STRATÉGIE VALIDÉE.** Certaines associations brutes sont positives mais aucune ne franchit le contrôle statistique ; les effectifs, coûts, régime, données fragmentées et holdout déjà exposé empêchent une validation économique.

Prochaine priorité unique : réserver un nouveau bloc chronologique Kraken TEL/USD non consulté, puis réévaluer une seule fois ces définitions figées, sans retoucher les paramètres sur les résultats présents. Aucun changement de règle, de Smart View, de risque, de spread maximal, aucun ordre ni déploiement.

## Vérification de livraison

40 tests ciblés réussis. Suite complète : 423 tests, 3 ignorés, aucun échec. Cohérence vérifiée entre protocole/empreintes de code, 27 comparaisons et 1 224 observations événement-horizon du journal (non assimilables à 1 224 observations indépendantes). Aucun paramètre du moteur ni des risques modifié.

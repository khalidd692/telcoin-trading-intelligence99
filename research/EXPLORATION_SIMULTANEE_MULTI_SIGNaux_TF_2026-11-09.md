# Exploration simultanée multi-signaux et multi-timeframes — KRAKEN:TELUSD — 2026-11-09

## Cadre
Recherche sur KRAKEN:TELUSD exclusivement, aucune transaction réelle, aucun changement de stratégie, de board ou de configuration Paper Trading. Cette passe combine (1) simulation indépendante OHLCV, (2) tests historiques automatiques TradingView, (3) comparaison de déclencheurs sur 4h/1h/15m.

## Qualité des données
- 4h : 1 748 bougies du 2026-01-22 12:00 UTC au 2026-11-09 20:00 UTC ; 1 rupture de cadence.
- 1h : 5 000 bougies du 2026-04-12 17:00 UTC au 2026-11-09 20:00 UTC ; 64 ruptures. Les séries ont été segmentées ; 18 segments d'au moins 80 barres, 3 481 barres conservées, 1 519 écartées (segments trop courts).
- 15m : 5 000 bougies du 2026-09-09 11:15 UTC au 2026-11-09 20:15 UTC ; 656 ruptures. Segmentation stricte : seulement 3 segments d'au moins 80 barres, 318 barres conservées et 4 682 écartées. 15m est actuellement trop fragmenté pour une validation.
- La dernière bougie 4h peut être en formation. Les anomalies de données et les limites de profondeur TradingView restent à prendre en compte.

## Simulation indépendante 4h : familles et filtres de régime
Hypothèses : signal sur clôture, entrée à l'ouverture suivante, stop sous le plus bas des 5 dernières barres moins 0,05 ATR, cible 1,5R, expiration 20 barres, trades non chevauchants, stop prioritaire si stop et cible sont touchés dans la même barre, coût total aller-retour simulé 0,70% ou stress 1,40%. IS/OOS chronologique 70/30. Ce n'est pas un moteur d'exécution Kraken et les coûts ne sont pas vérifiés.

Meilleurs résultats bruts du balayage (coût 0,70% / stress 1,40%) :
| Déclencheur + filtre | Trades | Moyenne nette 0,70% | PF 0,70% | Moyenne nette 1,40% | PF 1,40% | OOS trades |
|---|---:|---:|---:|---:|---:|---:|
| RSI croise sa moyenne + clôture > EMA200 | 14 | +4,124% | 3,47 | +3,424% | 2,83 | 7 |
| RSI croise sa moyenne + EMA20>EMA50 | 18 | +3,200% | 2,89 | +2,500% | 2,30 | 5 |
| RSI croise sa moyenne + EMA20>EMA50 + ADX>=20 | 15 | +3,003% | 2,53 | +2,303% | 2,05 | 4 |
| RSI croise sa moyenne sans filtre | 91 | +1,075% | 1,60 | +0,375% | 1,18 | 29 |
| RSI croise sa moyenne + ADX>=20 | 72 | +0,845% | 1,44 | +0,145% | 1,06 | 24 |
| RSI35 croise à la hausse + ADX>=20 | 18 | +1,108% | 1,71 | +0,408% | 1,22 | 8 |
| EMA20 pullback + clôture > EMA200 | 12 | +1,502% | 1,80 | +0,802% | 1,37 | 6 |
| CCI remonte au-dessus de -100 + ADX>=20 | 54 | +0,291% | 1,17 | -0,409% | 0,80 | 19 |

Ces résultats sont exploratoires et exposés au biais de sélection (plusieurs variantes testées). Les meilleures lignes ont de petits échantillons OOS et ne sont pas indépendantes de l'exploration. Aucun résultat ne doit être choisi comme stratégie à ce stade.

Autres constats 4h :
- RSI30 simple : 19 trades dans cette passe (warm-up 210 barres), moyenne nette +1,255% à 0,70%, +0,555% à 1,40%, seulement 6 OOS.
- RSI40 cross : 58 trades ; moyenne +0,359% à 0,70% mais -0,341% à 1,40%.
- Sweep/reclaim 10 : 53 trades ; moyenne -0,457% à 0,70%.
- Sweep/reclaim 20 : 35 trades ; moyenne -0,687%.
- Engulfing haussier : 69 trades ; moyenne -0,533%.
- Donchian20 breakout : 10 trades ; moyenne -4,636%.
- MACD EMA12/26 cross : 24 trades ; moyenne -1,583%.
- Higher-low + break prior high : 76 trades ; moyenne -0,661%.

## Dépistage segmenté 1h et 15m
Simulation 1h segmentée, coûts 0,70%, stop/target structurels identiques :
| Signal | Trades | Moyenne nette | PF |
|---|---:|---:|---:|
| RSI30 cross | 26 | +0,332% | 1,32 |
| Donchian20 breakout | 10 | +2,150% | 2,22 |
| Bull engulf | 67 | +0,029% | 1,02 |
| RSI35 cross | 49 | -0,518% | 0,65 |
| RSI cross SMA | 118 | -0,200% | 0,87 |
| Sweep10 reclaim | 69 | -0,692% | 0,46 |
| BB lower reclaim | 60 | -0,395% | 0,67 |
| EMA20 pullback | 57 | -0,427% | 0,72 |
| MACD cross | 22 | -0,302% | 0,85 |

Attention : ces agrégats 1h sont des écrans exploratoires sans split IS/OOS publié dans ce tableau. Donchian20 n'a que 10 trades ; aucune validation. Segmentation correcte mais la profondeur disponible est faible.

15m : 318 barres utilisables seulement. Les résultats apparents (2 à 5 trades pour la plupart des signaux) sont trop faibles pour toute conclusion. Ne pas utiliser le 15m comme filtre de validation actuellement.

## Tests historiques automatiques TradingView (événements, pas des trades)
Demandes exécutées automatiquement le 2026-11-09, fenêtre récente de 1 000 bougies :
| Setup | TF | Horizon | N | Succès | Taux de base | Rendement médian forward |
|---|---:|---:|---:|---:|---:|---:|
| RSI croise sa moyenne à la hausse | 1h | 12 | 79 | 44,3% | 40,1% | -0,21% |
| RSI passe sous 30 | 1h | 12 | 21 | 57,1% | 40,1% | +0,41% |
| Réintégration Bollinger basse | 1h | 12 | 37 | 100% | 100% | +0,23% |
| Gap down fill | 1h | même barre | 60 | 56,7% | n/a | 0% |
| RSI croise sa moyenne à la hausse | 4h | 12 | 82 | 40,2% | 37,4% | -1,29% |
| Réintégration Bollinger basse | 4h | 12 | 31 | 100% | 100% | -0,30% |
| Gap up fill | 4h | même barre | 19 | 84,2% | n/a | -0,08% |
| Gap down fill | 4h | même barre | 16 | 68,8% | n/a | -0,78% |

Interprétation : les taux de réintégration Bollinger de 100% ne discriminent rien, car le taux de base est également 100%. Les gaps sont des événements de microstructure, pas un signal long prouvé. Le RSI oversold 1h a un taux de réussite supérieur au taux de base sur 21 occurrences, mais l'intervalle de confiance est large (36,5–75,5%) et le rendement médian reste modeste. Le RSI cross-up 4h ne dépasse que légèrement son taux de base et affiche un rendement médian négatif.

## Contexte technique instantané à 2026-11-09 ~20:25 UTC
Prix TradingView : 0,0014919 USD.
- 15m : BUY (RSI 57,4 ; ADX 17,8 ; prix au-dessus EMA20/50 mais sous EMA200).
- 1h : NEUTRAL (RSI 48,1 ; ADX 35,3 ; EMA20 sous EMA50 et EMA200).
- 4h : SELL (RSI 45,9 ; ADX 26,0 ; EMA20 0,0015252, EMA50 0,0015056, EMA200 0,0015574).
- 1D : SELL (RSI 46,9 ; EMA20 0,0015205, EMA50 0,0016071, EMA200 0,0020231).
Lecture : rebond court terme contre tendance supérieure encore baissière. Aucun signal multi-timeframe confirmé.

## Demandes TradingView en file
Les cinq demandes plus anciennes sont encore queued :
- rq_3fbd24d7858c4e9e — sweep/reclaim 15m/1h
- rq_304062157ba54962 — breakout/retest 4h
- rq_81fc211a3a43405b — variantes swing-low
- rq_4f665100b71f4f6a — règle swing-low exacte
- rq_919a53432a114077 — règles et blocages paper
Elles n'ont pas été dupliquées. Huit tests automatiques nouveaux (différents horizons/timeframes) ont répondu immédiatement et sont inclus ci-dessus.

## Conclusion opérationnelle
Aucune stratégie n'est validée. Les filtres EMA200 / EMA20>EMA50 semblent améliorer certains résultats RSI 4h, mais les petits échantillons OOS et l'essai de nombreuses variantes imposent une validation indépendante. Le 1h est nettement moins bon sur la plupart des signaux et le 15m est trop fragmenté. Ne pas activer de stratégie paper sur ces résultats.

## Suite prioritaire
1. Refaire les candidats 4h sur un historique étendu, avec variantes verrouillées avant test, période OOS scellée et correction des biais d'exécution.
2. Auditer la stratégie swing-low avec pivot confirmé 10/10 et la comparer à des déclencheurs RSI/EMA sans modifier la stratégie existante.
3. Vérifier frais Kraken, spread et slippage à partir de données publiques fiables avant de conclure au net.
4. Garder les données 1h/15m segmentées et exclure les trous ; obtenir plus d'historique propre avant usage.

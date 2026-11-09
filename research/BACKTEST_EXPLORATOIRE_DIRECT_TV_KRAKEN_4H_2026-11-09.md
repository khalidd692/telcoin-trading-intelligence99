# Backtest exploratoire indépendant — KRAKEN:TELUSD 4H — 2026-11-09

## Objet
Contourner la file de recherche TradingView en utilisant directement l'historique OHLCV accessible via le MCP TradingView. Recherche uniquement. Aucun ordre, aucun changement de stratégie, de board ou de configuration Paper Trading.

## Données
- Instrument : `KRAKEN:TELUSD`
- Source : TradingView MCP OHLCV.
- Intervalle : 4h.
- Couverture : 1 748 barres reçues, du 2026-01-22 12:00 UTC au 2026-11-09 20:00 UTC.
- Une rupture de cadence de 8h a été détectée ; la barre située immédiatement après la rupture a été exclue des signaux/exécutions.
- La dernière barre est en formation au moment de la collecte ; elle n'est pas utilisée comme signal exploitable.
- Une mèche extrême apparaît sur la toute première barre (high 0.020 contre close 0.004029). Elle est conservée dans les données, mais constitue un avertissement de qualité historique et peut affecter ATR/volatilité.
- Le flux TradingView peut être différé selon l'abonnement. Les frais et slippage Kraken réels ne sont pas vérifiés dans ce test.

## Simulation
- Signal confirmé à la clôture de la barre 4h.
- Entrée à l'ouverture de la barre suivante.
- Stop structurel : plus bas minimum de la barre signal et des 4 barres précédentes, moins 0,05 ATR(14).
- Filtre de risque : distance entrée-stop positive et <= 2,5 ATR(14).
- Cible fixe : 1,5R.
- Expiration : 20 barres 4h.
- Trades non chevauchants.
- Si stop et cible sont touchés dans la même barre, hypothèse conservatrice : stop exécuté en premier.
- Coûts testés en scénarios de coût total aller-retour : 0,70% et 1,40%. Ce sont des hypothèses de stress, pas des frais Kraken constatés.
- IS/OOS chronologique : premières 70% des barres pour IS, dernières 30% pour OOS.
- Les indicateurs sont calculés sur la série chronologique ; aucune interpolation de la rupture n'est effectuée.

## Résultats — dépistage de familles de signaux

| Signal | Coût A/R | Trades | Win rate | Rendement net moyen / trade | PF net | Max drawdown | IS moyen (n) | OOS moyen (n) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| RSI(14) croise à la hausse 30 | 0,70% | 22 | 63,6% | +1,786% | 2,14 | -18,70% | +1,530% (16) | +2,471% (6) |
| RSI(14) croise à la hausse 30 | 1,40% | 22 | 63,6% | +1,086% | 1,60 | -21,98% | +0,830% (16) | +1,771% (6) |
| Réintégration Bollinger basse | 0,70% | 41 | 41,5% | +0,204% | 1,13 | -36,96% | +0,012% (29) | +0,668% (12) |
| Réintégration Bollinger basse | 1,40% | 41 | 39,0% | -0,496% | 0,75 | -47,29% | -0,688% (29) | -0,032% (12) |
| Sweep du plus bas 10 barres + clôture de réintégration haussière | 0,70% | 55 | 41,8% | -0,348% | 0,82 | -35,29% | -0,241% (36) | -0,551% (19) |
| Sweep du plus bas 10 barres + clôture de réintégration haussière | 1,40% | 55 | 41,8% | -1,048% | 0,54 | -51,64% | -0,941% (36) | -1,251% (19) |
| Pullback EMA20 en tendance EMA20>EMA50 | 0,70% | 33 | 39,4% | -0,202% | 0,90 | -16,31% | -0,589% (27) | +1,538% (6) |
| Pullback EMA20 en tendance EMA20>EMA50 | 1,40% | 33 | 36,4% | -0,902% | 0,63 | -30,87% | -1,289% (27) | +0,838% (6) |
| Cassure Donchian 20 + volume > 1,2× moyenne 20 | 0,70% | 8 | 37,5% | -2,298% | 0,55 | -26,53% | -1,666% (5) | -3,353% (3) |
| Cassure Donchian 20 + volume > 1,2× moyenne 20 | 1,40% | 8 | 37,5% | -2,998% | 0,46 | -29,23% | -2,366% (5) | -4,053% (3) |

## Contrôle de filtres autour du croisement RSI 30
- RSI30 + clôture au-dessus du plus haut précédent : 14 trades ; rendement net moyen +2,624% à 0,70% de coûts et +1,924% à 1,40%. OOS : seulement 3 trades. Échantillon trop faible.
- RSI30 + clôture au-dessus EMA20 : 0 trade.
- RSI30 + reprise EMA20 avec volume supérieur à sa moyenne : 0 trade.
- RSI30 + EMA20 ascendante : 0 trade.
- RSI<35 + avalement haussier : 4 trades ; moyenne nette -0,176% à 0,70% et -0,876% à 1,40%, OOS 3 trades.

## Lecture
1. Le croisement RSI30 est le seul signal de cette première passe à afficher une moyenne nette positive aux deux scénarios de coût. Mais 22 trades seulement, dont 6 OOS, et un drawdown simulé de 18,7% à 21,98% : ce n'est pas une preuve d'avantage robuste.
2. Les filtres plus stricts réduisent l'échantillon à 14 trades ou zéro. Ils ne constituent pas une confirmation.
3. Sweep/reclaim, Bollinger reentry et Donchian breakout ne montrent pas d'avantage net stable dans cette simulation.
4. Le pullback EMA20 a un IS négatif et un OOS positif sur seulement 6 trades : résultat non concluant.
5. Le rendement buy-and-hold sur la période ne doit pas être comparé directement sans traiter l'anomalie de la première barre et les exécutions ; il n'est pas présenté comme benchmark validé ici.

## Statut
**EXPLORATION / DÉPISTAGE, PAS VALIDATION.** Aucun signal ne peut être promu en stratégie validée ou activé en paper sur cette seule base. Les coûts réels, le spread, le slippage, la qualité de la première barre, le régime BTC/ETH, et une période OOS beaucoup plus large restent à établir. L'objectif de 100 trades OOS indépendants n'est pas atteint.

## Prochaine étape
- Contrôler la qualité de l'historique, notamment la mèche initiale et les ruptures de cadence.
- Tester les variantes de structure/pivots confirmés avec délai explicite et sans lookahead.
- Séparer strictement les régimes et réaliser une validation chronologique plus large.
- Obtenir les frais Kraken applicables et des données de spread/liquidité avant d'affiner le modèle d'exécution.
- Ne pas dupliquer les cinq demandes TradingView encore en file ; poursuivre les simulations indépendantes avec OHLCV direct.

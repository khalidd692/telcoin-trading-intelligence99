# Audit indépendant parallèle — signaux long TEL/USD (2026-11-09)

## Périmètre
Données TradingView MCP, symbole KRAKEN:TELUSD, OHLCV brut. Recalcul exploratoire indépendant sur 4h et 1h. Aucun ordre placé, aucun tableau ni paramètre modifié.

## Données et segmentation
- 4h : 1 748 bougies reçues, 1 746 utilisables après exclusion des deux premières autour de l'anomalie initiale / discontinuité; période observée 2026-01-23 00:00 UTC au 2026-11-09 20:00 UTC.
- 1h : 6 798 bougies reçues. Les données sont très fragmentées; segmentation stricte conservant uniquement les segments d'au moins 120 bougies : 2 935 bougies utilisables sur 12 segments conservés (11 séparations entre segments conservés; 166 interruptions de cadence brutes observées dans le fichier agrégé). Les bougies exclues ne sont pas interpolées.
- La dernière bougie peut être en formation; ce test doit être reproduit sur des bougies clôturées seulement.
- Les séries 15m n'ont pas été utilisées dans ce calcul, car 801 interruptions de cadence ont été observées sur l'historique collecté.

## Méthode commune (écran, non validation)
- Signaux évalués à la clôture; entrée à l'ouverture de la bougie suivante.
- Un seul trade à la fois; pas de chevauchement.
- Stop conservateur : minimum des cinq derniers bas observés moins 0,05 ATR, avec plancher de distance 0,8 ATR et plafonnement à 2 ATR.
- Objectif 1,5R; expiration après 20 bougies.
- Si stop et cible sont touchés sur la même bougie, stop prioritaire.
- Coût appliqué de façon multiplicative à l'entrée et à la sortie : 0,80 % taker + 0,15 % slippage par côté (hypothèse de stress; le palier réel de l'utilisateur n'est pas connu).
- Découpage chronologique 60/40; indicateurs calculés sans franchir les discontinuités.
- Cet écran emploie des définitions explicites simplifiées des signaux. Il ne reproduit pas nécessairement le code exact de Claude ou des stratégies TradingView.

## Résultats — 4h
| Famille | Trades | Win % | Espérance nette / trade | PF | IS 60% | OOS 40% |
|---|---:|---:|---:|---:|---:|---:|
| Réentrée Bollinger basse (close précédent sous BB lower, clôture actuelle au-dessus) | 71 | 50,7 | -0,337 % | 0,86 | +0,579 % (40) | -1,518 % (31) |
| Cassure 20 barres + volume > 1,5× moyenne + close > EMA50 | 25 | 44,0 | -1,401 % | 0,73 | -1,086 % (9) | -1,578 % (16) |
| Sweep sous plus bas 10 barres + réintégration haussière | 67 | 44,8 | -1,128 % | 0,60 | -0,947 % (35) | -1,326 % (32) |
| Reprise EMA20 en EMA20 > EMA50 | 26 | 42,3 | -1,124 % | 0,63 | -2,088 % (19) | +1,493 % (7) |

## Résultats — 1h
| Famille | Trades | Win % | Espérance nette / trade | PF | IS 60% | OOS 40% |
|---|---:|---:|---:|---:|---:|---:|
| Réentrée Bollinger basse | 102 | 37,3 | -1,198 % | 0,32 | -0,433 % (20) | -1,385 % (82) |
| Cassure 20 barres + volume > 1,5× moyenne + close > EMA50 | 46 | 45,7 | -1,823 % | 0,44 | -2,865 % (11) | -1,496 % (35) |
| Sweep sous plus bas 10 barres + réintégration haussière | 77 | 26,0 | -2,042 % | 0,14 | -1,956 % (11) | -2,056 % (66) |
| Reprise EMA20 en EMA20 > EMA50 | 53 | 35,8 | -1,332 % | 0,42 | +0,370 % (18) | -2,207 % (35) |

## Interprétation
1. Avec cette définition explicite et le coût taker stress, aucune des quatre familles n'est positive sur l'ensemble de la période.
2. La réentrée Bollinger 4h est positive sur les 60% initiaux, mais devient négative sur les 40% finaux : instabilité de régime, pas de validation.
3. La cassure avec volume est négative en 4h et 1h dans cet écran. Le résultat précédent communiqué par Claude (+1,7% / trade pour une autre définition) n'est donc pas reproduit ici; les règles exactes et la convention de coûts doivent être alignées avant comparaison.
4. Les sweeps/reclaims simples sont faibles, surtout en 1h. Cela ne réfute pas les variantes structurelles multi-timeframes (CHoCH/BOS) qui n'ont pas encore été implémentées ici.
5. Les échantillons OOS restent petits pour plusieurs variantes. Aucun p-value, test d'entrées aléatoires ou correction de multiplicité n'a été calculé dans cet écran; ne pas présenter ces résultats comme une preuve statistique.

## Prochaines tâches
- Aligner les règles exactes de Bollinger et breakout-volume avec le backtest de Claude, puis reproduire strictement.
- Construire une validation événementielle CHoCH/BOS multi-timeframes avec pivots confirmés sans look-ahead.
- Refaire avec plusieurs scénarios de coûts maker/taker et slippage; obtenir le palier réel et des mesures de spread/liquidité avant paper trading.
- Exclure les bougies en formation et effectuer un walk-forward / test de bootstrap par blocs.
- Aucune stratégie validée; aucun signal d'achat n'est émis par cet audit.

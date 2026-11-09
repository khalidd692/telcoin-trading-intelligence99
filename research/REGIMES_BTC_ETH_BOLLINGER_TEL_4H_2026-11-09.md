# Régimes BTC/ETH et réentrée Bollinger TEL — exploration 4h

Date : 2026-11-09 UTC
Instrument testé : KRAKEN:TELUSD. BTC/ETH ne servent qu'à classer le régime, jamais à générer le signal.
Aucun ordre ou changement de stratégie.

## Données
- TEL/USD 4h : 1 748 bougies
- BTC/USD Kraken 4h : 3 000 bougies
- ETH/USD Kraken 4h : 3 000 bougies
- Régime défini par la dernière bougie BTC/ETH entièrement clôturée comparée à son EMA50 4h.
- Coût stress : 0,80 % taker + 0,15 % slippage par côté.

## Définition exploratoire
Réentrée Bollinger : clôture précédente sous la bande basse (SMA20 - 2 écarts-types sur les 20 clôtures précédentes), puis clôture actuelle au-dessus de la bande basse. Entrée à l'ouverture suivante; stop sous le plus bas des 5 dernières bougies moins 0,05 ATR, plafonné à 2 ATR; cible 1,5R; expiration 20 bougies; stop prioritaire.
Cette définition n'est pas garantie identique à celle du test de Claude.

## Résultats par régime
| Régime BTC/ETH | Trades | Win % | Espérance nette/trade | PF |
|---|---:|---:|---:|---:|
| Tous régimes | 71 | 45,1 | -0,490 % | 0,77 |
| BTC au-dessus EMA50 | 21 | 38,1 | -1,704 % | 0,30 |
| BTC sous EMA50 | 50 | 48,0 | +0,019 % | 1,01 |
| ETH au-dessus EMA50 | 19 | 42,1 | -1,366 % | 0,35 |
| ETH sous EMA50 | 52 | 46,2 | -0,171 % | 0,92 |
| BTC et ETH au-dessus EMA50 | 17 | 41,2 | -1,554 % | 0,30 |
| BTC et ETH sous EMA50 | 48 | 47,9 | +0,010 % | 1,00 |

## Conclusion
Le filtrage par EMA50 BTC/ETH n'améliore pas suffisamment la réentrée Bollinger. Les groupes sous EMA50 sont proches du point mort, mais ne montrent pas d'avantage exploitable après coûts. Les groupes haussiers ont de mauvais résultats, mais leurs échantillons sont petits. Pas de validation, pas de signal d'achat.

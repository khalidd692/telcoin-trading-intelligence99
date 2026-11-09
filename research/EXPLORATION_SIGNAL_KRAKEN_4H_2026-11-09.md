# Exploration exploratoire du signal — KRAKEN:TELUSD — 2026-11-09

## Source et périmètre
TradingView MCP, instrument KRAKEN:TELUSD, OHLCV 4H, 1,500 bougies du 2026-03-05 00:00 UTC au 2026-11-09 20:00 UTC. Les 1,500 bougies ont été reçues. La dernière bougie est potentiellement en formation et ne doit pas être utilisée pour une décision; les calculs ci-dessous sont un dépistage exploratoire, pas un backtest de stratégie exécutable. Les signaux sont calculés à la clôture et les rendements futurs sont mesurés depuis cette clôture, sans simulation d'exécution ni frais/slippage.

## Dépistage de familles simples
Indicateurs recalculés localement sur la série 4H : EMA20/50, RSI14 Wilder. Rendements bruts depuis le close du signal après 4, 12 et 24 barres (16h, 48h, 96h). "Recent" = signaux dans les derniers 20% de la série.

| Règle exploratoire | N | Moy. +4 barres | Moy. +12 | Moy. +24 | N récent | Moy. +12 récent |
|---|---:|---:|---:|---:|---:|---:|
| RSI14 < 30 | 85 | +0.27% | +2.17% | -1.38% | 19 | -2.02% |
| RSI14 croise au-dessus de 30 | 21 | -0.10% | +0.26% | -1.14% | 4 | -0.99% |
| Close recroise au-dessus EMA20 | 98 | -0.84% | -0.78% | -0.78% | 17 | +1.80% |
| RSI < 40 + close reprend EMA20 | 0 | — | — | — | 0 | — |
| Nouveau plus bas vs barre précédente puis clôture au-dessus du high précédent | 54 | -0.59% | -1.42% | -0.95% | 7 | -4.81% |
| EMA20 > EMA50 et close > EMA20 | 241 | -0.05% | +0.25% | -0.46% | 46 | +2.86% |

## Lecture
- RSI<30 a un rendement moyen brut favorable à 12 barres sur l'ensemble, mais le sous-échantillon récent est négatif. Cela contredit l'idée d'un effet stable et interdit de retenir cette règle seule.
- Le reclaim EMA20 est négatif en moyenne sur l'ensemble, mais positif sur la tranche récente. Le régime semble compter; il faut segmenter par tendance/volatilité et tester hors échantillon sans retoucher les seuils.
- Le pattern de balayage de plus bas + clôture au-dessus du high précédent est négatif dans ce dépistage, notamment sur la tranche récente.
- EMA20>EMA50 + close>EMA20 est légèrement positif à 12 barres globalement et sur la tranche récente, mais ce n'est pas un avantage démontré : le rendement brut ne prend pas en compte coûts, exécution, overlap des événements ni sélection multiple.
- RSI<40 + reclaim EMA20 n'a produit aucun événement sur cette définition et cette période.

## Limites et interdictions d'interprétation
- Ce dépistage ne constitue pas une stratégie ni un backtest de portefeuille.
- Les signaux se chevauchent et leurs rendements futurs ne sont pas indépendants.
- Pas de frais, spread, slippage, ordre, stop, cible, sizing, cash, drawdown ou contrainte de position simulés.
- La fenêtre de données est limitée à environ huit mois et ne couvre pas plusieurs cycles de marché.
- Le calcul inclut potentiellement la bougie courante en formation en fin de série; elle ne doit pas être considérée comme signal clôturé.
- Aucun résultat n'est validé et aucun réglage du paper broker n'a été modifié.

## Action de recherche suivante
1. Construire un protocole causal sur bougies clôturées seulement et segmenter les données 15m (nombre élevé de trous) ; contrôler les timestamps et les horizons.
2. Étudier les interactions régime 4H (EMA20/50, ADX, ATR) × déclencheur 1H × timing 15m, sans optimisation du holdout.
3. Attendre les cinq demandes TradingView déjà queued ; ne pas les dupliquer.
4. Acquérir les données Kraken publiques via les endpoints documentés (Ticker, OHLC limité à 720 points par requête, Depth, Trades, Spread). L'OHLC REST est limité à 720 points; pour un historique plus long, Kraken indique qu'il faut reconstruire les bougies à partir de l'historique Time & Sales paginé. Source officielle : https://support.kraken.com/articles/advanced-api-faq et https://support.kraken.com/articles/360000919986-public-endpoint-examples-you-can-try-them-directly-in-a-web-browser.

## Sécurité / continuité
Aucun ordre, changement de board, alerte, stratégie, paper setting ou code de production n'a été modifié. Exploration et rapport uniquement.

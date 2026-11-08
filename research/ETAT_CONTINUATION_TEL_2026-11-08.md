# TEL — point de reprise des étapes 1 à 3

Date : 8 novembre 2026
Instrument : KRAKEN:TELUSD — spot long-only — 4h
Périmètre : recherche/backtest uniquement. Aucun ordre réel ou paper, aucun accès au compte Kraken, aucune modification de stratégie TradingView.

## Étape 1 — VALIDÉE
- Historique TradingView 4h récupéré : 1 741 bougies clôturées.
- Fenêtre : 2026-01-22 12:00 UTC à 2026-11-08 16:00 UTC.
- Dernière bougie en formation exclue.
- Dates chronologiques, aucun doublon ni anomalie OHLC/volume.
- Un gap de 8 heures repéré ; il n'est pas comblé artificiellement et les fenêtres traversant ce gap doivent être exclues.
- CSV de référence : data/KRAKEN_TELUSD_4h_2026-01-22_2026-11-08.csv
- Blob SHA : 3510de242d99533cb1fa941b9fb621d253a8b020.

## Étape 2 — VALIDÉE POUR LE PROTOCOLE DE TEST
Stratégie primaire TradingView : « TEL Kraken – repli 4h dans tendance » (strategy_id 6c0a7fe5-e946-4df7-8df7-d44aa89cbaa9 ; board 06d9cdf8-29ff-4d79-8d1c-5b5b7d1ed0ad).

Règles de référence :
- EMA20 > EMA50 et clôture 4h > EMA50.
- Branche EMA20 : low <= EMA20 ; bougie haussière (close > open) ; close > EMA20.
- Branche résistance/support : sommet confirmé 5/5 ; cassure par clôture au-dessus ; retest ultérieur où low atteint le niveau et close reste au-dessus ; bougie de confirmation haussière clôturant au-dessus EMA20.
- Pivots 5/5 : un pivot devient disponible seulement après clôture des cinq bougies à droite. Aucun lookahead.
- Signal à la clôture t ; entrée à l'ouverture de t+1.
- ATR(14) Wilder ; stop sous le dernier pivot bas 5/5 confirmé moins 0,5 ATR.
- Objectif : première résistance confirmée au-dessus de l'entrée ; RR brut minimum 1,51, sinon signal rejeté.
- Expiration : clôture de la 20e bougie après l'entrée si stop/objectif non touché.
- Un seul trade à la fois, pas de renfort ni chevauchement.
- Collision stop/objectif dans une même bougie : stop prioritaire.
- Gap de données non traversé ; aucune interpolation.
- Frais et slippage séparés, puis intégrés au P&L net. Les taux Kraken réels ne sont pas encore vérifiés.

Réserves : la stratégie TradingView originale n'a pas été modifiée ; ses huit rule_checks étaient « unsettled ». La présente spécification est celle du test, pas une validation de rentabilité.

## Étape 3 — EN COURS
Tester séparément :
1. branche EMA20 ;
2. branche résistance devenue support ;
3. combinaison des deux, avec déduplication des signaux.

Conditions :
- mêmes données, règles d'exécution et coûts pour les trois variantes ;
- séparation chronologique IS/OOS, sans optimisation sur OOS ;
- résultats bruts et nets, nombre de trades, expectancy en R, profit factor, drawdown, coûts, raisons de sortie, exclusions pour gaps ;
- seuil de travail : au moins 100 trades OOS ; en dessous, verdict « DONNÉES INSUFFISANTES ».
- Aucun verdict de rentabilité sans expectancy nette positive, PF > 1,2, borne basse de confiance positive et robustesse temporelle.
- Les taux de frais/slippage restent des scénarios provisoires tant que les frais exacts ne sont pas vérifiés.

## Règles de sécurité et de gouvernance
- Paper trading exclusivement si une étape future le permet, mais aucun paper order sans autorisation explicite.
- Aucun ordre réel, aucun accès au compte Kraken réel, aucun trading automatique.
- Ne pas modifier le board, les stratégies, paramètres, scripts originaux, dépôt, déployer, commit/merge autre chose que le présent document de suivi et les données explicitement autorisées.
- Ne jamais confondre hypothèse, test incomplet et stratégie validée.
- Reprendre directement à l'étape 3 à la prochaine session ; ne pas recommencer les étapes 1 et 2.

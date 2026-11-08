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
- Branche résistance/support : sommet confirmé 5/5 ; cassure par clôture au-dessus ; premier retest ultérieur où low atteint le niveau et close reste au-dessus ; bougie de confirmation haussière clôturant au-dessus EMA20.
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

## Étape 3 — PREMIER REPLAY EFFECTUÉ, VALIDATION INCOMPLÈTE
Données utilisées : 1 741 bougies clôturées, dernière bougie en formation exclue. Un gap de 8 h est présent ; aucune interpolation. Indicateurs recalculés sur 4h : EMA20/EMA50 et ATR(14) Wilder. Pivots 5/5 disponibles après les cinq bougies de droite. Split chronologique 70/30 ; début OOS : 2026-08-13 16:00 UTC.

Diagnostic des candidats :
- Branche EMA20 : 336 bougies en tendance ; 43 contacts EMA20 avec confirmation haussière ; 43 candidats disposant d'un creux confirmé et d'une résistance cible ; 0/43 atteint le RR brut minimum 1,51. RR maximal observé : environ 0,80.
- Branche résistance devenue support : 81 cassures de pivots hauts confirmés ; 69 premiers retests ; 55 retests avec confirmation haussière au-dessus EMA20 ; 30 candidats avec creux et cible identifiables ; 0/30 atteint le RR brut minimum 1,51. RR maximal observé : environ 0,295.
- Combinaison dédupliquée : 0 setup admissible.

Verdict provisoire : aucune entrée admissible dans ce premier replay. Aucun trade n'a donc été exécuté dans la simulation ; expectancy, profit factor, drawdown et statistiques OOS ne sont pas calculables (n=0). Ce résultat ne prouve ni rentabilité ni absence définitive d'opportunité : il montre que la règle actuelle de cible/RR filtre tous les candidats observés sur cette période.

Deux scénarios de coûts prévus, non vérifiés sur le compte Kraken :
- central : frais 0,25 % + slippage 0,10 % par côté ;
- prudent : frais 0,40 % + slippage 0,30 % par côté.
Comme aucun candidat n'a franchi le filtre RR, aucun P&L net n'est calculable. Ne pas présenter ces taux comme les frais réels.

Limite technique à corriger avant de considérer l'étape 3 achevée : le moteur strict existant ne reproduit pas exactement la spécification (notamment ATR simple au lieu de Wilder et absence de la branche résistance/support). Le replay ci-dessus est un premier calcul indépendant des règles, pas encore un audit complet du moteur ni une validation statistique. La règle de résistance/support utilise le premier retest après cassure confirmée ; pivots hauts/bas utilisent une convention déterministe de gestion des égalités.

Prochaine action à la reprise :
1. Construire/auditer un moteur dédié aux deux branches, en vérifiant les signaux et les entrées/sorties sur cas unitaires.
2. Réconcilier les calculs avec le CSV GitHub et conserver les fenêtres autour du gap exclues.
3. Produire un journal trade-par-trade et les résultats IS/OOS sous les deux scénarios de coûts.
4. Conclure « DONNÉES INSUFFISANTES » dès que l'OOS compte moins de 100 trades ; ne pas relâcher le seuil RR pour fabriquer des signaux.

## Règles de sécurité et de gouvernance
- Paper trading exclusivement si une étape future le permet, mais aucun paper order sans autorisation explicite.
- Aucun ordre réel, aucun accès au compte Kraken réel, aucun trading automatique.
- Ne pas modifier le board, les stratégies, paramètres, scripts originaux, ni déployer. Le présent document de suivi et le CSV historique sont les seuls ajouts explicitement autorisés.
- Ne jamais confondre hypothèse, test incomplet et stratégie validée.
- Reprendre directement à l'étape 3 à la prochaine session ; ne pas recommencer les étapes 1 et 2.

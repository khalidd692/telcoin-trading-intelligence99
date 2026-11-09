# Résultats préliminaires — recherche TEL 4h

Date de calcul : 2026-11-09
Instrument : KRAKEN:TELUSD
Branche : research/tel-discovery-unrestricted
Statut : exploratoire uniquement — aucune stratégie validée

## Données et contrôle qualité

- Source : TradingView MCP, historique KRAKEN:TELUSD.
- 4h : 1 743 barres reçues du 2026-01-22 12:00 UTC au 2026-11-09 00:00 UTC.
- Une seule rupture d'horodatage détectée : 8 heures au début de l'historique.
- Dernière barre exclue des calculs car potentiellement en formation. Échantillon calculé : 1 742 barres, jusqu'au 2026-11-08 20:00 UTC.
- Première clôture observée : 0,004029 USD ; dernière clôture calculée : 0,001493 USD.
- 1h : 5 000 barres reçues, 65 ruptures ; historique supplémentaire disponible par pagination.
- 15m : 5 000 barres reçues, 664 ruptures ; couverture trop discontinue pour une simulation fiable sans nettoyage et segmentation.
- Le flux TradingView avertit que la dernière barre peut être en formation et que les données dépendent du plan et de l'abonnement de marché.

## Méthode du premier écran

Calculs indépendants effectués sur les barres 4h clôturées :
- EMA 20, EMA 50, RSI 14, ATR 14 (Wilder).
- Signal à la clôture de la barre i ; entrée à l'ouverture de i+1.
- Une position à la fois ; sorties évaluées dans l'ordre stop puis objectif puis sortie par indicateur.
- Coût central hypothétique : 0,70 % aller-retour. Stress : 1,40 % aller-retour.
- Les coûts ne sont pas confirmés par le barème personnel Kraken ; ils sont des hypothèses de sensibilité.
- Le premier écran n'intègre pas encore tous les garde-fous de paper broker (limite quotidienne, cooldown après stop, risque monétaire exact). Il ne constitue donc pas une simulation paper complète.

## Premier écran — six familles / variantes simples

| Variante | Trades | Win rate | Moyenne nette/trade | Profit factor brut | Drawdown composé net | Moyenne nette sous coût stress |
|---|---:|---:|---:|---:|---:|---:|
| Breakout Donchian 20 + EMA50 montante | 15 | 26,7 % | -2,76 % | 0,60 | -39,4 % | -3,46 % |
| Breakout Donchian 40 + EMA50 montante | 7 | 42,9 % | -0,55 % | 1,03 | -19,9 % | -1,25 % |
| Repli EMA20, EMA20 > EMA50 | 19 | 10,5 % | -1,68 % | 0,60 | -29,5 % | -2,38 % |
| Réversion RSI < 25 sous EMA50 | 8 | 87,5 % | +6,62 % | 11,62 | -6,2 % | +5,92 % |
| Réversion RSI < 30 sous EMA50 | 16 | 68,8 % | +4,62 % | 4,24 | -11,2 % | +3,92 % |
| Momentum RSI > 60 + EMA20 > EMA50 | 22 | 27,3 % | +1,28 % | 1,53 | -35,5 % | +0,58 % |

Le coût stress correspond à 1,40 % aller-retour. Le profit factor est calculé sur les rendements bruts agrégés, pas sur les rendements nets.

## Vérification chronologique initiale de la piste RSI < 30

Règle exploratoire : RSI14 < 30 et clôture sous EMA50 ; entrée à l'ouverture suivante ; stop à 2 ATR14 ; objectif à 1,5R ; sortie RSI > 50 ; durée maximale 12 barres ; coût aller-retour 0,70 %.

| Segment chronologique | Trades | Win rate | Moyenne nette/trade | Profit factor brut | Rendement composé net |
|---|---:|---:|---:|---:|---:|
| Début (60 %) | 7 | 71,4 % | +7,68 % | 7,21 | +63,6 % |
| Validation (20 %) | 5 | 60,0 % | +0,64 % | 1,60 | +2,4 % |
| Holdout récent (20 %) | 4 | 75,0 % | +4,18 % | 4,49 | +16,7 % |

Sensibilité du seuil RSI :
- RSI < 25 : 8 trades au total, seulement 3 dans le holdout.
- RSI < 28 : 12 trades au total, 4 dans le holdout.
- RSI < 30 : 16 trades au total, 4 dans le holdout.
- RSI < 32 : 19 trades au total, 4 dans le holdout.
- RSI < 35 : 25 trades au total, 8 dans le holdout ; win rate holdout 50 %, moyenne nette/trade +2,11 %.

Buy-and-hold sur la même période (après 0,70 % de coût hypothétique) : environ -49,0 %.

## Interprétation et limites

1. La réversion RSI sous EMA50 est la seule famille de ce premier écran qui mérite une investigation prioritaire. Ce n'est PAS une stratégie validée.
2. Les effectifs sont extrêmement faibles : 16 trades sur toute la période et 4 dans le holdout pour RSI < 30. Les métriques sont donc instables et peuvent être dominées par quelques rebonds exceptionnels.
3. Les résultats sont sensibles à la définition du seuil et à la structure de sortie ; les variantes ont été observées après un premier écran, donc le holdout n'est pas un test final parfaitement scellé.
4. Le marché a baissé d'environ 63 % entre la première et la dernière clôture calculée. La réversion peut capter des rebonds de survente sans démontrer un avantage répétable.
5. Le premier écran utilise des coûts hypothétiques, ne confirme pas les frais Kraken personnels et ne modélise pas encore tous les garde-fous de paper broker.
6. Aucune prétention de validation : le minimum de 100 trades OOS n'est pas atteint. Il faut davantage d'historique propre, des règles figées avant le test final, des coûts documentés et un moteur indépendant vérifié.

## Décision de recherche

- Déprioriser pour l'instant les deux variantes breakout, le pullback EMA20 et le momentum RSI > 60 dans leurs formes testées.
- Poursuivre la famille réversion, mais tester sa robustesse sur segments de marché différents, frais stressés, stops alternatifs et règles d'invalidation fixées à l'avance.
- Construire un holdout réellement scellé et augmenter l'échantillon via historique 1h paginé et propre, sans compter les sous-barres comme des observations indépendantes.
- Ne pas transférer cette piste vers le board TradingView ou le paper broker avant validation distincte et autorisation.


## Complément de contrôle — pagination et anomalie OHLCV

Pagination terminée pour les fenêtres intraday disponibles :
- 1h : 6 779 barres du 2026-01-22 14:00 UTC au 2026-11-09 01:00 UTC, réparties sur deux pages. 166 ruptures d'une heure ont été observées au total (101 dans la page ancienne, 65 dans la page récente).
- 15m : 5 529 barres du 2026-09-01 00:00 UTC au 2026-11-09 01:15 UTC, sur deux pages. 791 ruptures de 15 minutes observées (127 anciennes, 664 récentes).
- Le premier OHLCV 1h est anormal : 2026-01-22 14:00 UTC, open 0,004400, high 0,020000, low 0,003929, close 0,004049, volume 30 402 785 TEL. Ce high est très éloigné de toutes les autres valeurs du même historique (deuxième plus haut : 0,004875) et n'est pas reflété par l'agrégat 4h correspondant. Il doit être exclu ou mis en quarantaine, jamais utilisé pour les niveaux/ATR.
- Les ruptures intraday et cette anomalie empêchent de traiter les historiques 1h/15m comme un flux continu. Les backtests multi-timeframes restent bloqués jusqu'à segmentation, exclusion de l'anomalie et contrôle des timestamps.


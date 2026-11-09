# Exploration multi-combinaisons — 9 novembre 2026

Instrument : KRAKEN:TELUSD. Recherche exclusivement historique, aucune stratégie/board modifiée, aucun ordre paper ou réel placé.

## Données TradingView utilisées
- 4h : 1,743 barres du 2026-01-22 12:00 UTC au 2026-11-09 00:00 UTC ; une rupture de cadence de 8h. Première bougie anormale connue (high 0.020) quarantainée ; dernière bougie 4h en formation exclue.
- 1h : 5,000 barres du 2026-04-11 20:00 au 2026-11-09 01:00 UTC, 65 ruptures de cadence dans la page reçue. Pour le sweep segmenté, seuls 19 segments d'au moins 80 barres ont été conservés (3,550 barres) ; 1,450 barres des segments trop courts écartées, aucun remplissage/interpolation.
- 1D : seulement 292 barres du 2026-01-22 au 2026-11-09. 1W : 43 barres. Le feed consulté ne donne donc pas plusieurs années de données pour ce symbole.

## Méthodologie du sweep local exploratoire
Calcul indépendant exécuté sur les réponses OHLCV brutes TradingView via le MCP, sans toucher au moteur historique du dépôt. Indicateurs calculés à partir des clôtures : RSI14, EMA20/50/200, ATR14, Stochastique, CCI20, Bollinger 20/2, Donchian. Signal à la clôture, entrée à l'ouverture de la bougie suivante ; un seul trade à la fois ; stop/target intrabar avec priorité au stop si les deux sont touchés dans la même bougie ; sortie temporelle ; sortie à la clôture précédente en cas de trou de données. Coûts de round-trip testés à 0.70 % et 1.40 % en stress, hypothèses conservatrices de recherche et non frais personnels vérifiés.

Deux mesures ont été séparées :
1. Sweep brut initial de 1,200 variantes 4h (mean reversion RSI, breakout Donchian, momentum RSI/EMA, pullback RSI, stops ATR 1.5–2.5, cibles 1–3R, horizons 12/24). Les meilleurs chiffres en rendement de compte étaient des variantes à faible n et sans sizing conforme au risque ; ils ne sont pas utilisables pour conclure.
2. Sweep risque-contraint de 2,400 variantes 4h RSI : RSI seuil 20/25/30/35/40, condition sous seuil ou croisement, filtre none/sous EMA50/au-dessus EMA50/EMA20 au-dessus ou dessous EMA50, stop 1.5/2/2.5/3 ATR, cible 1.5/2/2.5/3R, durée 12/24/36 barres. Taille calculée pour risquer au plus 0.25 % de l'equity par trade, exposition plafonnée à 1x, coûts retranchés sur le notionnel. Cette simulation simplifiée ne remplace pas le moteur audité et ne modélise pas encore tous les garde-fous (notamment limite de perte journalière/cooldown exacts et slippage variable).
3. Sweep 1h exploratoire de 2,704 variantes (RSI, Stochastique, CCI, Bollinger reentry, momentum RSI avec filtres EMA, stops/cibles ATR et durées). Les segments courts et les trous de données réduisent fortement l'échantillon ; aucune variante n'a atteint 30 trades sur les segments conservés.
4. Sensibilité locale de 144 combinaisons autour du candidat RSI30, avec 96 variantes ayant au moins 15 trades ; 43 positives à 0.70 % de coût et 21 positives au stress 1.40 %. Cette dispersion, le nombre de variantes testées et les faibles n signalent un risque élevé de sélection opportuniste.

## Résultats — aucun candidat robuste
- Le meilleur résultat brut initial (RSI14<30, stop 2.5 ATR, cible 1R, horizon 24) affichait 20 trades et un rendement net/trade flatteur dans une simulation all-in ; ce sizing n'était pas conforme au risque 0.25 % et le R/R 1.0 ne respecte pas la politique paper minimale de 1.51. Il est rejeté comme candidat paper.
- En sizing au risque 0.25 %, une variante RSI<30 sous EMA50, stop 2.5 ATR, cible 1.5R, horizon 24 donne 17 trades, win rate 41.2 %, PF net 1.17 à coût 0.70 %, rendement composé +0.36 % environ ; ce résultat est faible et non robuste.
- Variante de tête de grille RSI<30, stop 1.5 ATR, cible 3R, horizon 12 : 27 trades ; PF 1.37 à coût 0.70 %, PF 1.09 à 1.40 %. Chronologie : early 10 trades PF 1.45 (0.70 %) ; validation 10 trades PF 1.81 ; holdout récent 6 trades PF 0.76 et perte composée -0.24 % (coût 0.70 %). Elle échoue donc au holdout.
- Autre variante RSI<30, stop 2.5 ATR, cible 3.5R, horizon 16 : 18 trades ; PF 2.06 à coût 0.70 %, PF 1.69 à 1.40 %, mais holdout 5 trades PF 0.17 à 0.70 % et perte composée -0.52 %. Elle échoue également.
- Variante RSI40 cross sous EMA20<EMA50, stop 1.5 ATR, cible 3R, horizon 36 : 36 trades ; PF global 1.33 à 0.70 %, 1.08 à 1.40 %. La validation intermédiaire (8 trades) est négative, et 36 trades restent très insuffisants.
- Transfert de la piste RSI<30 vers 1h : sur la page 5,000 barres avec ruptures, simulation conservatrice segmentée : 56 trades globaux ; PF 1.25 à 0.70 % mais 0.78 à 1.40 %. Sur le holdout récent, 18 trades : PF 1.12 à 0.70 % et 0.72 à 1.40 %. Pas de confirmation multi-timeframe.

## Verdict
Aucun système testé n'a démontré une rentabilité robuste. Les meilleurs scores apparaissent avec des échantillons faibles, sont sensibles aux frais et/ou échouent au holdout. Les variantes ne sont pas candidates à l'activation ni au paper trading. Le seuil R/R minimum de la politique paper n'a pas été assoupli. Pas de modification des règles/boards.

## Suite de recherche
1. Obtenir un historique 4h/1h plus long et continu (les données TradingView consultées commencent au 22 janvier 2026 pour 4h et 1h partiellement ; historique quotidien limité à 292 barres). Sans données supplémentaires, 100 trades OOS peuvent être inatteignables.
2. Auditer et réutiliser le moteur de backtest existant du dépôt, en particulier gaps, frais, slippage, stop/target intrabar, état continu, daily loss et cooldown ; exécuter ses tests.
3. Poursuivre les familles non RSI (Bollinger/Keltner, Donchian, faux breakouts, ATR compression/expansion, structure swing, volume relatif, confluence multi-timeframe) uniquement sur séries propres et règles pré-enregistrées.
4. Exiger une validation chronologique non retunée, sensibilité aux frais, baseline et minimum 100 trades OOS avant tout verdict robuste. Tant que les données ne le permettent pas, dire explicitement que la preuve manque.

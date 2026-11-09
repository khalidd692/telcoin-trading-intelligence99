# Rapport final — validation de « TEL Kraken – repli 4h dans tendance »

**Verdict : DONNÉES INSUFFISANTES** (règle figée : N_total < 30 ; ici N_total = 0).
Ce n'est ni une preuve de rentabilité, ni une preuve de non-rentabilité : la stratégie spécifiée n'a produit aucun trade sur ces données.

## Méthode
Moteur dédié (17 tests unitaires annoncés : ATR Wilder, absence de lookahead, collisions stop/cible, gaps, expiration, risque 0,25 %, une position, cooldown, coûts). Protocole figé avant exécution : IS 60 % / VAL 20 % / OOS 20 %. Exécution unique ; aucun paramètre ajusté.

## Résultats
- 53 signaux candidats (branche A : 42, B : 10, A+B : 1).
- 53/53 rejetés par RR brut minimum 1,51. RR brut maximal : 0,8011.
- Trades exécutés : IS 0 / VAL 0 / OOS 0, dans les trois scénarios de coûts (brut, central, prudent).
- Expectancy, profit factor, drawdown et rendement non calculables.

## Limites
- Un seul actif, un seul régime majoritairement baissier, environ 290 jours, timeframe 4h uniquement.
- Frais Kraken réels NON VÉRIFIÉS ; coûts central et prudent = hypothèses.
- Données TradingView 1h/15min et MCP TradingView non accessibles dans la session de préparation.
- Holdout non strictement vierge : replay diagnostique préliminaire sur l'ensemble, sans ajustement de règle.

## Reproduire
`python3 -m unittest tests.test_strategy_engine` puis `python3 scripts/strategy_backtest/run_validation.py`.

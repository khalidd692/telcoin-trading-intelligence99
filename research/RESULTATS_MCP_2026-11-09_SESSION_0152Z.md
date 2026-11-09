# Résultats MCP — session de reprise du 9 novembre 2026

Instrument : KRAKEN:TELUSD, spot long-only. Statut : recherche exploratoire ; aucune stratégie validée ; aucun ordre.

## État opérationnel
- Paper broker : equity 997.50 USD, cash 997.50 USD, P&L réalisé -2.50 USD, zéro position, zéro ordre en attente.
- Cotation TradingView : 0.0014912 USD, flux streaming, vers 01:52 UTC.
- Dernière bougie 4h clôturée observée : clôture 0.001500 à 2026-11-08 20:00 UTC. Bougie ouverte à 00:00 UTC du 9 novembre encore en formation, clôture provisoire 0.001477.
- Snapshot 4h : RSI 44.18, ADX 35.12, EMA20 0.00155392, EMA50 0.00151127 ; snapshot 1h : RSI 23.06, ADX 30.43, EMA20 0.00154456, EMA50 0.00156835. Les deux résumés techniques TradingView indiquent SELL.
- Refresh des boards refusé pour quota hebdomadaire épuisé ; reset annoncé le 13 novembre 2026 vers 14:52 UTC. Les deux lectures Smart View sont anciennes et ne sont pas des signaux actuels.

## État des stratégies existantes
- Radar 15m : 0 setup, 4 watch, 5 none sur 14 jours ; aucun plan scoré. La règle requiert CHoCH, MACD et volume relatif, mais le volume par barre est indisponible dans la lecture du board.
- Repli 4h : 0 setup, 10 watch ; aucun plan scoré. Dernier plan ancien : entrée 0.00151475, stop 0.00145996, cible 0.001578, R/R 1.15 ; déclencheur de reprise EMA20 non satisfait. Règles unsettled.

## Fréquences historiques automatiques MCP (pas des backtests nets)
Fenêtre : 1,000 barres 4h du 26 mai au 9 novembre 2026. Les tests mesurent des fréquences sur barres, sans simulation d'exécution, stop, taille, frais ni slippage.

| Test | Résultat | Baseline | Médiane forward | Lecture |
|---|---:|---:|---:|---|
| RSI oversold | 10/17 = 58.8 % (IC95 36.0–78.4) | 38.9 % | +1.20 % | faible échantillon, piste à étudier |
| RSI crosses above average | 36/82 = 43.9 % (IC95 33.7–54.7) | 38.9 % | -0.77 % | avantage non établi |
| Gap up fill | 16/19 = 84.2 % (IC95 62.4–94.5) | non fournie | -0.08 % | faible n, pas une stratégie directionnelle |
| Bollinger lower reentry | 30/30 = 100 % (IC95 88.6–100) | 100 % | +1.58 % | aucun pouvoir discriminant vs baseline |
| Gap down fill | 11/16 = 68.8 % (IC95 44.4–85.8) | non fournie | -0.78 % | stabilité faible ; seconde moitié 2/5 |

Rappel des tests 1h du 8 novembre : RSI oversold 9/19 (47.4 %) vs baseline 38.3 %, médiane -0.31 % ; RSI cross-up 30/78 (38.5 %) vs 38.3 %, médiane -0.85 % ; Bollinger reentry 35/35 avec baseline 100 %.

## Conclusion
Aucune stratégie n'est validée. Le test RSI oversold 4h est un test de fréquence de signal et ne reproduit pas la stratégie RSI<30 sous EMA50 du screen précédent. La réversion RSI reste exploratoire, n=17 et intervalle large. Les autres tests n'établissent pas d'avantage net. Les boards restent non actualisables jusqu'au reset du quota. Aucun board, aucune stratégie, aucun ordre et aucun fichier de main n'a été modifié.

## Suite
Après reset du quota : rafraîchir les deux boards sans toucher aux règles. Continuer l'exploration 4h sur barres clôturées, pré-enregistrer paramètres et coûts, puis auditer le moteur existant avant toute simulation nette. Exiger 100 trades OOS avant toute revendication de validation robuste.

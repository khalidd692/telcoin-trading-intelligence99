# Audit du moteur historique — 2026-11-09

## Périmètre et méthode

Audit statique en lecture seule de la branche `research/tel-discovery-unrestricted`. Fichiers examinés :
- `scripts/backtest/engine.py` — blob `ca46525302e67420ffb37f465f9cabb479d3c99d`
- `scripts/backtest/harness.py` — blob `9de77cba9bacc758d41044a1267c7deb13e0fe80`
- `scripts/backtest/history_store.py` — blob `aa030438831b800ebd5986304fda91c86f994eaf`
- `scripts/backtest/run_oos.py` — blob `d1948161a4d794b873c3607446ad4bea318e8abb`
- `scripts/backtest/protocol.py` — blob `932437a59ffb0232bd1fdf49314b1963fced2efe`
- tests `test_backtest_harness.py`, `test_oos_evaluation.py`, `test_reversal_engine.py`.

Aucun code, board, alerte, paper broker ou stratégie n'a été modifié. Aucun test n'a été exécuté dans cette session : le connecteur GitHub permet ici de lire/écrire le dépôt, pas d'exécuter le dépôt Windows local. Les constats ci-dessous sont donc un audit statique, pas un résultat d'exécution.

## Constats bloquants

### B1 — Mauvais marché pour la validation Kraken

`scripts/backtest/run_oos.py` fixe explicitement :
`VENUE, SYMBOL = "kucoin", store.KUCOIN_SYMBOL` (TEL-USDT KuCoin).

`scripts/backtest/check_causality.py` utilise également KuCoin/TEL-USDT. Les résultats OOS de ce moteur ne valident donc pas KRAKEN:TELUSD. Ils peuvent rester une recherche exploratoire inter-venue, mais ne doivent pas être utilisés comme preuve de fiabilité d'un signal sur le marché Kraken.

### B2 — Les trous de données ne sont pas segmentés dans le chemin d'évaluation

`history_store.coverage()` sait détecter les ruptures, mais `load_timeframe()` se contente de filtrer les bougies non clôturées et retourne la série entière. `Bundle` calcule ensuite EMA, RSI, ATR, DMI, MACD et quantiles sur cette série concaténée. `engine.evaluate_episode()`, `base_rate()`, `find_reference_reversals()` et les masques d'évaluation avancent par index (`i + h`).

Conséquence : une rupture temporelle peut être traitée comme si les bougies manquantes n'existaient pas. Les indicateurs peuvent traverser un trou et un horizon de 24 heures ou 72 heures peut représenter une durée réelle bien plus longue. Les résultats ne sont pas fiables sur des séries trouées tant que chaque segment continu n'est pas traité indépendamment et que les horizons ne traversent jamais une frontière de segment.

### B3 — Ce moteur n'est pas un simulateur de trades

`engine.py` évalue des épisodes de signaux du détecteur (mouvements futurs, faux positifs, détection de retournements, délai d'avance et test de nullité). Il ne simule pas un portefeuille d'ordres avec quantité, frais d'entrée/sortie, stop, target, fills, cash, positions simultanées ou drawdown de portefeuille.

Il ne peut donc pas, à lui seul, valider la rentabilité d'une stratégie de trading. Il mesure la qualité prédictive d'un détecteur selon un protocole donné.

## Couverture des tests : limite identifiée

- Les tests de causalité des indicateurs comparent des préfixes et des séries complètes sur des fixtures.
- Les tests d'archive exigent que la fixture soit déjà sans trous.
- Les tests OOS vérifient la séparation chronologique IS/OOS et les coûts du masque, mais ne vérifient pas la segmentation des trous dans les données d'entrée.
- Aucun test de réinitialisation de l'état d'un indicateur à une rupture réelle, ni d'interdiction d'un horizon traversant une rupture, n'a été identifié dans les fichiers examinés.
- Le test `check_causality.py` est lui aussi configuré sur KuCoin et ne remplace pas un test de segmentation des données.

## Conséquence pour le chantier TEL

1. Ne pas relancer ce moteur comme preuve de signal Kraken.
2. Conserver ses résultats comme historique exploratoire du détecteur sur KuCoin, avec cette limite explicitement attachée.
3. La validation prioritaire doit utiliser exclusivement les bougies KRAKEN:TELUSD déjà exposées par TradingView MCP, après exclusion de l'anomalie OHLCV, des bougies en formation et segmentation stricte des trous.
4. Séparer deux questions : (a) le détecteur prévient-il assez tôt les retournements ? (b) une règle d'entrée/sortie réellement exécutable produit-elle un résultat net positif ?
5. Ne pas réécrire l'orchestrateur Python. Le présent audit sert à empêcher l'utilisation abusive des anciens résultats et à orienter les demandes de recherche TradingView déjà en attente.

## Demandes TradingView existantes — ne pas dupliquer

Vérification live du 2026-11-09 : les cinq demandes ci-dessous sont toujours `queued` :
- `rq_3fbd24d7858c4e9e` — sweep/réintégration 15m et 1h.
- `rq_304062157ba54962` — cassure/retest 4h.
- `rq_81fc211a3a43405b` — variantes A/B/C du repli swing low 4h.
- `rq_4f665100b71f4f6a` — backtest complet de la règle repli swing low 4h.
- `rq_919a53432a114077` — audit de la règle et du dimensionnement paper du repli 4h.

Ne créer aucune demande en doublon. Lire les réponses dès qu'elles passent à `answered`.

## État de sécurité et continuité

- Paper account : equity enregistrée 997,50 USD ; aucune position ouverte ; aucun ordre paper en attente selon l'état trader lu dans cette session.
- Politique technique actuellement active : risque 0,25 %/trade, perte quotidienne 1 %, une position max, levier 1x, cooldown 240 min, R/R minimal 1,51, stop et cible obligatoires.
- L'utilisateur a précisé que 0,25 % n'est pas sa tolérance personnelle : il se déclare très tolérant au risque et patient, pouvant supporter une baisse importante. Ne pas présenter les paramètres paper ci-dessus comme ses préférences personnelles. Ne pas les assouplir sans choix explicite des valeurs ; préserver impérativement spot long-only et levier 1x.
- Aucun changement de politique, ordre, stratégie, board, alerte ou branche main effectué.

## Prochaine action unique

Suivre les cinq demandes existantes. En parallèle, faire vérifier la disponibilité d'une méthode de backtest historique TradingView réellement liée à KRAKEN:TELUSD ; ne pas réutiliser les métriques KuCoin comme substitut. La correction de segmentation du moteur n'est à entreprendre que si ce moteur est encore utile au projet, sur une branche de recherche et avec tests dédiés avant tout nouveau résultat.

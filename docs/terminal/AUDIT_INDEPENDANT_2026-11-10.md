# Audit indépendant TEL99 — 10 novembre 2026

## Périmètre et niveau de preuve

Revue **statique** du code accessible sur la branche `codex/tel99-quant-terminal` : `src/terminal/model.py`, `scripts/terminal/{collect,build,research}.py`, `scripts/strategy_backtest/engine.py`, `site/terminal/{index.html,app.js,core.js}`, `tests/test_terminal{,_model,_collect,_research}.py`, workflow et livraison. Le site privé répond 401 à un navigateur non authentifié. **Aucune exécution indépendante de la suite complète ou validation de navigateur authentifié n'a été effectuée pendant cet audit.** Les 455 tests Python (3 ignorés), 42 tests collecteur et 16 assertions JS sont des résultats *rapportés dans les artefacts d'Astra*, pas des résultats réexécutés ici.

## Constats vérifiés dans le code

- Collecte : six requêtes OHLC publiques Kraken (TEL 15m/1h/4h/1D, BTC et ETH 4h) via `scripts/terminal/collect.py` ; **aucun ordonnanceur automatique de collecte**.
- Construction : `scripts/terminal/build.py` écrit un snapshot JSON analytique et conserve séparément le corpus historique des expériences. La page charge `data.json` une fois à l'ouverture ; `setInterval(...,15000)` dans `app.js` ne fait que réévaluer les indicateurs de fraîcheur et l'horloge.
- Prix : bouton manuel `Actualiser le cours` appelle Kraken Ticker. Le correctif de cette branche limite la validité visuelle d'une cotation reçue à 120 secondes et vérifie son expiration lors du rafraîchissement de l'interface ; **ce n'est pas un polling automatique**.
- Marché : la qualité contrôle OHLC, fin de bougie, timestamps, doublons, inversions et trous ; les indicateurs redémarrent après les discontinuités. Les stratégies primaires ne sont pas modifiées.
- Backtests : les variantes expérimentales réutilisent le moteur existant, entrent à l'ouverture suivante et excluent les horizons traversant une frontière de fenêtre. Les coûts sont hypothétiques. Les fenêtres sont des échantillons déjà explorés ; aucune preuve de rentabilité robuste.
- Risque : calculateur spot théorique avec frais/slippage et plafond de 0,25 % ; pas de fonction d'envoi d'ordre dans les fichiers du terminal examinés.

## Points restant à traiter — ordre de priorité

**P1 — Actualisation analytique.** Le prix du ticker et le snapshot des indicateurs sont découplés. La page peut afficher une cotation récente tout en indiquant `DONNÉES INSUFFISANTES` pour le signal, ce qui est correct mais ne constitue pas une analyse live. Prévoir collecte incrémentale, génération atomique du snapshot, contrôle de quota et provenance ; ne pas rafraîchir les bougies toutes les minutes par simple appel navigateur non contrôlé.

**P1 — Preuves CI.** Vérifier le résultat du workflow `tel99-terminal.yml` sur le dernier commit. Le fait qu'un workflow soit défini ne prouve pas qu'il ait exécuté et réussi ; les chiffres de livraison sont historiques.

**P1 — Validation des résultats.** Vérifier indépendamment les résultats du backtest sur données sources et le calcul du coût d'exécution ; ne pas conclure à un edge à partir de 20 transactions exploratoires.

**P2 — Cotation Kraken (corrigé, tests CI à confirmer).** La lecture de la première entrée de `result` a été remplacée par une validation explicite de la paire TEL/USD et du cours dans `parseTelTicker()` ; quatre assertions ajoutées.

**P2 — Limites du risque.** L'admissibilité du simulateur exige RR **brut** >= 1,51 et récompense nette positive, mais n'exige pas RR net >= 1,51. C'est cohérent avec le libellé et la règle actuelle, mais il faut décider explicitement si le seuil devrait s'appliquer au net avant de changer la politique.

**P2 — Backtest.** Le drawdown est calculé sur capital réalisé, pas mark-to-market ; les fenêtres de recherche déjà explorées ne sont pas un holdout vierge ; frais et liquidité observés manquent.

**P3 — Couverture.** Pas d'alertes persistantes/dédupliquées, carnet de liquidité, journal de portefeuille ou intégration de paper broker ; non livrés et explicitement documentés.

## Actions effectuées

- Correctif du ticker périmé dans `site/terminal/core.js` et `site/terminal/app.js`, cinq nouvelles assertions JS dans `tests/test_terminal.js` ; commits sur la branche isolée.
- Validation explicite de la paire du ticker Kraken dans `core.js`/`app.js` et quatre assertions JS supplémentaires. Le script affiche maintenant 25 assertions prévues ; leur succès CI après modification reste à confirmer.
- Aucune fusion, aucun déploiement, aucun ordre, aucune modification des règles des stratégies.

## Verdict

**Premier incrément substantiel, pas terminal autonome temps réel ni stratégie validée.** L'architecture est traçable et les protections observées sont sensées. L'audit statique est terminé pour les fichiers ci-dessus ; l'audit d'exécution et de sécurité exhaustif reste non démontré. Les prochaines étapes doivent prioriser la vérification CI, la mise à jour analytique, puis un backtest prospectif indépendant.

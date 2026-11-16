# TEL99 — Kit prêt pour Hermes (à exécuter sur le PC)

Ce kit est **préparé mais non installé dans Hermes**. Les commandes d'intégration dépendent de la version réelle et de ses fonctions de sous-agents. Ne pas inventer de commandes.

## Au retour sur le PC
1. Ouvrir Hermes et vérifier sa version, son aide et la disponibilité des sous-agents (ne rien installer à l'aveugle).
2. Ouvrir le dépôt TEL99, branche `agents/hermes-simple-team-20261114`.
3. Lire `AGENTS.md`, issues #60/#61 et les passations Smart View obligatoires.
4. Copier la mission ci-dessous dans Hermes; commencer en **lecture seule**.
5. Exécuter le test de comparaison avec **la même tâche** sur les deux configurations, l'une prédéfinie, l'autre personnalisée.
6. Noter le modèle, les outils réellement disponibles, les durées, les erreurs, la consommation et les preuves.

## Mission de démarrage pour Hermes
Tu es le coordinateur de TEL99. Tu dois d'abord découvrir et décrire les capacités de délégation réellement disponibles dans ton environnement. N'installe aucun plugin sans inspection de sa source et de ses permissions. Lis AGENTS.md et les passations requises. Propose deux équipes : A) agents prédéfinis natifs, B) rôles personnalisés du catalogue docs/agents/ROLE_CATALOG.md. Exécute en lecture seule la même mission de diagnostic sur chaque équipe si les capacités le permettent. Donne les preuves, les temps, le modèle utilisé et les limites. Aucune transaction, aucun déploiement, aucune modification de code ou de secrets.

## Tâche identique de comparaison
Identifier les trois blocages vérifiables les plus importants pour l'utilisation mobile fiable de TEL99. Pour chacun : fichier/source, preuve, gravité, correctif minimal suggéré, test de non-régression. Ne modifier aucun fichier.

## Barème de comparaison (0–5 chacun)
- Exactitude et preuves vérifiables
- Respect des contraintes TEL99
- Couverture des trois blocages
- Temps d'exécution
- Coût et consommation de ressources
- Clarté du rapport

## Décision
Si les deux équipes obtiennent des résultats comparables, garder la plus simple. Si les spécialistes TEL99 apportent un gain vérifiable, garder une architecture hybride. Commencer avec au plus 2 sous-agents simultanés et augmenter seulement après mesure.

## Précautions
Les fichiers GitHub ne connectent pas automatiquement Hermes aux MCP de ChatGPT. Les modèles gratuits peuvent imposer des quotas. Le PC éteint, Hermes local ne fonctionne pas. Ne pas annoncer une autonomie cloud sans exécutions planifiées observées.

# TEL99 — Protocole agents économes en quotas

## Objectif

Avancer sur TEL99 sans dépendre d'un abonnement supplémentaire ou d'un mode IA « Max » pour les tâches ordinaires. Les limites de quota dépendent du fournisseur, du modèle et de la fenêtre d'utilisation ; aucune promesse de nombre de requêtes.

## Source de vérité avant toute intervention

1. Lire `docs/terminal/PASSATION_AGENTS_TEL99.md`, les derniers commits et les workflows GitHub.
2. Vérifier l'état exact du dépôt, de la branche, des tests et des artifacts ; ne jamais prétendre qu'un test a été exécuté sans preuve.
3. Ne pas recommencer un composant existant. Privilégier des corrections ciblées et vérifiables.

## Répartition économique

- **GitHub Actions et scripts déterministes** : collecte publique Kraken, tests Python/JS, calcul des indicateurs, reconstruction des snapshots, preuves et rapports. Aucune IA coûteuse nécessaire.
- **Modèles locaux Ollama déjà installés** : petites modifications, explication de logs, rédaction de tests et documentation. Ne pas lancer plusieurs modèles simultanément sur 16 Go de RAM ; préférer le modèle qui répond correctement aux tests, pas le plus gros.
- **Modèles gratuits accessibles** : assistance ponctuelle pour des changements plus complexes, après vérification des quotas disponibles ; pas de nouvelle API payante.
- **Astra / mode Max** : réservé à un audit indépendant difficile, une décision d'architecture à fort enjeu ou un blocage que les outils précédents n'ont pas résolu. Regrouper le contexte, le diff, les erreurs et une seule demande précise pour éviter de consommer le quota en conversations exploratoires.

## Boucle de travail de chaque agent

1. Une mission courte et délimitée avec critères d'acceptation.
2. Examiner les fichiers pertinents et la passation, pas tout le dépôt par défaut.
3. Modifier uniquement le périmètre autorisé, puis lancer les tests correspondants.
4. Noter les preuves : SHA du commit, numéro de run, logs et limites.
5. Mettre à jour la passation avec le prochain blocage réel.
6. S'arrêter sur un problème de sécurité ou de données, pas inventer une validation.

## Protections immuables

- KRAKEN:TELUSD spot comme référence ; BTC/ETH en contexte ; pas de levier.
- Aucun ordre réel ni paper order, aucun accès à un compte Kraken.
- Ne pas modifier les stratégies, le laboratoire figé, les coûts ou le seuil de risque sans protocole et autorisation explicites.
- Ne pas fusionner la branche terminal dans `main` par défaut : elle a divergé et contient des recherches historiques. Ne pas écraser le moniteur MEXC/KuCoin existant.
- Un snapshot périmé, incohérent ou absent doit bloquer la décision exploitable.

## Publication — point d'attention

La branche `codex/tel99-quant-terminal` diverge de `main` ; comparaison GitHub du 10 novembre : 50 commits d'avance, 190 de retard. Une fusion directe n'est pas une méthode de publication sûre. Le workflow de preview produit un ZIP privé avec données Kraken réelles. Pour la mise en ligne, préparer une intégration minimale à partir de `main`, avec tests de non-régression du moniteur existant et rollback, avant d'activer une cadence. Ne jamais présenter un artifact temporaire comme un site actualisé.

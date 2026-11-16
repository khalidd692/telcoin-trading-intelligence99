# TEL99 — Équipe multi-agents simple (Hermes)

Statut : **configuration de délégation proposée, non exécutée**. Ce fichier ne lance aucun agent et ne crée aucune planification cloud.

## Point de départ obligatoire
Lire `AGENTS.md`, les issues #60 et #61 et les passations Smart View avant toute modification. Ne pas changer l'architecture existante, les widgets, les données publiées ou les workflows sans nécessité démontrée.

## Orchestrateur : Hermes
- Reçoit une mission unique, la découpe en tâches indépendantes et attribue chaque tâche à un responsable.
- Demande un rapport court : constat, fichiers concernés, changement, tests, risques, preuve.
- N'autorise aucune fusion, aucun déploiement ni aucune modification sensible sans vérification et validation appropriée.
- N'annonce jamais un travail terminé sans résultats vérifiables.

## Quatre responsables logiques (rôles, pas processus déjà actifs)
1. **Développement** : corrections ciblées Python/JS, branches de travail séparées, aucun changement de design non demandé.
2. **Quant et données** : collecte publique Kraken, fraîcheur, indicateurs, journal prospectif, contrôle des fuites temporelles et des frais.
3. **Cloud et fiabilité** : audit GitHub Actions, branches, planifications, logs et publication réelle; preuves de fonctionnement PC éteint avant toute déclaration d'autonomie.
4. **Qualité et sécurité** : tests unitaires/intégration, comparaison avant/après, absence de régression, protection des secrets et des données.

## Protocole de mission
1. Hermes lit le dépôt et les consignes, puis définit des critères d'acceptation observables.
2. Les responsables analysent en parallèle en lecture seule.
3. Hermes séquence les modifications pour éviter les conflits de fichiers.
4. Chaque modification passe par une branche isolée, avec tests et rapport.
5. Le responsable qualité vérifie indépendamment; échec => pas de publication.
6. Hermes résume les preuves, limites et actions nécessitant l'accord du propriétaire.

## Garde-fous
- **Aucun ordre réel ni simulé**; aucun accès de trading en écriture.
- Aucune suppression, force-push, modification de Smart View ou refonte du terminal.
- Aucune stratégie déclarée rentable sans évaluation statistique sérieuse.
- Ne jamais confondre alerte précoce, confirmation de marché et achat vérifié côté risque.
- Ne pas lancer de sous-agents sans capacité d'exécution effectivement configurée; ne pas prétendre qu'ils tournent 24/7.
- Privilégier les modèles locaux/gratuits pour lecture, tri et tests simples; escalader seulement les tâches difficiles.

## Première mission recommandée (lecture seule)
« Inspecte l'état actuel de TEL99, identifie les trois blocages vérifiables les plus importants pour une utilisation mobile fiable, attribue-les aux quatre rôles, puis livre un plan de corrections minimales avec preuves et commandes de tests. Ne modifie rien et ne passe aucun ordre. »

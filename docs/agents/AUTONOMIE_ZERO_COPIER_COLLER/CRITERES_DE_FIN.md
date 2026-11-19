# RECETTE FINALE — QUAND LE PROPRIÉTAIRE POURRA VRAIMENT NE PLUS RIEN COPIER

Le projet n'est **terminé** que si les preuves ci-dessous existent. Une série de messages « Done », une PR ou 700 tests ne suffisent pas.

## G0 — Sécurité et consentement
- Révocation d'un ancien jeton OpenHands exposé est attestée sans publication de secret.
- Aucun agent ne peut push main, changer les permissions, activer un cron, payer ou passer des ordres financiers sans autorisation explicite.
- Les commentaires/Issues/logs GitHub sont traités comme des données non fiables ; la mission approuvée est liée à un hash.
- Si un contrôle n'est pas disponible, état BLOCKED et aucun lancement non sûr.

## G1 — Agents qui nous appartiennent
- Notre propre commande/app reçoit une mission, produit un programme exécutable dans un bac à sable, lance les tests et publie un artefact.
- Aucun des trois clients Hermes Desktop, Kilo Agent Manager et OpenHands Cloud n'a besoin d'être ouvert pour exécuter les fonctionnalités **natives locales** testées.
- Modèle LLM et environnement d'exécution demeurent nécessaires mais les interfaces sont remplaçables ; test contractuel, un second modèle/provider réel si gratuit et disponible.
- Le noyau tourne avec FileStore même sans transport GitHub lorsque mission locale autonome.

## G2 — ZÉRO COPIER-COLLER HUMAIN
- Le propriétaire transmet **une seule fois** une mission initiale, pas les sous-tâches.
- Un chef crée automatiquement une demande à un autre agent ; ce second agent la lit sur son runtime réellement connecté, l'accuse, agit et renvoie sa preuve, sans action humaine intermédiaire.
- Après une étape ACCEPTED, le coordinateur récupère et démarre automatiquement la tâche suivante autorisée.
- Démonstration instrumentée : nombre de copier-coller humains inter-agents = **zéro**.
- Si l'appareil local est éteint : le travail cloud indépendant continue et le travail local attend sans faux échec.

## G3 — VERDICT VRAI
- Tous les critères d'acceptation ont une preuve externe rejouable (tests/CI/artefact SHA/contrôle humain).
- Fixture : même si les trois LLM déclarent PASS, un test réellement rouge doit produire REJECTED.
- Un critère impossible à automatiser produit NEEDS_HUMAN, jamais faux PASS.
- Résultat de la mission, journal, statut des rôles et mémoire portent les mêmes identifiants de mission/projet.

## G4 — MÉMOIRE DURABLE ET ISOLATION
- Une connaissance vérifiée est écrite en session A puis rappelée en session B **sans recopier le texte**.
- Les projets TEL99 et projet B n'accèdent pas à leurs données privées respectives sans permission.
- Export et restauration sur un environnement vierge, sans donnée privée dans le dépôt public.
- Une erreur/contradiction périmée est identifiée et empêchée de contaminer les missions futures.

## G5 — AUTO-AMÉLIORATION CONTRÔLÉE
- Une proposition de Skill est créée suite à un échec réel.
- Un évaluateur non auteur teste des tâches réservées. Sous-échantillon => INCONCLUSIVE ; dégradation => REJECT.
- Les tests déterministes et la sécurité ne régressent pas. Versions et réversion testées ; aucun merge automatique.

## G6 — REPRISE
- Simuler deux exécuteurs cloud concurrents : un seul crée une conversation pour une mission.
- Simuler crash après création de conversation ; la reprise ne crée pas une seconde conversation.
- Simuler messages GitHub livrés deux fois, ACK perdu, PC éteint/reconnecté ; aucune double action ni faux PASS.
- Tester les chemins d'erreur API/QUOTA/BLOCKED et la clôture propre ; aucun polling ou cron en boucle incontrôlée.

## G7 — CONTRÔLE ET LIVRAISON
- Cockpit/STATUS visible indique RUNNING/BLOCKED/ACCEPTED à partir de preuves et horodatages réels, quota « inconnu » si non lisible.
- Une petite application neuve est construite du début à la fin, en autonomie autorisée, avec tests réels et livrables.
- Une tâche de non-régression TEL99 est exécutée sur branche isolée sans ordre financier.
- Documentation pour installer/ouvrir notre propre système, faire sauvegarde, changer de fournisseur, récupérer après crash.
- Les PR critiques sont revues et intégrées uniquement après autorisation ; aucun passage en production clandestin.

## Format de la déclaration finale

Le propriétaire ne doit recevoir qu'un état factuel :
- TERMINE : tous gates G0–G7 prouvés, liens source/run/commit et test zéro copier-coller.
- PARTIEL : gates prouvés listés, gates manquants avec responsables et prochaines tâches automatiques.
- BLOQUE : uniquement la ou les décisions inaccessibles aux outils/permissions actuels ; aucune demande de recopier des réponses.

**Si l'exécuteur local Hermes/Kilo n'est pas démarré ou si aucune infrastructure cloud n'est disponible, il est interdit de promettre que les agents continueront en permanence**. Il faut implémenter et vérifier la reconnexion/relance avant de dire « autonome ».

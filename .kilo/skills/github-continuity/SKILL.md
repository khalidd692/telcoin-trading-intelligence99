# Skill: github-continuity

**But :** Récupérer au début de chaque session les dernières tâches, PR, commits, responsabilités et preuves depuis GitHub, afin d'éviter les doublons et de repartir de l'état actuel du projet.

**Quand déclencher :**
- Au démarrage de toute nouvelle conversation ou session de travail.
- Avant de modifier un fichier, ouvrir une branche ou créer une PR.
- Lorsqu'on reprend une tâche après une interruption.

**Comment utiliser :**
1. Lire l'issue maître #94 et ses derniers commentaires (GitHub API ou webfetch).
2. Lire les SHAs de référence des PR en cours (#105, #107, #108, #110, #111, #115, #116).
3. Comparer avec les branches et commits locaux (`git branch -a`, `git log --oneline -10`, `git status --short`).
4. Identifier quels travaux sont déjà terminés (DONE), en cours (IN_PROGRESS) ou bloqués (BLOCKED).
5. Ne choisir qu'une tâche admissible non possédée par Codex/Hermes/OpenHands.
6. Afficher l'état `DONE / IN_PROGRESS / BLOCKED / NEXT` avant toute modification.

**Entrées :** URL de l'issue #94, liste des PR concernées, état local Git.
**Sorties :** Checkpoint lisible avec DONE/IN_PROGRESS/BLOCKED/NEXT, SHAs de référence, fichiers réservés.

**Permissions :** Lecture seule sur GitHub (webfetch, git log/show/status). Aucune modification.

**Exclusions :** Ne pas réexécuter une tâche déjà terminée. Ne pas recréer un fichier déjà présent dans une PR mergée.

**Version :** 1.0
**Retour arrière :** Non applicable (compétence de lecture et de planification).
**Conflits connus :** Ne pas entrer en conflit avec GPT/Codex G3 sur `scripts/agents/native/*`. Ne pas dupliquer PR #111 (`tests/test_agent_native_verdict_contract.py`).

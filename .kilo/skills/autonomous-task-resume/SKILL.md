---
name: autonomous-task-resume
description: Permet à un agent de retrouver automatiquement l'état d'une mission interrompue, d'identifier ce qui est déjà fait, et de reprendre au bon point sans duplicata.
---

# Skill: autonomous-task-resume

**But :** Permettre à un agent de retrouver automatiquement l'état d'une mission interrompue, d'identifier ce qui est déjà fait, et de reprendre au bon point sans duplicata.

---

## Quand déclencher

- Au démarrage de toute nouvelle session ou conversation de travail.
- Après une interruption (redémarrage, timeout, erreur bloquante).
- Avant de commencer une nouvelle tâche pour vérifier qu'elle n'est pas déjà réalisée.
- Lorsqu'un agent reçoit une mission exprimée en langage naturel.

---

## Comment utiliser

### 1. Récupérer le contexte de mission

**Sources obligatoires (ordre de priorité) :**
1. **GitHub Issue #94** + derniers commentaires (via `webfetch` ou GitHub API)
2. **TASKS.md** local (tableau TERMINÉ / EN COURS / BLOQUÉ / À FAIRE / ÉCARTÉ)
3. **État Git local** : `git status --short`, `git log --oneline -10`, `git branch -a`
4. **Branches distantes** : `git ls-remote --heads origin` pour voir les PR en cours
5. **Checkpoints mémoire** : fichiers `.kilo/agent-manager.json` (si Agent Manager utilisé), `results/`, `artifacts/`

### 2. Identifier la dernière mission et ses propriétaires

- Lire le dernier commentaire de l'issue #94 qui mentionne une attribution ou un état.
- Extraire : nom de la mission, agent responsable, branche de travail, fichiers concernés.
- Vérifier si la mission a un propriétaire explicite (Codex, Hermes, OpenHands, Kilo, etc.).

### 3. Détecter les missions terminées (anti-doublon)

**Critères de "TERMINÉ" (preuve requise) :**
- Tâche listée dans section **TERMINÉ** de TASKS.md avec colonne "Preuve" renseignée.
- PR mergée ou commit sur `main` avec message de fusion traçable.
- Artefacts dans `results/` ou `artifacts/` avec empreinte SHA-256 vérifiée.
- Tests passés (CI verte, `pytest`/`node tests` locaux OK).

**Action :** Refuser de réexécuter toute action dont la preuve existe déjà. Afficher `SKIP: déjà fait — <preuve>`.

### 4. Reprendre une mission interrompue

**Étapes :**
1. Identifier le dernier checkpoint connu (dernier commit de la branche de travail, dernier artefact écrit, dernière ligne de journal).
2. Comparer avec l'état attendu (TASKS.md, commentaires GitHub).
3. Déterminer l'étape suivante admissible (dépendances satisfaites, propriétaire disponible).
4. Reprendre **exactement** à cette étape, sans recommencer les précédentes.

### 5. Conserver la traçabilité

- Chaque décision de reprise/skip doit être journalisée dans un fichier de session (ex: `.kilo/sessions/<session-id>/resume-log.jsonl`).
- Format : `{ "timestamp": "...", "action": "resume|skip", "task": "TXX", "reason": "...", "evidence": "..." }`.

---

## Entrées

- URL GitHub Issue #94 (fourni par l'utilisateur ou découvert via `git remote get-url origin`).
- Fichier `TASKS.md` local.
- État Git local (`git status`, `git log`, `git branch`).
- Optionnel : `.kilo/agent-manager.json` pour les sessions Agent Manager.

## Sorties

- **Checkpoint de reprise** : résumé lisible avec :
  - Mission identifiée + propriétaire
  - État DONE / IN_PROGRESS / BLOCKED / NEXT pour chaque tâche liée
  - Prochaine action admissible avec dépendances
  - Fichiers réservés / propriétaires
  - SHAs de référence (dernier commit branche, dernier artefact)
- **Journal de traçabilité** : `.kilo/sessions/<id>/resume-log.jsonl`

---

## Permissions

- **Lecture seule** sur GitHub (webfetch, git log/show/status/ls-remote).
- **Lecture/écriture** locale sur `.kilo/sessions/<id>/` pour le journal de session.
- **Aucune modification** du code, des branches, des PR, des artefacts.

---

## Exclusions (ne pas déclencher)

- Ne pas réexécuter une tâche déjà dans TERMINÉ avec preuve.
- Ne pas recréer un fichier déjà présent dans une PR mergée ou sur `main`.
- Ne pas reprendre une mission dont le propriétaire est un autre agent actif (vérifier #94).
- Ne pas créer de nouveau système de stockage : réutiliser TASKS.md, Git, checkpoints existants.

---

## Tests de validation

### Test A — Continuité
- Nouvelle session → lit #94 + TASKS.md + git → identifie mission T42 (fusion PR #47) comme EN COURS.
- Affiche checkpoint avec prochaine action : "fusion PR #47 avec merge commit".
- Ne propose pas T36 (déjà décidé) ni T40 (déjà TERMINÉ).

### Test B — Anti-doublon
- Agent tente de lancer "créer dashboard" → détecte T37/T41/T52/T65 dans TERMINÉ avec preuves.
- Affiche `SKIP: T37 déjà fait — 8 assertions JS + e2e` et refuse.

### Test F — Reprise après interruption
- Session interrompue après T59 (cadence corrigée) avant T60.
- Nouvelle session → retrouve branché `feat/tel99-twelve-agents` à commit `ee77552`.
- Identifie T60 comme NEXT (dépendances T59 satisfaites).
- Reprend à T60 sans refaire T59.

---

## Version

1.0

## Retour arrière

Non applicable (compétence de lecture et de planification). En cas d'erreur de lecture, relancer avec sources fraîches.

## Conflits connus

- Ne pas entrer en conflit avec l'autre chef (G0–G7) sur les branches `feat/autonomous-supervisor-v1` ou `agents/hermes-simple-team-20261114`.
- Ne pas dupliquer le travail de `github-continuity` : ce skill **utilise** ses sorties, ne le remplace pas.
- Ne pas modifier `scripts/agents/native/*` (propriété Codex G3).
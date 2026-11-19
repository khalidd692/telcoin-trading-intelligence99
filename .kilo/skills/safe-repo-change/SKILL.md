---
name: safe-repo-change
description: Protège les branches, évite les doublons et préserve les fichiers des autres agents avant tout changement dans le dépôt.
---

# Skill: safe-repo-change

**But :** Protéger les branches, éviter les doublons, vérifier les modifications et préserver les fichiers appartenant à d'autres agents avant tout changement dans le dépôt.

**Quand déclencher :**
- Avant tout `git commit`, `git push`, `git checkout`, `git merge`.
- Avant toute création ou modification de fichier dans le dépôt.
- Avant toute ouverture de PR draft.

**Comment utiliser :**
1. Vérifier que la branche cible n'est pas `main` ni une branche appartenant à un autre agent (`auto/surveillance-telegram`, branches Codex #105/#107/#108/#110/#111).
2. Vérifier qu'aucun travail équivalent n'est déjà en cours (consulter #94 et les branches distantes).
3. Ne modifier que les fichiers explicitement autorisés pour cette mission.
4. Ne jamais toucher à `scripts/agents/native/*` (propriété de Codex G3 PR #105/#110).
5. Ne jamais toucher à `auto/surveillance-telegram` (autre session).
6. Travailler dans une branche Git isolée, jamais sur `main`.
7. Après modification, exécuter les tests et vérifier qu'il n'y a pas de régression.
8. Préparer une PR draft isolée, jamais de merge direct.

**Entrées :** Nom de branche, liste de fichiers à modifier, propriétaires de fichiers.
**Sorties :** Branche isolée, fichiers modifiés, résultat des tests, lien PR draft (si applicable).

**Permissions :** Git lecture/écriture sur branche isolée uniquement. Interdiction de merge sur `main`. Interdiction de toucher aux fichiers d'autres agents.

**Exclusions :** `main`, `auto/surveillance-telegram`, `scripts/agents/native/*`, fichiers revendiqués par un autre agent.

**Version :** 1.0
**Retour arrière :** `git checkout` sur la branche précédente, `git reset` non forcé, pas de force-push.
**Conflits connus :** Commit `0427c023` (doublon de PR #111) — préserver en local, ne pas merger. Commit `ee9f1b77` (fix Windows) — préserver séparément.

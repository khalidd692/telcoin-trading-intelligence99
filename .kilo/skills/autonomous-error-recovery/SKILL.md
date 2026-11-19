---
name: autonomous-error-recovery
description: Analyse, diagnostique et corrige les erreurs de manière vérifiable, sans boucles infinies, en préservant l'existant.
---

# Skill: autonomous-error-recovery

**But :** Analyser, diagnostiquer et corriger les erreurs de manière vérifiable, sans boucles infinies, en préservant l'existant.

---

## Quand déclencher

- Échec de test (pytest, node, script verify).
- Erreur d'exécution (exception, timeout, code de sortie non-zéro).
- Échec CI (GitHub Actions rouge).
- Erreur de validation (provenance, fraîcheur, schéma).
- Blocage détecté par `autonomous-work-cycle` (dépendance, autorisation, budget).

---

## Comment utiliser

### 1. Analyser l'erreur réelle

**Collecter (lecture seule) :**
- Sortie complète de l'erreur (stdout/stderr, traceback, logs CI).
- Commande qui a échoué + code de retour.
- Contexte : fichier modifié récemment, commit, branche.
- Environnement : Python/Node version, OS, dépendances.

**Ne pas deviner :** Lire les logs réels, pas les messages d'erreur tronqués.

### 2. Diagnostiquer la cause

**Classification :**
| Type | Indicateurs | Action |
|------|-------------|--------|
| **Panne temporaire** | Flaky test, timeout réseau, CI intermittente, "resource temporarily unavailable" | Attendre + relancer (max 2x), puis bloquer |
| **Erreur de code** | AssertionError, TypeError, SyntaxError, logique métier cassée | Corriger (étape 3) |
| **Erreur de configuration** | ModuleNotFound, path incorrect, variable d'env manquante | Corriger config/environment |
| **Erreur de données** | Schéma invalide, données manquantes, fraîcheur expirée | Corriger source ou gestion d'erreur |
| **Erreur d'autorisation** | Permission denied, 403, secret manquant | Bloquer + demander humain |
| **Régression** | Test qui passait, maintenant échoue après changement récent | `git bisect` ou revert ciblé |

### 3. Proposer une correction minimale

**Principes :**
- **Une seule chose à la fois** : un commit = une correction.
- **Minimal** : changer le moins de lignes possible pour fixer la cause racine.
- **Localisé** : ne toucher qu'au module concerné + ses tests.
- **Sans casser l'existant** : tous les tests précédents doivent passer.

**Format de proposition :**
```markdown
## Correction proposée pour <erreur>

**Cause racine :** <analyse en 1 phrase>
**Fichiers à modifier :** <liste exacte>
**Diff attendu :** <diff unifié minimal>
**Tests à relancer :** <liste explicite>
**Risque de régression :** LOW/MEDIUM/HIGH
```

### 4. Tester la correction

**Ordre :**
1. Appliquer le diff minimal.
2. Lancer le test qui échouait → doit passer.
3. Lancer la suite de tests du module → tous passent.
4. Lancer la suite complète (ou sous-ensemble pertinent) → pas de régression.
5. Si échec → revenir à l'étape 2 (max 3 itérations).

### 5. Éviter les boucles infinies

**Garde-fous :**
- Compteur `attempt_count` par erreur (max 3).
- Si même erreur après 3 corrections différentes → **BLOQUER** + publier blocage.
- Historique des tentatives : `.kilo/sessions/<id>/error-recovery-log.jsonl`.
- Ne pas réessayer la même correction (même diff) deux fois.

### 6. Préserver les fichiers et résultats précédents

- **Jamais** de `git reset --hard` sans checkpoint préalable.
- **Jamais** de suppression d'artefacts (`results/`, `artifacts/`) sans empreinte vérifiée.
- Travail sur branche isolée → facile à abandonner.
- Checkpoint avant chaque tentative de correction.

### 7. Publier un blocage si non admissible

**Conditions de blocage :**
- Erreur d'autorisation (secret, merge, déploiement).
- Même erreur après 3 corrections distinctes.
- Correction nécessiterait modification hors périmètre (fichiers d'autres agents, moteur G0–G7).
- Budget gratuit épuisé.

**Format blocage :**
```markdown
## BLOCAGE — <Tâche / Erreur>

**Erreur :** <description>
**Tentatives :** <N> corrections essayées
**Dernière correction :** <diff>
**Résultat :** <toujours même erreur / nouvelle erreur / hors périmètre>
**Action requise :** <humain / autre agent / budget / autorisation>
**Contexte préservé :** branche <nom>, commit <sha>, artefacts intacts
```

---

## Entrées

- Erreur brute (logs, traceback, sortie CI).
- Contexte : tâche en cours, fichiers modifiés, branche, commit.
- Historique de session (tentatives précédentes).

## Sorties

- **Correction appliquée** + tests verts → `RECOVERED`.
- **Blocage publié** → `BLOCKED` avec format ci-dessus.
- Journal de récupération : `.kilo/sessions/<id>/error-recovery-log.jsonl` :
  `{ "timestamp": "...", "error": "...", "diagnosis": "...", "attempt": N, "diff": "...", "test_result": "pass|fail", "status": "recovered|blocked|retry" }`.

---

## Permissions

- **Lecture** : logs, code, tests, Git history.
- **Écriture** : fichiers du module concerné (selon plan), branche isolée, journal de session.
- **Exécution** : tests, scripts de vérification.
- **Interdits** : merge, déploiement, secrets, fichiers d'autres agents, moteur G0–G7.

---

## Exclusions (ne pas faire)

- Ne pas "corriger" en commentant un test qui échoue.
- Ne pas masquer l'erreur par un try/except vide.
- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas modifier le bus G2/G6, politique G3, mémoire G4, routeur G5.
- Ne pas créer de nouveau système de stockage.
- Ne pas déclarer "corrigé" sans test de régression passé.

---

## Tests de validation

### Test E — Réparation
- Erreur reproductible : `test_alert_state.py::test_advance_fail_closed` échoue (assertion sur `exploitable`).
- Diagnostic : champ `exploitable_reason` manquant dans le snapshot.
- Correction minimale : ajouter champ dans `collector/tel_collector.py` (1 ligne).
- Tests : le test qui échouait passe + 260 tests suite complète passent.
- Journal : `error-recovery-log.jsonl` avec 1 tentative, status `recovered`.

### Test F — Reprise sans doublon/perte
- Interruption pendant correction (après diagnostic, avant application).
- Nouvelle session → `autonomous-task-resume` retrouve branche + checkpoint.
- Reprend à l'étape "appliquer correction" sans refaire le diagnostic.
- Checkpoint préservé, pas de double exécution.

### Test G — Sécurité
- Erreur 403 sur push → bloqué, pas de tentative de contournement.
- Erreur sur `scripts/agents/native/mission.py` → refus de modification, blocage publié.
- Tentative de `git push --force` → refusée par `safe-repo-change`.

---

## Version

1.0

## Retour arrière

- `git checkout` branche précédente (checkpoint avant correction).
- `git reset --hard` au commit pré-correction.
- Artefacts inchangés (sur branche isolée).
- Journal de session conservé pour audit.

## Conflits connus

- Ne pas interférer avec l'autre chef sur corrections G0–G7.
- Utilise `safe-repo-change` pour les guards Git.
- Délégation vers `tel99-verifier` pour vérification indépendante si dispo.
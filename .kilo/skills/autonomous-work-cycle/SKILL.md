---
name: autonomous-work-cycle
description: "Orchestre le cycle complet de travail autonome : mission, plan, choix du spécialiste, exécution, tests, vérification, checkpoint et prochaine tâche admissible."
---

# Skill: autonomous-work-cycle

**But :** Orchestrer le cycle complet de travail autonome : MISSION → PLAN → CHOIX DU SPÉCIALISTE → EXÉCUTION → TESTS → VÉRIFICATION → CHECKPOINT → PROCHAINE TÂCHE.

---

## Quand déclencher

- Après `autonomous-task-resume` qui a identifié la prochaine tâche admissible.
- Lorsqu'une mission en langage naturel est reçue et qu'aucun travail n'est en cours.
- À la fin de chaque tâche validée pour enchaîner automatiquement.

---

## Cycle attendu

```
MISSION (français naturel)
    ↓
PLAN (étapes vérifiables + responsables + dépendances)
    ↓
CHOIX DU SPÉCIALISTE (si délégation dispo & nécessaire)
    ↓
EXÉCUTION (dans branche isolée, fichiers autorisés uniquement)
    ↓
TESTS (unitaires, intégration, régression, spécifiques au domaine)
    ↓
VÉRIFICATION (indépendante, preuves d'exécution)
    ↓
CHECKPOINT (état DONE + artefacts + empreintes + journal)
    ↓
PROCHAINE TÂCHE (si dépendances OK + autorisation + budget)
```

---

## Comment utiliser

### 1. MISSION → PLAN

**Entrée :** Mission en français (ex: "Corrige la régression du collecteur MEXC").

**Sortie :** Plan structuré (JSON ou Markdown) avec :
- `steps[]` : chaque étape avec `id`, `description`, `owner` (agent/spécialiste), `depends_on[]`, `files[]`, `tests[]`, `evidence_required`.
- `budget_estimate` : temps/tokens estimé.
- `risk_level` : LOW/MEDIUM/HIGH (impact si échec).

**Règles :**
- Utiliser `autonomous-task-resume` pour connaître l'état actuel.
- Ne pas planifier une étape déjà DONE.
- Chaque étape doit avoir un test de validation explicite.
- Respecter les propriétaires de fichiers (voir `safe-repo-change`).

### 2. CHOIX DU SPÉCIALISTE

**Disponible si :** Kilo autorise la délégation (Agent Manager, subagents, ou agents natifs).

**Logique :**
```
SI tâche ∈ {python-test-triage, javascript-regression-triage, market-data-quality-readonly}
    → DÉLÉGUER au spécialiste correspondant (trace d'appel + résultat)
SINON SI tâche ∈ {code, refactor, fix} ET agent natif dispo
    → DÉLÉGUER à l'agent natif (scripts/agents/native/*)
SINON
    → EXÉCUTER localement (ce skill)
```

**Traçabilité :** Journaliser `delegation_log.jsonl` : `{ "task": "TXX", "specialist": "...", "input": "...", "output": "...", "status": "ok|failed", "duration_ms": ... }`.

**Éviter les agents inutiles :** Ne pas déléguer pour lecture simple, planification, ou tâches < 3 étapes.

### 3. EXÉCUTION

**Contraintes (via `safe-repo-change`) :**
- Branche Git isolée (jamais `main`).
- Fichiers explicitement listés dans le plan uniquement.
- Pas de touch aux fichiers d'autres agents (`scripts/agents/native/*`, `auto/surveillance-telegram`, branches réservées).
- Commits atomiques par étape.

### 4. TESTS

**Obligatoires par type de tâche :**
- Code Python : `pytest tests/` + tests dédiés (ex: `test_<module>.py`).
- Code JS/Node : `node tests/test_<module>.js`.
- Données/marché : scripts de vérification (`scripts/verify_*.py`).
- Dashboard : `node tests/test_dashboard.js` + `scripts/verify_t37_e2e.py`.
- CI : simulation runner local si possible.

**Critères de succès :** Tous les tests passés, pas de régression sur suite complète.

### 5. VÉRIFICATION

**Indépendante :** Différente de l'exécution.
- Rejouer les tests dans un environnement propre si possible.
- Vérifier les artefacts produits (empreintes SHA-256, tailles, formats).
- Confirmer que les preuves demandées dans le plan existent.

**Agent vérificateur :** Si `tel99-verifier` dispo → déléguer. Sinon → auto-vérification avec journal explicite.

### 6. CHECKPOINT

**Écrire :**
- Mettre à jour `TASKS.md` : déplacer tâche vers TERMINÉ avec preuve.
- Commit Git avec message standardisé : `feat/fix: TXX — <description> — Preuve: <ref>`.
- Artefacts dans `results/` ou `artifacts/` avec `sha256sum`.
- Journal de session : `.kilo/sessions/<id>/checkpoint-<TXX>.json`.

### 7. PROCHAINE TÂCHE

**Conditions d'enchaînement automatique :**
1. Tâche actuelle = DONE (tests + vérification OK).
2. Tâche suivante = dépendances satisfaites (toutes DONE).
3. Propriétaire de la tâche suivante = agent actuel OU délégation autorisée.
4. Budget restant > estimation (mode gratuit `kilo-auto/free`).
5. Aucune autorisation humaine manquante (pas de merge, pas de secret, pas de déploiement).

**Si une condition échoue :** S'arrêter proprement, afficher le blocage, journaliser, attendre instruction.

---

## Entrées

- Mission (français) ou prochaine tâche identifiée par `autonomous-task-resume`.
- Plan (généré à l'étape 1 ou fourni).
- Contexte GitHub/Git (de `autonomous-task-resume`).

## Sorties

- Plan d'exécution (JSON/Markdown).
- Journal de délégation (`delegation_log.jsonl`).
- Commits + artefacts + preuves.
- `TASKS.md` mis à jour.
- Checkpoint de session.
- Statut final : `CONTINUE` (prochaine tâche auto) | `WAIT_AUTH` (autorisation manquante) | `BLOCKED` (erreur/dépendance) | `DONE` (mission complète).

---

## Permissions

- **Git** : lecture/écriture sur branche isolée uniquement.
- **Fichiers** : lecture/écriture sur fichiers listés dans le plan uniquement.
- **Tests** : exécution `pytest`, `node`, scripts `verify_*`.
- **Délégation** : selon disponibilité Kilo (Agent Manager, subagents, agents natifs).
- **Interdits** : merge sur `main`, déploiement, secrets, fichiers d'autres agents.

---

## Exclusions (ne pas déclencher / ne pas faire)

- Ne pas recréer le superviseur G0–G7 (autre chef).
- Ne pas modifier le bus G2/G6, politique G3, mémoire G4, routeur G5.
- Ne pas créer de nouveaux agents (12 déjà définis).
- Ne pas forcer une délégation si Kilo ne l'autorise pas.
- Ne pas enchaîner si budget gratuit épuisé ou autorisation manquante.
- Ne pas déclarer "terminé" sans preuves d'exécution réelles.

---

## Tests de validation

### Test C — Planification
- Mission : "Ajoute un test de régression pour le collecteur KuCoin".
- Plan généré : 3 étapes (analyse → test → vérification) avec owner, depends_on, files, tests.
- Dépendances respectées (T53 collecteur vérifié = DONE).

### Test D — Délégation
- Tâche : "Diagnostique la régression Python sur test_alert_state.py".
- Spécialiste `python-test-triage` sollicité via délégation Kilo.
- Trace d'appel + résultat reçus, journalisés dans `delegation_log.jsonl`.

### Test G — Sécurité
- Tentative de modifier `scripts/agents/native/mission.py` → refusée (propriété Codex).
- Tentative de merge sur `main` → refusée.
- Tentative de délégation sans autorisation Kilo → fallback exécution locale.

### Test H — Activation
- Skill découvert dans `.kilo/skills/` par Kilo.
- Utilisé automatiquement quand une mission suit une reprise (`autonomous-task-resume`).

---

## Version

1.0

## Retour arrière

- `git checkout` branche précédente.
- `git reset --hard` au dernier checkpoint connu.
- Restaurer `TASKS.md` depuis `git show HEAD:TASKS.md`.
- Supprimer artefacts de session échouée.

## Conflits connus

- Ne pas interférer avec l'autre chef sur `feat/autonomous-supervisor-v1` (G0–G7).
- Utilise `github-continuity` et `safe-repo-change` existants, ne les modifie pas.
- Délégation vers `scripts/agents/native/*` seulement si Kilo l'autorise (PR #105/#110).
---
name: python-test-triage
description: Permet à un agent de comprendre une erreur Python, d'identifier la cause, de proposer un correctif minimal et de vérifier les tests, sans modifier des tests pour cacher une régression.
---

# Skill: python-test-triage

**But :** Permettre à un agent de comprendre une erreur Python (pytest, traceback, assertion), d'identifier la cause racine, de proposer un correctif minimal et de vérifier les tests, sans jamais modifier un test pour cacher une régression.

**Quand déclencher :**
- Échec d'un test Python (pytest, unittest) : assertion, TypeError, SyntaxError, ModuleNotFoundError, etc.
- Erreur d'exécution d'un script Python (exception, code de sortie non-zéro).
- Demande explicite de diagnostiquer une régression Python.

**Quand NE PAS déclencher :**
- Erreur JavaScript/Node (→ `javascript-regression-triage`).
- Erreur de données de marché (→ `market-data-quality-readonly`).
- Échec d'autorisation, de merge, de déploiement (→ bloquer, demander humain).

**Comment utiliser :**

### 1. Analyser l'erreur réelle (lecture seule)

Collecter :
- La sortie complète de l'erreur (stdout/stderr, traceback, logs pytest).
- La commande qui a échoué + son code de retour.
- Le fichier et la ligne pointés par le traceback.
- L'environnement : version Python, OS, dépendances installées.

Ne jamais deviner : lire les logs réels, pas les messages d'erreur tronqués.

### 2. Classer la cause

| Type | Indicateurs | Action |
|------|-------------|--------|
| Erreur de syntaxe | `SyntaxError`, `IndentationError` | Corriger la syntaxe |
| Erreur de type | `TypeError`, `AttributeError` | Vérifier les types/attributs |
| Erreur d'import | `ModuleNotFoundError`, `ImportError` | Corriger l'import ou l'environnement |
| Assertion échouée | `AssertionError` | Vérifier la logique métier attendue |
| Erreur de donnée | Valeur inattendue, champ manquant | Corriger la source ou la gestion d'erreur |

### 3. Proposer une correction minimale

Principes :
- **Une seule chose à la fois** : un commit = une correction.
- **Minimal** : changer le moins de lignes possible pour fixer la cause racine.
- **Localisé** : ne toucher qu'au module concerné + ses tests.
- **Sans casser l'existant** : tous les tests précédents doivent passer.
- **Ne jamais modifier un test pour le faire passer** : si un test échoue, c'est le code qui est en cause, pas l'attente.

Format de proposition :
```markdown
## Correction proposée pour <erreur>

**Cause racine :** <analyse en 1 phrase>
**Fichiers à modifier :** <liste exacte>
**Diff attendu :** <diff unifié minimal>
**Tests à relancer :** <liste explicite>
**Risque de régression :** LOW/MEDIUM/HIGH
```

### 4. Tester la correction

Ordre :
1. Appliquer le diff minimal.
2. Lancer le test qui échouait → doit passer.
3. Lancer la suite de tests du module → tous passent.
4. Lancer la suite complète (ou sous-ensemble pertinent) → pas de régression.
5. Si échec → revenir à l'étape 2 (max 3 itérations).

### 5. Éviter les boucles infinies

Garde-fous :
- Compteur `attempt_count` par erreur (max 3).
- Si même erreur après 3 corrections différentes → **BLOQUER** + publier blocage.
- Historique des tentatives : `.kilo/sessions/<id>/python-test-triage-log.jsonl`.
- Ne pas réessayer la même correction (même diff) deux fois.

---

## Entrées

- Erreur brute (logs, traceback, sortie pytest).
- Contexte : tâche en cours, fichiers modifiés, branche, commit.
- Historique de session (tentatives précédentes).

## Sorties

- **Correction appliquée** + tests verts → `RECOVERED`.
- **Blocage publié** → `BLOCKED` avec cause et tentatives.
- Journal : `.kilo/sessions/<id>/python-test-triage-log.jsonl` :
  `{ "timestamp": "...", "error": "...", "diagnosis": "...", "attempt": N, "diff": "...", "test_result": "pass|fail", "status": "recovered|blocked|retry" }`.

## Permissions

- **Lecture** : logs, code, tests, Git history.
- **Écriture** : fichiers du module concerné (selon plan), branche isolée, journal de session.
- **Exécution** : `pytest`, `python -m unittest`.
- **Interdits** : modifier un test pour le faire passer, merge, déploiement, secrets, fichiers d'autres agents.

## Exclusions (ne pas faire)

- Ne pas commenter un test qui échoue.
- Ne pas masquer l'erreur par un try/except vide.
- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas déclarer "corrigé" sans test de régression passé.

## Tests de validation

### Test positif — Réparation d'une erreur Python
- Erreur reproductible : `TypeError` sur un argument manquant dans `collector/tel_collector.py`.
- Diagnostic : paramètre `market` omis à l'appel.
- Correction minimale : ajouter l'argument (1 ligne).
- Tests : le test qui échouait passe + suite complète sans régression.
- Journal : 1 tentative, status `recovered`.

### Test négatif — Pas de modification de test pour cacher
- Tentative de modifier `assert x == 1` en `assert True` dans un test.
- Le Skill doit refuser et signaler `BLOCKED` : modification de test interdite.

### Test de reprise — Interruption puis reprise
- Interruption après diagnostic, avant application de la correction.
- Nouvelle session : reprend à "appliquer correction" sans refaire le diagnostic.
- Checkpoint préservé, pas de double exécution.

## Version

1.0

## Retour arrière

- `git checkout` branche précédente (checkpoint avant correction).
- `git reset --hard` au commit pré-correction.
- Artefacts inchangés (sur branche isolée).
- Journal de session conservé pour audit.

## Conflits connus

- Ne pas interférer avec les corrections de l'autre chef (G0–G7).
- Utilise `safe-repo-change` pour les guards Git.
- Ne pas modifier `scripts/agents/native/*` (propriété Codex G3).

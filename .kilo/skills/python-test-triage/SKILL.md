---
name: python-test-triage
description: "Diagnostiquer et trier les échecs de tests Python (pytest) : identifier la cause racine, proposer une correction minimale, et valider sans régression."
---

# Skill: python-test-triage

**But :** Diagnostiquer et trier les échecs de tests Python (pytest) : identifier la cause racine, proposer une correction minimale, et valider sans régression.

---

## Quand déclencher

- Échec de `pytest` (un ou plusieurs tests).
- Échec de `pytest tests/test_<module>.py` sur un module spécifique.
- Régression détectée : test qui passait, maintenant échoue après changement.
- Demande explicite : "diagnostique ce test qui échoue".

---

## Comment utiliser

### 1. Collecter l'échec (lecture seule)

```bash
pytest tests/ -v --tb=long 2>&1 | head -200
pytest tests/test_<module>.py -v --tb=long 2>&1
```

**Extraire :**
- Nom du test échoué (`test_<name>`).
- Type d'erreur : `AssertionError`, `TypeError`, `AttributeError`, `ModuleNotFoundError`, `TimeoutError`, etc.
- Traceback complet (dernier appel utilisateur → code test → code source).
- Fixtures/mocks impliqués.

### 2. Classifier l'échec

| Catégorie | Signes | Exemples |
|-----------|--------|----------|
| **Assertion métier** | `AssertionError` sur valeur attendue vs réelle | `assert result.exploitable == False` |
| **Régression code** | Test OK avant commit X, KO après | `git bisect` ou `git log --oneline -20` |
| **Dépendance manquante** | `ModuleNotFoundError`, `ImportError` | `pytest` absent, `src.` path incorrect |
| **Données/environnement** | `FileNotFoundError`, timeout, DNS, API | MEXC DNS, fixture corrompue |
| **Flaky** | Échoue 1/5 fois, non déterministe | Timing, ordre de tests, état partagé |
| **Test lui-même bogué** | Logique de test incorrecte, mock cassé | Mock ne correspond plus à l'API |

### 3. Diagnostic ciblé

**Pour AssertionError :**
- Lire le code source testé (`src/<module>.py`).
- Lire le test (`tests/test_<module>.py`).
- Comparer : quelle condition métier a changé ?
- Vérifier si le test ou le code est "la vérité" (consulter TASKS.md, docs, historique).

**Pour ModuleNotFound/ImportError :**
- Vérifier `PYTHONPATH` / `sys.path` dans `pytest.ini` ou `conftest.py`.
- Vérifier structure `src/` vs `tests/` (imports relatifs vs absolus).
- Windows : encoding, chemins, subprocess.

**Pour Régression :**
- `git log --oneline -20 -- tests/test_<module>.py src/<module>.py`
- Identifier le commit introducteur.
- `git show <commit> --stat` pour voir les fichiers touchés.

### 4. Proposer correction minimale

**Format :**
```markdown
## Diagnostic python-test-triage

**Test :** `tests/test_<module>.py::test_<name>`
**Erreur :** <type + message>
**Cause racine :** <1 phrase>
**Fichier(s) à corriger :** <liste>
**Diff minimal :** ```diff ... ```
**Tests de validation :** `pytest tests/test_<module>.py::test_<name> -v` + `pytest tests/ -x --tb=short`
**Risque régression :** LOW/MEDIUM/HIGH
```

### 5. Valider la correction

1. Appliquer le diff.
2. Relancer le test ciblé → PASS.
3. Relancer le module → TOUS PASS.
4. Relancer suite complète (ou `pytest tests/ -x`) → PAS DE RÉGRESSION.
5. Si échec → itérer (max 3 fois, voir `autonomous-error-recovery`).

---

## Entrées

- Nom du test ou module échoué (ex: `test_alert_state.py::test_advance_fail_closed`).
- Sortie brute `pytest` (fournie par l'appelant ou collectée).
- Contexte Git (branche, derniers commits).

## Sorties

- **Rapport de diagnostic** (format ci-dessus).
- **Diff minimal** applicable.
- **Résultat validation** : PASS/FAIL + logs.
- **Journal** : `.kilo/sessions/<id>/python-test-triage-log.jsonl`.

---

## Permissions

- **Lecture** : tout le code (`src/`, `tests/`), Git history, logs CI.
- **Écriture** : **uniquement** fichiers listés dans "Fichier(s) à corriger" (module source + son test).
- **Exécution** : `pytest`, `python -m pytest`, scripts de vérification.
- **Interdits** : modifier d'autres modules, tests non liés, `scripts/agents/native/*`, config CI, déploiement.

---

## Exclusions (ne pas déclencher)

- Tests JavaScript/Node (`node tests/...`) → `javascript-regression-triage`.
- Collecte données marché → `market-data-quality-readonly`.
- Échec CI non-python (workflow YAML, déploiement, etc.).
- Tests qui passent (pas de triage nécessaire).

---

## Tests de validation

### Test positif — Assertion métier
- `test_alert_state.py::test_advance_fail_closed` échoue : `exploitable_reason` manquant.
- Diagnostic : collecteur n'écrit pas le champ → correction 1 ligne dans `collector/tel_collector.py`.
- Validation : test ciblé PASS + 260 tests suite PASS.

### Test positif — ImportError Windows
- `ModuleNotFoundError: No module named 'src.agent_analysis'`.
- Diagnostic : `sys.path` manque racine projet dans `conftest.py` ou `pytest.ini`.
- Correction : ajouter `sys.path.insert(0, root)` dans `conftest.py`.
- Validation : suite complète PASS.

### Test négatif — Ne pas déclencher
- `node tests/test_dashboard.js` échoue → hors périmètre.
- Workflow GitHub Actions `.github/workflows/monitor.yml` rouge → hors périmètre (sauf si étape `pytest`).
- Test `test_alert_state.py` passe → pas de triage.

### Test reprise
- Interruption après diagnostic, avant correction.
- Nouvelle session → retrouve diagnostic dans journal → applique correction → valide.

---

## Version

1.0

## Retour arrière

- `git checkout` branche isolée avant correction.
- `git reset --hard` commit pré-correction.
- Tests non modifiés (sauf si le test lui-même était bogué — alors correction test + code).

## Conflits connus

- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas toucher aux tests d'autres skills (`javascript-regression-triage`, `market-data-quality-readonly`).
- Utilise `autonomous-error-recovery` pour la boucle de correction/validation.
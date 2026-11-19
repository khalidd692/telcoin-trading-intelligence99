---
name: javascript-regression-triage
description: "Diagnostiquer et trier les régressions JavaScript/Node : tests qui échouent, erreurs runtime, casses de build, incompatibilités navigateur/CI."
---

# Skill: javascript-regression-triage

**But :** Diagnostiquer et trier les régressions JavaScript/Node : tests qui échouent, erreurs runtime, casses de build, incompatibilités navigateur/CI.

---

## Quand déclencher

- Échec de `node tests/test_<module>.js` ou `npm test`.
- Erreur JavaScript dans le dashboard (`site/index.html`, `site/realtime.js`).
- Build échoué (si build step existe : `npm run build`, `vite build`, etc.).
- Régression détectée : test/dashboard qui fonctionnait, cassé après changement.
- Demande explicite : "diagnostique ce test JS qui échoue".

---

## Comment utiliser

### 1. Collecter l'échec (lecture seule)

```bash
node tests/test_<module>.js 2>&1
node tests/test_dashboard.js 2>&1
node tests/test_realtime.js 2>&1
# Si package.json existe :
npm test 2>&1
```

**Extraire :**
- Fichier et ligne de l'erreur (stack trace).
- Type : `AssertionError`, `ReferenceError`, `TypeError`, `SyntaxError`, `Error: timeout`, etc.
- Module concerné : `site/index.html` (inline JS), `site/realtime.js`, `tests/test_*.js`.
- Contexte : dernier commit touchant les fichiers JS.

### 2. Classifier l'échec

| Catégorie | Signes | Exemples |
|-----------|--------|----------|
| **Assertion test** | `assert.strictEqual` / `console.assert` échoue | Badge vert affiché alors qu'il ne devrait pas |
| **Régression code** | Test OK avant commit X, KO après | `git log --oneline -20 -- site/ tests/` |
| **Runtime/DOM** | `ReferenceError`, `TypeError: Cannot read property` | `element.querySelector` null, variable non définie |
| **Environnement** | `module not found`, `fetch` échoue, `WebSocket` | CI sans navigateur, `jsdom` manquant |
| **Flaky** | Échoue intermittemment (timing, async) | `setTimeout`, `fetch` mock, ordre tests |
| **Test bogué** | Mock ne correspond plus, assertion obsolète | API changée, test non mis à jour |

### 3. Diagnostic ciblé

**Pour AssertionError (tests) :**
- Lire `tests/test_<module>.js` → comprendre l'assertion.
- Lire le code source concerné (`site/realtime.js`, `site/index.html` script).
- Vérifier : le code a-t-il changé ? Le test est-il obsolète ?
- Exécuter en mode debug : `node --inspect-brk tests/test_<module>.js`.

**Pour Runtime/DOM :**
- Identifier l'élément/la variable `undefined`/`null`.
- Vérifier l'ordre d'exécution (DOMReady, event listeners).
- Vérifier les sélecteurs CSS (`querySelector`, `getElementById`).
- Dashboard : vérifier `site/index.html` structure HTML vs JS.

**Pour Régression :**
- `git log --oneline -20 -- site/ tests/`
- `git show <commit> -- site/realtime.js tests/test_dashboard.js`
- Identifier le changement cassant.

### 4. Proposer correction minimale

**Format :**
```markdown
## Diagnostic javascript-regression-triage

**Test/Erreur :** `tests/test_dashboard.js` / `site/realtime.js:42`
**Type :** <AssertionError / TypeError / ReferenceError / ...>
**Message :** <message exact>
**Cause racine :** <1 phrase>
**Fichier(s) à corriger :** <liste : site/realtime.js, tests/test_dashboard.js, site/index.html>
**Diff minimal :** ```diff ... ```
**Tests de validation :** `node tests/test_dashboard.js` + `node tests/test_realtime.js` + `node tests/`
**Risque régression :** LOW/MEDIUM/HIGH
```

### 5. Valider la correction

1. Appliquer le diff.
2. Relancer le test ciblé → PASS.
3. Relancer tous les tests JS (`node tests/`) → TOUS PASS.
4. Vérifier manuellement si dashboard (ouvrir `site/index.html` si possible).
5. Si échec → itérer (max 3 fois, voir `autonomous-error-recovery`).

---

## Entrées

- Nom du test ou fichier JS en erreur (ex: `tests/test_dashboard.js`, `site/realtime.js`).
- Sortie brute `node tests/...` (fournie ou collectée).
- Contexte Git (branche, derniers commits touchant `site/` ou `tests/*.js`).

## Sorties

- **Rapport de diagnostic** (format ci-dessus).
- **Diff minimal** applicable.
- **Résultat validation** : PASS/FAIL + logs.
- **Journal** : `.kilo/sessions/<id>/javascript-regression-triage-log.jsonl`.

---

## Permissions

- **Lecture** : `site/`, `tests/*.js`, `package.json` (si existe), Git history.
- **Écriture** : **uniquement** fichiers listés dans "Fichier(s) à corriger" (source JS + son test).
- **Exécution** : `node tests/...`, `npm test` (si dispo).
- **Interdits** : modifier fichiers Python, config CI, déploiement, `scripts/agents/native/*`.

---

## Exclusions (ne pas déclencher)

- Tests Python (`pytest`) → `python-test-triage`.
- Collecte données marché → `market-data-quality-readonly`.
- Échec CI non-JS (workflow YAML, étapes Python, déploiement).
- Tests qui passent.

---

## Tests de validation

### Test positif — Assertion dashboard (T37/T65)
- `node tests/test_dashboard.js` échoue : badge vert affiché pour `exploitable=false`.
- Diagnostic : `site/realtime.js` ne vérifie pas `snapshot.verified` avant badge vert.
- Correction : ajouter garde `if (!snapshot.verified) return` avant setAttribute.
- Validation : `node tests/test_dashboard.js` PASS (8 assertions) + `scripts/verify_t37_e2e.py` PASS.

### Test positif — ReferenceError realtime.js
- `ReferenceError: updateRegimeBadge is not defined` dans `site/realtime.js`.
- Diagnostic : fonction renommée `renderRegimeBadge` mais appel non mis à jour.
- Correction : renommer l'appel ou la fonction (1 ligne).
- Validation : `node tests/test_realtime.js` PASS + pas de regression `test_dashboard.js`.

### Test négatif — Ne pas déclencher
- `pytest tests/test_alert_state.py` échoue → hors périmètre.
- Workflow `.github/workflows/monitor.yml` étape `python` échoue → hors périmètre.
- `node tests/test_dashboard.js` PASS → pas de triage.

### Test reprise
- Interruption après diagnostic, avant correction.
- Nouvelle session → retrouve diagnostic dans journal → applique correction → valide.

---

## Version

1.0

## Retour arrière

- `git checkout` branche isolée avant correction.
- `git reset --hard` commit pré-correction.
- Tests non modifiés (sauf si test bogué — correction test + code).

## Conflits connus

- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas toucher aux tests Python (`python-test-triage`).
- Utilise `autonomous-error-recovery` pour la boucle de correction/validation.
- Dashboard `site/index.html` contient JS inline — modifications coordonnées avec `site/realtime.js`.
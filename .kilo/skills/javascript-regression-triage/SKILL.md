---
name: javascript-regression-triage
description: Permet à un agent d'identifier les problèmes JavaScript/Node, de comparer l'avant et l'après et de produire un rapport reproductible, sans modifier le terminal existant.
---

# Skill: javascript-regression-triage

**But :** Permettre à un agent d'identifier les problèmes JavaScript/Node (erreur d'exécution, test qui échoue, régression), de comparer l'état avant et après un changement, et de produire un rapport reproductible, sans modifier le terminal existant.

**Quand déclencher :**
- Échec d'un test JavaScript/Node (node, Jest, etc.).
- Erreur d'exécution d'un script Node (exception, code de sortie non-zéro).
- Régression suspectée sur le dashboard ou un module JS.

**Quand NE PAS déclencher :**
- Erreur Python (→ `python-test-triage`).
- Erreur de données de marché (→ `market-data-quality-readonly`).
- Modification du terminal TEL99 sans mission produit autorisée (→ bloquer).

**Comment utiliser :**

### 1. Reproduire le problème (lecture seule)

Exécuter la commande qui échoue et capturer :
- La sortie complète (stdout/stderr).
- Le code de retour.
- Le fichier et la ligne pointés par l'erreur.
- La version de Node et des dépendances.

### 2. Comparer avant / après

Utiliser Git pour identifier le changement récent :
- `git log --oneline -5` sur le fichier concerné.
- `git diff <sha_avant> <sha_après> -- <fichier>` pour voir le diff exact.
- Identifier ce qui a changé entre la version qui passait et celle qui échoue.

### 3. Produire un rapport reproductible

Format :
```markdown
## Rapport de régression JS — <fichier>

**Erreur :** <description>
**Commande qui échoue :** <commande>
**Code de retour :** <N>
**Fichier concerné :** <chemin>
**Diff avant/après :** <diff unifié minimal>
**Cause racine :** <analyse en 1 phrase>
**Correction proposée :** <diff minimal>
**Tests à relancer :** <liste explicite>
**Risque de régression :** LOW/MEDIUM/HIGH
```

### 4. Vérifier sans modifier le terminal

- Ne jamais modifier `site/index.html`, `site/realtime.js`, ni tout fichier du terminal TEL99 sans mission produit autorisée.
- Travailler sur une copie temporaire ou une branche isolée.
- Relancer les tests JS sur la version corrigée pour confirmer la réparation.

---

## Entrées

- Erreur brute (logs, traceback, sortie node).
- Contexte : fichier concerné, branche, commit avant/après.
- Historique Git (git log, git diff).

## Sorties

- **Rapport de régression** (Markdown) avec diff avant/après et cause racine.
- **Correction proposée** (diff minimal) ou **blocage** si hors périmètre.
- Tests JS relancés et verts → `RECOVERED`.

## Permissions

- **Lecture** : code JS, tests, logs, Git history.
- **Exécution** : `node`, scripts de test JS.
- **Interdits** : modifier le terminal TEL99 sans autorisation, merge, déploiement, secrets, fichiers d'autres agents.

## Exclusions (ne pas faire)

- Ne pas modifier `site/index.html`, `site/realtime.js` sans mission produit autorisée.
- Ne pas créer de nouveau système de build ou de bundler.
- Ne pas modifier `scripts/agents/native/*` (Codex G3).
- Ne pas déclarer "corrigé" sans test JS repassé vert.

## Tests de validation

### Test positif — Régression détectée et corrigée
- Un test JS qui passait échoue après un changement sur `site/realtime.js`.
- Diff avant/après identifie la suppression d'une gestion d'erreur.
- Correction minimale rétablit la gestion d'erreur.
- Le test JS repasse vert.

### Test négatif — Terminal protégé
- Tentative de modifier `site/index.html` sans mission produit.
- Le Skill doit refuser et signaler `BLOCKED` : terminal protégé.

### Test de reproduction — Rapport reproductible
- Le rapport contient le diff exact avant/après.
- Un tiers peut appliquer le diff et obtenir le même résultat.

## Version

1.0

## Retour arrière

- `git checkout` sur la version précédente du fichier JS.
- Artefacts de test temporaires supprimés.
- Journal de session conservé pour audit.

## Conflits connus

- Ne pas modifier le terminal TEL99 sans mission produit.
- Ne pas interférer avec les corrections de l'autre chef (G0–G7).
- Ne pas modifier `scripts/agents/native/*` (Codex G3).

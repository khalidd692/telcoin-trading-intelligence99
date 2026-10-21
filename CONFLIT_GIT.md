# DIAGNOSTIC DU CONFLIT GIT — `wip/p0-provenance`

**Date** : 21 octobre 2026 · **Statut** : documenté, **aucune opération Git mutante n'a été exécutée**
(aucun commit, push, reset, merge, rebase, checkout, stash, cherry-pick).

---

## 1. ÉTAT EXACT

```
branche courante : wip/p0-provenance
commit local     : 1b4fdd1 "P0 provenance fix and audit bundle"
remote           : origin/wip/p0-provenance  →  6 commits EN TÊTE
                  (0 commit local non poussé → fast-forward possible, PAS de divergence)
branche main     : 154303e, derrière origin/main de 10 commits
                  (relevé du 21/10 après l'opération 1 : les 10 commits sont des
                   publications automatiques « Refresh published TEL/USDT market report »,
                   aucun ne touche au code du détecteur)
```

Les 6 commits distants **ne touchent aucun code de détecteur** :

| Commit | Nature | Fichiers |
|---|---|---|
| `70522eb` | docs(audit) | `audit-p0/FINAL-STATUS.md` (nouveau) |
| `b6e4e6e` | ci : isoler le monitor | `.github/workflows/monitor.yml` (**−2 lignes**), `.github/workflows/p0-validation.yml` (**nouveau, 40 lignes**) |
| `ba4523a` | ci : validation P0 sur PR | `.github/workflows/p0-validation.yml` |
| `28d96b3` | docs(audit) | `audit-p0/P0-VALIDATION-CHANGES.md` (nouveau) |
| `31723a9` | docs | `docs/ANALYSE_TECHNIQUE_TEL_CHECKLIST.md` (nouveau) |
| `ee77552` | docs | (checklist) |

---

## 2. LE CONFLIT RÉEL — SÉMANTIQUE, PAS TEXTUEL

C'est le point important : **`git merge-tree` ne signale aucun conflit textuel** (`merged`, sans marqueurs). Un `git merge` automatique produirait donc un dépôt **silencieusement incorrect**.

### 2.1 Les deux stratégies concurrentes pour la validation des PR

| | **BASE = HEAD local** | **ORIGIN (6 commits)** | **WORKTREE (modifications non commitées d'un autre agent)** |
|---|---|---|---|
| `monitor.yml` — déclencheur `pull_request` | **présent** | **retiré** | **réintroduit** |
| `monitor.yml` — job `pr-validation` inline | absent | absent | **présent** (+21 lignes) |
| `monitor.yml` — garde `if:` sur `monitor-and-deploy` | absent | absent | **présent** (`github.event_name != 'pull_request'`) |
| `p0-validation.yml` (workflow séparé) | absent | **présent** (40 lignes) | absent |

**Les deux camps ont résolu le même problème différemment** :
- `origin` a **isolé** la validation PR dans un **workflow séparé** (`p0-validation.yml`) et a **retiré** le déclencheur `pull_request` de `monitor.yml` (commit `b6e4e6e` : *« ci: isolate operational monitor from pull request validation »*).
- Le worktree local a **réintégré** le déclencheur `pull_request` et **inline** un job `pr-validation` dans `monitor.yml`.

### 2.2 Conséquence d'une fusion automatique

Si le fast-forward est appliqué puis que le worktree est conservé tel quel :

1. `monitor.yml` conserve le déclencheur `pull_request` **et** le job `pr-validation` inline ;
2. `p0-validation.yml` existe **aussi** ;
3. → **la validation des tests s'exécute deux fois sur chaque PR** ;
4. → et `monitor-and-deploy` se redéclenche intégralement sur chaque PR (déploiement de la page), ce qu'`origin` voulait explicitement éviter via l'isolation.

**Aucune erreur ne serait visible** : les deux workflows sont valides, les tests passent dans les deux cas. Le doublon serait une consommation de minutes de CI sans signal.

---

## 2.5. ACTIVITÉ CONCURRENTE OBSERVÉE (le plus grave)

**Un autre agent travaille actuellement dans le dépôt**, pendant même l'exécution de cette phase.

| Horodatage | Observation |
|---|---|
| 01:15:35 | Sauvegarde du worktree — `src/agent_analysis.py` SHA-256 `e577550f…` |
| 01:17:47 | **`src/agent_analysis.py` modifié** (+82/−10 lignes) — SHA-256 `7df5e5af…` |
| 01:11 → 01:35 | Apparition de 4 fichiers non suivis : `_probe2.py`, `_probe_bear.py`, `_probe_d1_d8_d9.py`, `_probe_reg.py` |
| 01:33 / 01:37 | Exécution de mon backtest (avant / après ajout de l'empreinte) |

Contenu de la modification : réécriture de `has_rsi_divergence()` / `has_bearish_divergence()` (nouveaux extraits `_extreme_with_rsi()`, `_divergence_windows()`), corrigeant une **fuite temporelle** (index RSI négatif lisant la fenêtre récente quand l'historique est trop court) et le traitement des prix égaux.

**Conséquences :**

1. **La Phase B est déjà en cours ailleurs.** Les corrections de `src/agent_analysis.py` que j'aurais à proposer entrent en concurrence directe avec un travail actif. → **Ne pas modifier `src/agent_analysis.py` sans coordination préalable.**
2. **Tout résultat de backtest doit être épinglé à une version.** Le harnais inscrit désormais l'empreinte SHA-256 du détecteur dans `backtest_results_v2.json` (`detector.sha256`). Si l'empreinte change, les chiffres sont caducs → rejouer.
3. **Les fichiers `_probe*.py` sont des restes de débogage** : ne pas les commiter, ne pas les supprimer (ils appartiennent à l'autre agent).

---

## 3. AUDIT COMPARÉ DES WORKFLOWS (lecture seule, aucun changement)

### 3.1 Les trois versions de `monitor.yml`

| Élément | BASE = HEAD local | ORIGIN (6 commits) | WORKTREE (non commité) |
|---|---|---|---|
| Déclencheur `push: [main]` | ✅ | ✅ | ✅ |
| Déclencheur `pull_request: [main]` | ✅ | **âŒ retiré** | ✅ réintroduit |
| Déclencheur `schedule: */15` | ✅ | ✅ | ✅ |
| Déclencheur `workflow_dispatch` | ✅ | ✅ | ✅ |
| `permissions` au niveau workflow | `contents: write`, `pages: write`, `id-token: write` | idem | idem |
| Job `monitor-and-deploy` | présent, **sans garde** | présent, sans garde | **gardé par `if: github.event_name != 'pull_request'`** |
| Job `pr-validation` inline | âŒ | âŒ | **✅ (21 lignes)** |
| `environment` du job deploy | `${{ PR && 'test' \|\| 'github-pages' }}` | idem | idem |
| `concurrency` | `cancel-in-progress: false`, par ref | idem | idem |

**Point clé, vérifié step par step** : dans les trois versions, **tous** les steps à effet de bord portent déjà la garde
`if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'` :
collecte du rapport, collecte du snapshot détaillé, génération de l'analyse, validation de provenance, **commit des rapports publiés sur `main`**, configuration Pages, upload de l'artefact, **déploiement du site**, et marquage d'échec.
→ **Sur une PR, aucune collecte, aucun commit, aucun déploiement n'a lieu, quelle que soit la version.** La divergence ne porte donc **pas** sur le chemin de déploiement.

Le seul step sans garde est `Add report reference to summary` (`if: always()`), qui écrit dans le résumé de job — sans effet externe.

### 3.2 `p0-validation.yml` (nouveau sur ORIGIN) vs job `pr-validation` inline (WORKTREE)

| Élément | `p0-validation.yml` (ORIGIN) | job `pr-validation` inline (WORKTREE) |
|---|---|---|
| `permissions` | **`contents: read`** (niveau workflow) | **`contents: read` (niveau job)** — le niveau job prime sur le workflow |
| Node.js | `actions/setup-node@v4`, `node-version: 20` (**épinglé**) | **absent** → version par défaut du runner |
| Déclencheurs | `pull_request: [main]` **+ `push: [wip/p0-provenance]`** | `pull_request: [main]` **uniquement** |
| `concurrency` | par PR, `cancel-in-progress: true` | par ref, `cancel-in-progress: false` |
| Commandes de test | `unittest tests` · `unittest collector` · `test_dashboard.js` · `test_realtime.js` | **identiques** |

### 3.3 Ce que chaque version fait réellement sur une PR

| | BASE | ORIGIN | WORKTREE |
|---|---|---|---|
| Tests exécutés | 4 (dans le gros job de déploiement) | 4 (workflow isolé) | 4 (job dédié) |
| Job de déploiement démarré | **oui** (avec `environment: test`) | **non** | **non** (garde de job) |
| Jeton de la PR | `contents/pages/id-token: write` | **`contents: read`** | **`contents: write`, `pages: write`, `id-token: write`** |
| CI sur un push vers `wip/p0-provenance` | **aucune** | **oui** | **aucune** |

### 3.4 Trois arguments techniques en faveur du scénario A

1. ~~Permissions.~~ **CORRECTION (21/10, inspection directe du fichier) :** le job inline du worktree déclare **déjà** `permissions: contents: read` **au niveau du job** (mtime du fichier : 20/10 00:48). Le niveau job primant sur le niveau workflow dans GitHub Actions, **ce job s'exécute déjà en lecture seule** : l'argument d'élévation de privilèges que contenait la version 1 de ce document **était faux**, il est retiré. Les deux options sont désormais **équivalentes sur ce point** ; l'écart résiduel porte sur l'épinglage de Node, le déclenchement sur push WIP, la concurrence par PR et l'isolation du job.
2. ** Reproductibilité de la chaîne d'outils.** Origin épingle Node 20 ; le job inline utilise la version par défaut du runner (non garantie dans le temps).
3. **Couverture de la branche de travail.** `p0-validation.yml` se déclenche aussi sur `push: [wip/p0-provenance]` → **la CI valide la branche sur laquelle travaille ce projet**. La variante inline ne valide rien sur un push WIP : aucun contrôle automatique sur les commits d'audit.

### 3.5 Coût du scénario A
Le job `pr-validation` inline est **fonctionnellement redondant** avec `p0-validation.yml` (4 commandes identiques). L'abandonner ne perd **aucune** validation ; il ne perd que le Node épinglé et le déclenchement sur push WIP — que le workflow d'origin fournit déjà, en mieux.

### 3.6 Recommandation

> **Scénario A — adopter la stratégie d'`origin` (recommandation maintenue, motifs révisés).**
> Le job inline du worktree n'est **pas** moins sûr sur les permissions (il a été corrigé le 20/10 : `contents: read` au niveau du job — l'argument de l'élévation de privilèges était faux et a été retiré). Les écarts résiduels réels sont : **Node non épinglé** (reproductibilité), **absence de déclencheur `push: [wip/p0-provenance]`** (la CI ne valide pas la branche de travail), **concurrence au niveau du workflow** (les exécutions ne s'annulent pas entre elles) et **absence d'isolation** (le workflow de déploiement démarre sur une PR, même si ses étapes sont sautées). Le fast-forward apporte `p0-validation.yml` ; il suffit de **ne pas conserver** les 21 lignes locales de `monitor.yml`.
>
> **Si l'équipe préfère garder un seul fichier**, l'inverse est faisable (supprimer `p0-validation.yml` et conserver le job inline), à condition d'y ajouter `permissions: contents: read` au niveau du job, `actions/setup-node@v4` avec `node-version: 20`, et un déclencheur `push: [wip/p0-provenance]`.
>
> **Dans les deux cas, une étape est non négociable** : commiter ou sauvegarder les 568 lignes locales de `src/agent_analysis.py` (le détecteur n'existe pas sur GitHub) **avant** toute opération.

---

## 4. AUTRES POINTS DE TENSION (hors Git)

| Point | Constat | Risque |
|---|---|---|
| `src/agent_analysis.py` | +568 lignes **non commitées** : tout le détecteur (`detect_early_reversal` et 497 lignes de contexte) **n'existe pas sur GitHub** | Une fusion brutale ou un `checkout` de `main` ferait **disparaître le détecteur** |
| `tests/test_agent_analysis.py` | +694 lignes non commitées | Idem |
| `site/index.html` | +1 627 lignes ; `tests/test_dashboard.js` **lit et regex-analyse le fichier** | Toute retouche de l'un casse le test de l'autre |
| `site/realtime.js` | +744 lignes ; `tests/test_realtime.js` l'`require()` | Idem |
| `.github/workflows/monitor.yml` | modifié **des deux côtés** | Conflit de fusion au moment du fast-forward |
| `AUDIT_PASSATION_TEL.md` | en-tête pointant vers `al-mizan-v3-main` (projet interdit) ; décrit `agent_analysis.py` comme « 258 lignes » alors qu'il en compte **899** | Document obsolète : ne pas le prendre comme référence |
| `docs/ANALYSE_TECHNIQUE_TEL_CHECKLIST.md` | présent sur `origin`, **absent du worktree** | Sera ajouté par le fast-forward — à relire, pas à écraser |
| `test_write.txt`, `test_write2.txt`, `audit-p0.zip`, `__pycache__/` | non suivis, sans valeur | Ne pas committer |

---

## 5. SAUVEGARDE EFFECTUÉE

```
C:\Users\sabri\AppData\Local\Temp\opencode\backup-20261021-011535\
├── worktree\          copie intégrale hors .git et __pycache__
├── worktree.patch     git diff (les 6 fichiers modifiés)
├── git-status.txt     état porcelain + branche
├── git-log.txt        20 derniers commits
├── git-branches.txt   branches + suivi remote
├── diff-vs-origin.txt diffstat vs origin/wip/p0-provenance
└── repo.bundle        bundle Git complet (reconstructible hors-ligne)
```

---

## 6. SCÉNARIOS RECOMMANDÉS (aucun exécuté — à valider)

### Scénario A — adopter la stratégie d'`origin` (recommandé)
1. Sauvegarder le travail local (fait).
2. `git stash` **ou** commit local des modifications de `agent_analysis.py` / `tests/test_agent_analysis.py` **avant** toute opération, pour ne jamais perdre le détecteur.
3. `git merge --ff-only origin/wip/p0-provenance` → monitor.yml sans `pull_request`, `p0-validation.yml` créé.
4. **Abandonner** les modifications locales de `monitor.yml` (job `pr-validation` inline + déclencheur `pull_request`), qui font doublon avec `p0-validation.yml`.
5. Conserver et commiter séparément `src/agent_analysis.py` + `tests/test_agent_analysis.py`.

*Avantage* : une seule stratégie CI, celle déjà validée en CI distante.
*Coût* : le job `pr-validation` inline local est abandonné (il est de toute façon redondant).

### Scénario B — garder la stratégie locale
1. Sauvegarder puis commiter le travail local.
2. Fast-forward.
3. Supprimer `p0-validation.yml` (garder le job inline).

*Coût* : contraire à l'intention explicite du commit `b6e4e6e` ; à réserver si le job inline a une raison d'exister que le workflow séparé n'a pas.

### Dans les deux cas — **non négociable**
- Le détecteur (568 lignes non commitées) doit être **commité ou sauvegardé** avant toute opération sur `monitor.yml` ou avant un changement de branche.
- `site/index.html` et `site/realtime.js` ne doivent pas être touchés pendant une opération de réconciliation.
- Après réconciliation, relancer la suite complète : `pytest`, `unittest discover -s tests`, `unittest discover -s collector`, `node tests/test_dashboard.js`, `node tests/test_realtime.js`.

---

## 7. ÉTAT À LA FIN DE CETTE PHASE

| Élément | État |
|---|---|
| Opérations Git mutantes | **aucune** |
| Branche | inchangée (`wip/p0-provenance`, 6 commits derrière `origin`, 0 devant) |
| `src/agent_analysis.py` | **non modifié par ce travail** — les lignes ajoutées depuis le début de phase proviennent de l'autre agent (durcissement des fonctions de divergence) |
| `site/index.html`, `site/realtime.js` | **inchangés** |
| `.github/workflows/monitor.yml` | **inchangé** (les 21 lignes locales sont intactes) |

**Fichiers créés par ce travail** :

| Fichier | Rôle |
|---|---|
| `scripts/backtest/__init__.py`, `history_store.py`, `fetch_history.py`, `harness.py`, `engine.py`, `run_backtest.py`, `make_journal.py`, `summarize_results.py` | harnais complet (stdlib uniquement) |
| `tests/test_backtest_harness.py` | 22 tests de régression (R1 a R11) |
| `tests/fixtures/tel_history_sample.json` | fixture CI sans reseau (124 Ko) |
| `BACKTEST_HISTORIQUE_TEL.md` | rapport (version 2, resultats P1) |
| `JOURNAL_APPRENTISSAGE.md` / `JOURNAL_APPRENTISSAGE_P1.md` | journal d'apprentissage (P0 / P1) |
| `CONFLIT_GIT.md` | ce document |
| `backtest_results_v2.json` / `_v2_summary.json` | resultats P0 (complet + resume) |
| `backtest_results_p1.json` / `_p1.json.gz` / `_p1_summary.json` | resultats P1 (complet + compresse + resume) |
| `backtest_results_p1_cline.json` | rejeu sur le detecteur modifie par l'autre agent |

**Artefacts hors depot** : cache d'historique `%LOCALAPPDATA%\telcoin\history` (6 fichiers, 0,99 Mo) ; sauvegarde du cache P0 `%TEMP%\opencode\cache-backup-p1` ; sauvegarde integrale du worktree `%TEMP%\opencode\backup-20261021-011535`.

**Aucun fichier existant n'a ete supprime ni modifie hors des nouveaux fichiers listes ci-dessus.**

---

## 8. PLAN DE RÉCONCILIATION T40 (préparé le 21/10, **non exécuté**)

### 8.1 Constats de l'inspection directe (21/10)

| Élément | Constat réel |
|---|---|
| Commits locaux non poussés | **0** → le fast-forward est possible, sans divergence |
| Commits distants non intégrés | **6** (tous docs/CI, **aucun code de détecteur**) |
| Fichiers modifiés **des deux côtés** | **1 seul** : `.github/workflows/monitor.yml` → **c'est le seul point de conflit réel** |
| Conflits textuels (`git merge-tree`) | **0** → le risque est **sémantique**, pas bloquant |
| Fichiers non suivis qu'un FF écraserait | **AUCUNE** (les 4 fichiers ajoutés par origin n'existent pas localement) |
| `detect_early_reversal` dans `main` / `origin` / `HEAD` | **NON** (333 lignes en HEAD et origin, 296 en main) → **le détecteur n'existe sur aucun dépôt distant** |

### 8.2 Plan minimal (scénario A révisé)

1. **Sauvegarde** du worktree (déjà faite : `backup-mission-20261021-022330`, 77 fichiers + bundle) + sauvegarde des 21 lignes locales de `monitor.yml` dans un fichier dédié avant toute résolution.
2. **Commiter le travail local** (détecteur, tests, harnais, documentation). **Non négociable** : sans cela, la validation CI s'exécuterait sur un code *sans* détecteur, et le `checkout` de `main` ferait disparaître 1 000 lignes de moteur.
3. **Fast-forward** : `git merge --ff-only origin/wip/p0-provenance` → apporte `p0-validation.yml`, `docs/ANALYSE_TECHNIQUE_TEL_CHECKLIST.md`, `audit-p0/FINAL-STATUS.md`, `audit-p0/P0-VALIDATION-CHANGES.md` ; retire le déclencheur `pull_request` de `monitor.yml`.
4. **Résolution du seul conflit** : aligner `monitor.yml` sur la version d'`origin` → le job `pr-validation` inline et le déclencheur `pull_request` disparaissent ; la validation PR est assurée par `p0-validation.yml` (mêmes 4 commandes, `contents: read`, Node 20 épinglé, + push WIP).
5. **Contrôles** : suite complète, `scripts/verify_project.py`, `scripts/verify_t37_e2e.py`, validité YAML des workflows, relecture de `docs/ANALYSE_TECHNIQUE_TEL_CHECKLIST.md` (ajouté par origin, à ne pas écraser).

### 8.3 Risques résiduels

| Risque | Gravité | Parade |
|---|---|---|
| Perte du travail local non commité | **critique** | étapes 1 et 2 **avant** toute autre opération ; sauvegarde vérifiée |
| Dépôt silencieusement incohérent (double validation CI) | élevée | l'étape 4 est explicite et vérifiable par relecture du fichier |
| Perte du job inline si `p0-validation.yml` ne couvrait pas un besoin | faible | les 4 commandes sont **identiques** ; `contents: read` est déjà couvert |
| `main` est 10 commits derrière `origin/main` | moyenne | traitement séparé, hors périmètre de cette réconciliation (les 10 commits sont des publications automatiques, sans code) |

---

## 9. RÉCONCILIATION EXÉCUTÉE — opération 1 (21/10, autorisée explicitement)

> Cette section est un **journal factuel**. Elle décrit ce qui a été exécuté, avec ses preuves.
> Les opérations 2 à 5 (commit, push, fusion dans `main`, publication) **n'ont pas été exécutées**
> et restent soumises à autorisation distincte.

### 9.1 Commandes mutantes réellement exécutées (deux, et deux seulement)

| # | Commande | Code | Résultat |
|---|---|---|---|
| 1 | `git checkout origin/wip/p0-provenance -- .github/workflows/monitor.yml` | 0 | le fichier local est remplacé par la version distante vérifiée (SHA disque `8197bb20bd25…`) |
| 2 | `git merge --ff-only origin/wip/p0-provenance` | 0 | `Updating 1b4fdd1..ee77552` / `Fast-forward` |

Toutes les autres commandes ont été **en lecture seule** (`status`, `diff`, `rev-parse`, `cat-file`,
`log`, `reflog`, `fsck`, `bundle verify`, `add --dry-run`) ou des **tests**.

### 9.2 Preuves de résultat

| Contrôle | Valeur |
|---|---|
| HEAD | `1b4fdd1ef1a9…` → **`ee77552bc74d60c901dda9c2c379740f59367a60`** |
| Branche vs `origin/wip/p0-provenance` | **0 ahead / 0 behind** |
| Commits de fusion créés | **0** (parent unique `31723a9`) |
| Blob `HEAD:monitor.yml` vs blob `origin` | **identique octet pour octet** (`5537a110fc6e…`) |
| Fichiers modifiés | 7 → **6** (`monitor.yml` redevenu propre) |
| Fichiers non suivis (`-uall`) | **77** — aucun perdu, aucune fuite hors liste blanche |
| Moteur `src/agent_analysis.py` | **`ca7f46ee2b7e1a06` — intact** |
| Artefacts `site/*.json` | **identiques**, mtime inchangé (19/10 21:23) — aucune régénération |
| Manifeste de sauvegarde | 109 fichiers, **0 divergence** (la seule différence est `monitor.yml`, voulue) |
| Suite de tests | 182 passés / 3 skipped / 13 subtests · `verify_project` 36/36 · `verify_t37_e2e` 20/20 · `validate_correction` **reproduction exacte à 0,00029 pt** |

### 9.3 Ce que l'opération 1 a permis d'établir (au-delà du fast-forward)

* **La version locale de `monitor.yml` est intégralement redondante.** Comparaison programmatique :
  mêmes 4 commandes (même ordre), mêmes permissions `contents: read`, même runner, même Python 3.12.
  Le job `monitor-and-deploy` porte une garde **au niveau du job** (`if: github.event_name != 'pull_request'`)
  → il ne démarre pas sur PR → **les tests sont exécutés une seule fois** dans les deux stratégies.
  `origin` est en outre supérieur sur 4 points : Node 20 épinglé, annulation par PR, validation sur push WIP, étapes nommées.
* **Les 25 points de contrôle Git de la session précédente** (`cline checkpoint`) étaient *dangling*,
  donc élagables par `git gc`. Ils sont désormais protégés par `refs/backup/cline-checkpoints/<date>-<sha>`
  (25 références pointant sur des commits **existants** : aucun objet créé, aucun commit, aucun push).
  Le plus récent (`1f87646`, 21/10 16:15) est **identique à l'état vivant** pour les 6 fichiers critiques
  (comparaison normalisée EOL) : le travail de l'agent précédent est intégralement présent, rien n'a divergé.
  Retrait : `git for-each-ref --format='%(refname)' refs/backup/cline-checkpoints/ | ForEach-Object { git update-ref -d $_ }`
* **L'étape 2 a été répétée à blanc** dans un clone temporaire : commit simulé de **62 fichiers exactement**,
  0 fuite de fichiers de l'agent tiers, 0 divergence avec le worktree vivant, les 4 commandes de la CI vertes
  dans l'arbre commité (182 tests). Rien n'a été commité dans le dépôt actif.

### 9.4 État des sauvegardes

| Sauvegarde | Contenu | Usage |
|---|---|---|
| `backup-precommit-20261021-160913` | état **avant** réconciliation (109 fichiers) + `monitor.yml.local-modifications` (version locale, SHA `ccd47b26b23e…`) | restauration de la version locale de `monitor.yml` |
| `backup-precommit-20261021-163412` | état **après** réconciliation (113 fichiers) + bundle cliquable | restauration de l'état courant |

### 9.5 Ce qui reste à faire (opérations 2 à 5, non autorisées)

1. **Commit local** de la liste blanche (62 fichiers : 6 modifiés + 56 non suivis de ma part ; `monitor.yml` exclu,
   artefacts `site/*.json` exclus, 21 fichiers de l'agent tiers exclus). Jamais `git add -A`.
2. **Push** de `wip/p0-provenance` → déclenche `p0-validation.yml` (validation CI en lecture seule).
3. **Fusion dans `main`** — nécessaire pour que l'artefact publié contienne `early_reversal`, `regime`, `exploitable`.
   *Vérifié le 21/10 : `src/agent_analysis.py` sur `origin/main` et sur `main` fait **271 lignes** et ne contient
   **aucune** occurrence de `early_reversal`.* L'ordre 2 → 3 → 4 reste donc **non négociable** : un `checkout` de `main`
   fait disparaître le moteur tant que l'étape 2 n'a pas eu lieu.
4. **Publication** — régénération de `site/agent_analysis.json` par le cron */15, puis déploiement.

> **Rappel de statut (inchangé)** : la règle reste une **règle de recherche — observation qualifiée**.
> L'intervalle de confiance du pool exploitable **inclut zéro** et les frais réels ne sont pas confirmés :
> aucune rentabilité n'est démontrée.

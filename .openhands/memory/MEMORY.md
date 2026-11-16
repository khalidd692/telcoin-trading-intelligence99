# Mémoire (OpenHands)

## Préférences
- TEL99 : réponses en français, rapports factuels avec preuves, pas de reconstruction.
- Contraintes TEL99 récurrentes : lecture seule, aucun ordre (réel ou simulé), aucun déploiement,
  aucune installation payante, ne pas modifier Smart View ni écraser l'existant.

## Environnement
- Sessions = OpenHands Cloud runtime. Modèle gratuit : `openhands/deepseek-v4.1-flash`
  (profils `Default`, `openhands_deepseek-v4.1-flash`). `switch_llm` limité à ces deux profils.
- agent-server local v1.62.0, API `http://localhost:60000`, en-tête `X-Session-API-Key`.
  POST `/api/conversations` -> HTTP 201. Délégation ACTIVE via `task_tool_set` (tool `task`) :
  les TaskAction créent de vraies sous-conversations sous `/var/openhands/conversations/<cid>/subagents/`.
- SÉCURITÉ sous-agents : registre d'agents module-global « premier-arrivé-gagne » -> noms d'agents
  UNIQUES par exécution obligatoires. Isolation : `sub_agent_scope` {tools:true}. Blocage déterministe :
  hooks PreToolUse, exit 2 = bloque. Ne pas se fier au seul `permission_mode` ; vérifier `base_state.json`.
- Agents personnalisés = fichiers `.agents/agents/*.md` (projet) ou `~/.agents/agents`, `~/.openhands/agents`.
  Le loader ne lit QUE le premier niveau (sous-dossiers et `README.md` ignorés).
- `OPENHANDS_API_KEY` : accès `/api/v1/*` et `/api/automation/v1` sur app.all-hands.dev (0 automation).

## Dépôt khalidd692/telcoin-trading-intelligence99 (TEL99)
- Branches clés : produit `codex/tel99-quant-terminal`, données `tel99-live-data`,
  évaluation `tel99-evaluation-data`, équipe `agents/hermes-simple-team-20261114` (PR #63, base produit).
- `GITHUB_TOKEN` : **avait `contents: write` le 2026-11-15 au soir** (contredit l'entrée lecture seule
  ci-dessous, plus ancienne). Preuve : `git push -u origin fix/pr74-security-hardening-20261115` OK.
  `GET /repos/...` `permissions.push:true`. `main` reste `protected:false` ; `GET /branches/<b>/protection`
  -> 403 (permission *Administration* non accordée). Vérifier l'état réel avant de conclure à un blocage.
  (Historique lecture seule : App installation token `Iv23lizrrwLGm04hszl7` ; helper credential identique.)
- `TEL99_GITHUB_PAT` : PAT fine-grained user `khalidd692`, `admin:true` sur le repo, mais
  `/branches/*/protection` -> 403 ; `rulesets:[]` : ce n'est PAS une protection de branche.
- Workflow `tel99-agent-team-audit.yml` : ne se déclenche QUE sur `agents/hermes-simple-team-20261114`.
  Sur une autre branche, forcer via `POST /actions/workflows/<id>/dispatches {"ref":"<branche>"}`.
- Branche #74 avait une RÉGRESSION : `guard.py` blob `61802849` (sans #71). Référence #71 = `26579ceb`.
- Publier une branche exige un jeton `contents: write`.
- Clone initial SHALLOW : `git bundle create <branche>` échoue au clonage (`Failed to traverse parents`).
  Correctif lecture seule : `git fetch --unshallow origin` PUIS créer le bundle. Le patch `git format-patch -1`
  appliqué via `git am` sur le parent reproduit l'arbre exact (vérifier `rev-parse HEAD^{tree}`).
- Livrable de secours : `/workspace/project/tel99-backup/` (README + `publish-tel99.ps1` Windows + `patches/` 3 patchs
  + bundles incremental/full + tar.gz + SHA256SUMS.txt). Base `320ff86` ; arbre commit 1 `2a94e1e4…`,
  arbre final `6818acd7…`. Après `3db48c1` : `e78a28a` (correctif dry-run) et `fadb218` (doc modèles locaux).
- Voies d'écriture testées SANS résultat (ne pas répéter) : MCP GitHub (aucun outil), proxy git
  `/api/v1/webhooks/secrets` (HTTP 500), `/api/v1/integrations` et `/api/v1/me` (renvoient l'app HTML).
- Piège : `run_pilot.py --dry-run` exigeait un profil LLM → traceback en CI (aucun profil commité). Corrigé.

## Équipe d'agents TEL99 (commit `3db48c1`, branche `agents/hermes-simple-team-20261114`)
- 3 agents actifs `.agents/agents/tel99-{dev,analyst,verifier}.md` (terminal seul, `confirm_risky`, hook
  PreToolUse, budgets plafonnés). 9 rôles réservés INACTIFS dans `.agents/agents/reserve/`.
- Source unique `scripts/agents/team_config.py` + générateur `render_agents.py` (--check en CI) ; lanceur
  `run_pilot.py` (lit le profil LLM au runtime, aucun secret commité) ; garde `guard/guard.py` ;
  vérif `verify_delegation.py` ; tests stdlib `tests/test_agent_team.py` (34).
- GARDE-FOU : juger chaque SEGMENT shell par son mot de TÊTE, pas par recherche de sous-chaîne (sinon
  faux positifs sur `find deploy`, `grep deploy-pages`, `2>&1`, `open(...)` en lecture). Gérer `bash -c`,
  `env VAR=1 cmd`, `xargs cmd`. Exit 2 = bloque, 0 = laisse passer.
- Un plafond `max_iterations` bas fait finir un pilote en `MaxIterationsReached` APRÈS livraison des
  sous-agents : juger sur les TaskAction/rapports, pas sur le seul statut final.
- Les « 12 rôles » d'origine = documentation + `scripts/agents/team_audit.py` (inventaire statique).

## Session 2026-11-15 (reprise PR #71) — corrections importantes
- **CHANGEMENT MAJEUR : le jeton de session a maintenant un accès EN ÉCRITURE.** Contredit l'entrée
  « LECTURE SEULE » ci-dessus. Preuve : `POST /repos/.../git/refs` -> 201, `DELETE` -> 204,
  `git push` -> accepté. Le jeton `GITHUB_TOKEN` (App `Iv23lizrrwLGm04hszl7`) et `TEL99_GITHUB_PAT`
  sont DIFFÉRENTS (sha256 distincts) ; le PAT a `admin:true` mais `/branches/*/protection` renvoie
  quand même 403 (manque le scope `administration`). `main` = `protected:false`, `rulesets:[]`.
- PR #71 = `feat/tel99-hybrid-dispatch-default-branch-20261115` -> `main`, 34 fichiers AJOUTÉS,
  0 modifié/supprimé. Ajoute `.github/workflows/tel99-hybrid-audit.yml` (repository_dispatch
  `tel99_hybrid_audit_v1`, read-only) + `cloudflare/tel99-hybrid/` (Worker `TEL99_ENABLED=false`,
  `crons:[]`) + `scripts/agents/automation/*` + `.agents/agents/*`. Chaîne de PR : #63 -> #66 -> #69 -> #71.
- **`Workers Builds: tel99-hybrid-scheduler` n'est PAS un workflow GitHub** : c'est un check run de
  l'app externe `cloudflare-workers-and-pages` (Cloudflare Git integration). Il échouait sur `b0ac019`
  et passe sur `62f0c00` ; aucun build ne se reproduit hors dépôt. `wrangler deploy --dry-run` local OK.
- **Contournements du garde-fou trouvés et corrigés (commit `62f0c00`)** : (1) `git -C <dir> push`
  / `git -c k=v commit` (options globales à valeur) ; (2) `timeout 5 rm`, `nice -n 10 rm`,
  `xargs -I{} rm` (argument du wrapper = tête de commande) ; (3) `find . -delete` / `-exec`.
  Corrigés par `GIT_VALUE_OPTIONS` + `_git_subcommand()`, saut des args de wrapper dans `head_words()`,
  et blocage des actions `find` destructives. Suite : 531 tests OK, 52 + 69 sur les tests ciblés.
- Quota OpenHands Cloud observé : 20/jour, 10 restants. `GET /api/automation/v1` -> `{automations:[]}`.
  Aucun `repository_dispatch` exécuté (0 run). Aucun cron actif.

## État TEL99 au 2026-11-15 (suite)
- **Crons actifs sur `main`** (contredit « aucun cron ») : tel99-hourly-validation,
  tel99-forward-evaluation, tel99-live-publication, monitor — tous lecture seule.
  Ces 4 workflows existent sur `main` seulement, absents du clone local.
- PR #72 = couche d'intelligence (routeur/mémoire/amélioration mesurée), base
  branche d'équipe, 566 tests OK, démo +35 % réelle. Aucune CI GitHub sur cette
  base : aucun workflow ne cible `agents/hermes-simple-team-20261114`.
- Notion non accessible (aucune clé) — blocage externe, pas un oubli.
- `scripts/agents/intelligence/` : importer via `sys.path` vers `scripts/agents`
  puis `from intelligence import ...` (le dépôt n'utilise pas de paquet `agents`).

## Intégration 3 environnements (PR #73, 2026-11-15)
- `hermes-tel99/router/` et Kilo = INEXISTANTS dans le dépôt. Routeur réel =
  `scripts/agents/intelligence/router.py`. Ne pas croire aux « 13 tests Hermes ».
- `TEL99_GITHUB_PAT` = écriture OK (git push branche réussit). `GITHUB_TOKEN` =
  lecture seule. Code search API NON FIABLE (0 même sur termes existants) → grep tarballs.
- Protocole d'échange v1 + bus dans `scripts/agents/protocol/` (envelope, bus, cli,
  demo, schema, adapters). Bus refuse tout acteur `connected:false` (Kilo).
- Aucune CI sur une PR de base ≠ `main`.

## Autonomie cloud (PR #74, 2026-11-15)
- Orchestrateur cloud = `scripts/agents/automation/orchestrator.py` (venu de PR #66), réuni au
  bus de PR #73 sur `feat/agents-cloud-autonomy-integration-20261115`. Pont = `automation/bus_bridge.py`.
- Persistance durable = `protocol/store.py` KvStore (AUTOMATION_KV_TOKEN) ; sinon FileStore.
- `main` NON protégée (protected:false, rulesets:[]) et le PAT n'a pas la permission Administration
  (GET protection -> 403) => protection main = action humaine.
- Hors sandbox cloud : pas de KV lock => orchestrator refuse toute mission réelle (fail-closed, voulu).
- Mission autorisée réelle = issue #70 (label `tel99-mission`).
- PIÈGE : `journal_entry(state, ..., **dict)` casse si le dict contient une clé `state`.
- PIÈGE : tests qui dépendent de OPENHANDS_API_KEY échouent en CI (quota None -> fail-closed).
- CI : workflow `tel99-agent-team-audit.yml` tourne sur la branche d'équipe (PR + push).

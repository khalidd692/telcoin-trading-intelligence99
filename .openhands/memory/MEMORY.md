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
- **KV automation = CAS** : `GET /v1/kv/{k}?meta=true` → `version` ; `PUT ?nx=true` / `PUT ?if_version=N` ;
  **409** sur conflit. Pas de DELETE conditionnel → libérer = écrire un tombstone par CAS.
  Mécanisme des skills `github` / `github-pr-reviewer` (`ReviewCoordination`).
- **Enfant de conversation** : l'outil `task_tool_set` émet `TaskAction` (`subagent_type`) et
  `TaskObservation` (`subagent`, `task_id`, `status` completed|error, `content`). PAS
  `StartChildConversationObservation`. Doc : /sdk/guides/task-tool-set.
- **Workflow `tel99-agent-team-audit.yml`** : ne se déclenche QUE sur `agents/hermes-simple-team-20261114`.
  Sur une autre branche, forcer via `POST /actions/workflows/<id>/dispatches {"ref":"<branche>"}`.
- PR #71 : draft, base `main`, CI 3/3 OK, fichiers absents de `main` (404), Worker `TEL99_ENABLED=false`,
  `crons: []`. Blocage = décision humaine de fusion (pas technique).
- Clone initial SHALLOW : `git bundle create <branche>` échoue au clonage (`Failed to traverse parents`).
  Correctif lecture seule : `git fetch --unshallow origin` PUIS créer le bundle. Le patch `git format-patch -1`
  appliqué via `git am` sur le parent reproduit l'arbre exact (vérifier `rev-parse HEAD^{tree}`).
- Livrable de secours : `/workspace/project/tel99-backup/` (README + `publish-tel99.ps1` Windows + `patches/` 3 patchs
  + bundles incremental/full + tar.gz + SHA256SUMS.txt). Base `320ff86` ; arbre commit 1 `2a94e1e4…`,
  arbre final `6818acd7…`. Après `3db48c1` : `e78a28a` (correctif dry-run) et `fadb218` (doc modèles locaux).
- Voies d'écriture testées SANS résultat (ne pas répéter) : MCP GitHub (aucun outil), proxy git
  `/api/v1/webhooks/secrets` (HTTP 500), `/api/v1/integrations` et `/api/v1/me` (renvoient l'app HTML).
- Piège : `run_pilot.py --dry-run` exigeait un profil LLM → traceback en CI (aucun profil commité). Corrigé.
- `TEL99_GITHUB_PAT` = jeton ÉCRITURE (`contents:write`) : `git push` OK sur une branche existante,
  mais PAS `actions:write` (dispatch workflow → 403). `GITHUB_TOKEN` = inverse (`actions:write`
  dispatch → 204, mais push → 403). Les deux sont complémentaires ; aucun ne peut tout faire seul.
- TOPOLOGIE (fratrie, pas chaîne) : `main` (défaut) ← PR #71 `feat/tel99-hybrid-dispatch…` (plugin
  complet, orchestrateur ANCIEN 784 l.) ; `codex/tel99-quant-terminal` ← PR #63 `agents/hermes-simple-team…`
  ← PR #74 `feat/agents-cloud-autonomy…` ← PR #75 `fix/pr74-security-hardening…` (durci 1338 l.).
  #71 et #75 sont FRÈRES et touchent les mêmes fichiers additifs → fusion manuelle à conflits add/add.
- Piège SDK (2e session) : `TaskExecutor` renvoie un texte NON VIDE quand un sous-agent ne produit
  rien (`"Task completed with no result."` etc.) → un contrôle de longueur seul = faux succès.
- Coût : le sandbox a `gpt-5.6` par défaut (coût inconnu) → allowlist gratuite CODÉE EN DUR
  (`preflight.check_model`, `team_config.FREE_MODEL_IDS`), insensible à `TEL99_LLM_MODEL`.
- CAS KV : `?meta=true`/`if_version`/`nx=true` documentés UNIQUEMENT pour le namespace user-scoped
  (`X-Session-API-Key` + `?automation_id=`) ; le KV per-run (`Bearer $AUTOMATION_KV_TOKEN`) n'expose
  pas forcément `version` → sonde `kv_meta_probe()`, verrou fail-closed.

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

## Preuves cloud (2026-11-16, branche `converge/tel99-main-20261116`, PR #76)
- MODÈLE GRATUIT PROUVÉ : `openhands/deepseek-v4.1-flash` = défaut du compte cloud ;
  run réel `TEL99-FREE-OK`, quota cloud inchangé (20/20, used_today=0). Le proxy managé
  direct (`llm-proxy.app.all-hands.dev`) refuse (403) : seul le chemin agent-server/conversations marche.
- DÉLÉGATION PROUVÉE : `POST /api/conversations` avec `agent` + TaskTool -> 3 vraies sous-conversations
  (`task:task_N`) sous `/var/openhands/conversations/<cid>/subagents/<id>/base_state.json`.
  Chaque sous-agent : tools=`["terminal"]`, `hook_config.pre_tool_use` présent, budgets plafonnés.
  Inspecter ces fichiers = preuve d'isolation réelle (pas `allowed_tools` de la requête).
- GARDE-FOU PROUVÉ : sur `rm -rf`, `HookExecutionEvent.exit_code=2`, `blocked_actions` =
  "guard: BLOCKED (mutating command 'rm')", AUCUNE ObservationEvent, cible intacte. exit 2 = bloque.
- KV CAS PROUVÉ de bout en bout contre un vrai serveur HTTP local (GET ?meta=true, PUT ?nx=true,
  PUT ?if_version=N, 409 conflit). KV cloud user-scoped = BLOQUÉ sans automation matérialisée
  (GET/PUT /api/automation/v1/kv -> 400 "automation_id required"). 0 automation => pas de KV cloud.
- MANIFESTE `.plugin` validé côté serveur : `GET /api/automation/v1/plugin-spec/preflight?source=…&ref=…&repo_path=.plugin`
  -> HTTP 200, `resolved_ref`, `suggested_trigger`. Le POST `/validate` avec `plugin`/`config` renvoie
  `extra_forbidden` (schéma strict) : utiliser preflight, pas validate.
- WORKFLOW `tel99-hybrid-audit.yml` (repository_dispatch) ABSENT de `main` : il n'existe que sur les
  branches de PR (#71, #76). L'« actif » listé par l'API Actions inclut des workflows non fusionnés.
- Worker hybride `tel99-hybrid-scheduler` : `workers_dev:false` -> 404 (attendu) ; relais WS public
  `telcoin-public-ws-relay` -> /health 200.

## Mission C — livraison autonomie (2026-11-16, PR #76, head c3b6e420)
- AJOUT Mission C : `scripts/agents/automation/emergency.py` = kill-switch (env
  `TEL99_EMERGENCY_STOP`, sentinelle `.tel99-automation-state/EMERGENCY_STOP`, clé KV
  `emergency_stop`, + drapeau config `emergency_stop`). Vérifié EN PREMIER dans `run()`
  -> `exit=3` avant toute sonde/dépense. 11 tests. Schéma `.plugin` étendu.
- `scripts/agents/automation/verify_kv.py` : preuve du VRAI KV (CAS/verrou/dédup/reprise/
  persistance) ; `--local` démarre un serveur KV jetable -> 10/10 PASS. Étape CI ajoutée
  au workflow hybride (tourne en `pull_request`).
- `scripts/agents/automation/automation.config.json` : config prête à coller (dry_run=true,
  conforme `additionalProperties=false`).
- `docs/agents/ACTIVATION_RUNBOOK.md` : 5 actions humaines + séquence de validation finale.
- PIÈGE : `orchestrator` lit `AUTOMATION_API_URL`/`AUTOMATION_KV_TOKEN` à l'IMPORT (constantes
  module). Un harnais qui les pose doit importer orchestrator APRÈS (import paresseux).
- PIÈGE : `kv_meta_probe` renvoie `supported` seulement si la clé EXISTE ; sonder AVANT
  acquisition -> `key_absent:true`. Sonder APRÈS acquire.
- PR #76 : 85 fichiers, +13060/-0, mergeable=clean, CI 4/4. 680 tests OK (skipped=6).

## Mission C — clôture technique (2026-11-16, PR #76 head 7cfd5caf)
- Config d'automation : la clé `_comment` violait `additionalProperties:false` -> SUPPRIMÉE.
  Test `test_shipped_automation_config_matches_the_plugin_schema` valide la config EXACTE
  contre le schéma (jsonschema 4.26 dispo après `pip install jsonschema`).
- Arrêt d'urgence fiabilisé : frein LOCAL (env `TEL99_EMERGENCY_STOP`, sentinelle
  `.tel99-automation-state/EMERGENCY_STOP`, drapeau config `emergency_stop`) évalué AVANT
  `load_state()` -> le chemin arrêté ne fait AUCUN accès réseau (avant : load_state lisait le KV).
  Clé KV `emergency_stop` vérifiée ensuite. Deux portées distinctes documentées :
  « prochain lancement » vs « interrompre une conversation pilotée par le run ».
  `wait_for(cid, deadline, poll, state_dir=...)` relit le frein local, appelle
  `interrupt_conversation` et retourne `stopped`. Diagnostic : `scope=next_run_and_owned_conversation`.
- `docs/agents/ACTIVATION_DOSSIER.md` = index du dossier final d'activation.
- 688 tests OK (skipped=6) ; CI PR #76 4/4 ; automations=0.

# Autonomie cloud TEL99 — preuves mesurées (16/11/2026)

Chaque ligne ci-dessous est une **sonde ou un run réel exécuté**, pas une
supposition. Ce document corrige les affirmations antérieures devenues fausses.
Règles respectées : aucun ordre (réel ou simulé), aucun déploiement, aucun
merge, aucun cron activé, aucun secret exposé.

## 1. Modèle gratuit — VÉRIFIÉ (run réel, coût nul)

Un run réel du modèle gratuit a été exécuté via l'agent-server local.

| Élément | Valeur mesurée |
|---|---|
| Modèle | `openhands/deepseek-v4.1-flash` |
| Conversation | `a1703e38-8880-491b-a7c6-eec69e567719` (créée, exécutée, supprimée) |
| Réponse | `TEL99-FREE-OK` |
| Coût | quota cloud **inchangé** : `daily_limit=20`, `used_today=0`, `remaining=20` |
| Config cloud | `GET /api/v1/settings` → `agent_settings.llm.model = "openhands/deepseek-v4.1-flash"` |
| Modèles vérifiés | `GET /api/llm/models/verified` → `openhands` liste `deepseek-v4.1-flash` |

**Correction** : `CLOUD_CAPABILITIES_MEASURED.md` affirmait « Modèles gratuits :
le routeur refuse tout run réel ». C'est **faux** : le modèle gratuit est le
défaut du compte cloud et un run réel a abouti.

Le proxy managé direct (`llm-proxy.app.all-hands.dev`) refuse un appel hors
agent-server (`403 PermissionDeniedError`), mais le **chemin agent-server** — le
seul utilisé par les agents — fonctionne.

## 2. Délégation des trois sous-agents — VÉRIFIÉ (run réel)

Conversation `3d1c7717-7b7c-4ad7-b9e3-384dd17de0d8` (`execution_status=finished`).

| Preuve | Valeur mesurée |
|---|---|
| Sous-conversations réelles | `task:task_00000001`, `task:task_00000002`, `task:task_00000003` |
| Répertoires persistés | `/var/openhands/conversations/…/subagents/<id>/base_state.json` |
| Outils réels par sous-agent | `["terminal"]` uniquement |
| Garde-fou actif | `hook_config.pre_tool_use` présent dans chaque `base_state.json` |
| Garde-fou exécuté | `HookExecutionEvent` par sous-agent, `exit_code=0` |
| Budgets plafonnés | `max_iterations=4`, `max_budget_per_run=0.02` par sous-agent |
| Rapport | chaque sous-agent a rendu un message final avec la sortie exacte |
| Modèle hérité | `inherit` → `openhands/deepseek-v4.1-flash` |

Un premier run a fini en `MaxIterationsReached` (limite 6) **après** travail réel :
le plafond borne le run, il ne l'empêche pas.

## 3. Verrou KV à comparaison-échange (CAS) — VÉRIFIÉ de bout en bout

Le verrou d'unicité de mission a été exécuté contre un **vrai serveur HTTP**
local implémentant le contrat documenté (`GET ?meta=true`, `PUT ?nx=true`,
`PUT ?if_version=<n>`, `409` sur conflit).

| Étape | Résultat |
|---|---|
| 1) `acquire_lock("run-a")` (clé absente) | **True** — écriture `nx=true` → 201 |
| 2) `acquire_lock("run-b")` (verrou tenu) | **False** — « lock held by run-a until … » |
| 3) `kv_get_meta` | `owner=run-a`, `version=1` |
| 4) `release_lock("run-a")` | tombstones conditionnel (`if_version`) |
| 5) `acquire_lock("run-c")` | **True** |
| `kv_meta_probe` | `supported: True`, `has_version: True` |

Fail-closed confirmé : sans backend exposant une version, `acquire_lock`
retourne `False` et **refuse** de démarrer une mission réelle.

## 4. KV cloud user-scoped — DÉBLOQUÉ (voir §10)

`GET/PUT /api/automation/v1/kv/...` sans `automation_id` → **HTTP 400**
« automation_id query parameter is required ». Avec un `automation_id` inexistant
→ **HTTP 404** « Automation not found ». Un **brouillon** (`/v1/drafts`) ne
matérialise pas d'automation : le KV le refuse aussi.

Correction du 16/11 : une automation **matérialisée** (même INACTIVE) suffit à
ouvrir le KV réel. Une automation a été créée en `state=INACTIVE`, et
`verify_kv.py` y passe **10/10** (§10). Le verrou n'est donc plus « bloqué » :
il est prouvé localement (§3) **et** contre le KV cloud réel.

## 5. Manifeste de plugin — VALIDÉ côté serveur (lecture seule)

`GET /api/automation/v1/plugin-spec/preflight?source=…&ref=converge/tel99-main-20261116&repo_path=.plugin`
→ **HTTP 200**, `resolved_ref = f3a85ea7…`, déclencheur suggéré **événement**
`issues.labeled` (voir §11 : `repository_dispatch` n'est pas délivré),
`runtime.llm_profile.default_name = openhands_deepseek-v4.1-flash`.
Le serveur résout et parse le manifeste sans effet de bord.

## 6. Garde-fou en conditions réelles — VÉRIFIÉ (action bloquée)

Une conversation réelle a reçu l'instruction d'exécuter `rm -rf /tmp/tel99_probe_guard`.

| Preuve | Valeur mesurée |
|---|---|
| Action proposée | `terminal` : `rm -rf /tmp/tel99_probe_guard` |
| `HookExecutionEvent` | **`exit_code = 2`** (blocage) |
| `blocked_actions` | `"guard: BLOCKED (mutating command 'rm')"` |
| `ObservationEvent` | **aucune** — la commande n'a jamais été exécutée |
| Dossier cible | toujours présent après le run (non supprimé) |

Le garde-fou **agit**, il ne se contente pas d'avertir : la mutation a été
empêchée avant toute exécution.

## 7. Sonde de diagnostic — CORRIGÉE

`diagnose_environment()` appelait `GET /api/conversations` **sans** clé de
session : le serveur répondait **HTTP 422** (`ids` manquant), donc un serveur
**vivant** était signalé non joignable. Corrigé : envoi de `X-Session-API-Key`
et endpoint `GET /api/conversations/count`. Résultat après correctif :
`HTTP 200 (authenticated)`. Deux tests de non-régression ajoutés.

## 8. Quota cloud

`GET /api/quota/status` → `daily_limit=20`, `used_today=0`, `remaining=20`,
`reset_at=2026-11-17T00:00:00Z`. Ce quota limite le **nombre** de conversations,
pas le coût : le budget par run reste la limite réelle.

## 9. Capacités d'automation

`GET /api/automation/v1/capabilities` → `ready:true`,
`maxAutomationTimeoutSeconds:1800`, `triggerKinds:[cron,event]`,
`eventSources` incluant `github`, `eventTypes` incluant `issues.*`,
`issue_comment.*`, `pull_request.*`, `push`, `release.*`, `workflow_run.*`.
Le paquet runtime du plugin pèse **143 Ko** (< limite upload 1 Mo).

## 10. KV cloud réel — DÉBLOQUÉ et VÉRIFIÉ (10/10)

Une automation **matérialisée** suffit pour atteindre le KV réel, sans l'activer.
Automation `6c3ed81d-9c20-4040-abad-13f26fe025f9` créée en `state=INACTIVE`.

| Vérification | Résultat |
|---|---|
| `verify_kv.py` contre le KV réel | **PASS (10 checks)** |
| Verrou (CAS, nx) | PASS — un second propriétaire est refusé |
| Bus (ouverture / reprise / dédup / persistance) | PASS |

**Défaut réel trouvé et corrigé** : le KV cloud route `/v1/kv/{key}` sur **un seul
segment** ; une clé contenant `/` renvoie un **404 de routage** au lieu de la
valeur. `KvStore` construisait `tel99-bus/missions/<id>` → le bus ne pouvait rien
persister. Invisible en stockage fichier local et dans l'auto-vérification
en mémoire. `KvStore` mappe désormais `/` → `.` sur le fil et filtre `?prefix=`
côté client (le serveur l'ignore).

## 11. Déclencheur réel — ÉVÉNEMENT, pas `repository_dispatch`

`GET /api/automation/v1/capabilities` → `eventTypes` (source `github`) :
`issues.*`, `issue_comment.*`, `pull_request.*`, `pull_request_review.*`, `push`,
`release.*`, `workflow_run.*`. **`repository_dispatch` n'y figure pas** : un
déclencheur sur cet évènement ne se déclencherait **jamais**.

Déclencheur retenu : `issues.labeled` (source `github`), filtré sur
`repository.full_name` et le label `tel99-mission` — l'évènement qui correspond
réellement à la file de missions. Le manifeste `.plugin` suggère ce même
déclencheur (`suggested_trigger_template`).

## 12. Dry-run mission #70 — 0 conversation

Mission #70 (lecture seule) sélectionnée par `policy.select_mission`. Journal :
`dry_run: no conversation started`, `exit=0`. Conversations agent-server :
**0 avant, 0 après**. Aucun `POST /api/conversations` émis.

## Ce qui reste à faire pour activer (action humaine)

1. Fusionner la branche de convergence (PR #76) dans `main` — **autorisation requise**.
2. Protéger `main` (PR obligatoire, checks, pas de force-push) — 403 avec les jetons actuels.
3. Révoquer le jeton GitHub exposé et en émettre un neuf, stocké hors dépôt.
4. Passer l'automation `dry_run` à `false` et déclencher **une** fois (label
   `tel99-mission`), puis observer un run **sans le PC**.
5. Seulement alors, considérer le régime permanent.

Aucune de ces étapes n'a été exécutée : elles exigent une autorisation explicite.

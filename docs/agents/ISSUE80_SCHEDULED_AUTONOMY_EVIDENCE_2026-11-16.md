# Issue #80 — Démonstration d'autonomie cloud (PC éteint) — preuves mesurées

Date : 2026-11-16 (UTC). Auteur : agent OpenHands, à la demande du responsable technique.

**Statut global : PASS sur les critères d'exécution (2 runs réels, dont 1 programmé) ; BLOCKED sur 2 points humains.**
Aucun merge, aucun déploiement production, aucun cron permanent, aucun ordre financier,
aucun abonnement, aucun modèle payant. `main`, les données et les workflows de production
n'ont pas été modifiés par cet agent. Les deux automations sont laissées `INACTIVE`.

> Toutes les valeurs ci-dessous proviennent de **runs et de sondes réels**, avec IDs et
> horodatages UTC. Aucun résultat n'est simulé. Là où une preuve manque, c'est écrit
> explicitement (constat vs hypothèse).

---

## 0. Résumé exécutif (PASS / FAIL / BLOCKED)

| Critère de réception | Statut | Preuve |
|---|---|---|
| Mission manuelle cloud prouvée | **PASS** | run `58126453` `COMPLETED` (déjà prouvé #79, re-vérifié ici) |
| **Run programmé** distinct, sans PC | **PASS** | cron `fdffcbc4` → run `eeb51ffe` `COMPLETED` à `13:06:25Z` |
| 3 sous-agents natifs, outils restreints | **PASS** | `tel99-analyst/dev/verifier` par run, `tools=["terminal"]` |
| Guard runtime vérifié | **PASS (partiel)** | guard bloquant en local + `preflight_ok` dans le run ; `base_state.json` du sandbox cloud non lisible depuis cette session |
| Run `COMPLETED` + coûts/quota + IDs | **PASS** | coûts `$0.026975` / `$0.031261` ; quota `20/jour` ; conv IDs ci-dessous |
| Verrou KV CAS (pas de double mission) | **PASS** | CAS `nx`/`if_version`/`409` sur le **KV cloud réel** + `verify_kv.py` 10/10 |
| Reprise après échec sans réexécution | **PASS** | `stale_active_reconciled` → `resume` ; `processed=[70,81]` |
| Aucune action exchange / ordre / déploiement / secret | **PASS** | voir §8 |
| Aucun merge ni activation permanente | **PASS** | automations `INACTIVE` ; `main` intact (§8) |
| Étape exigeant paiement/permission | **BLOCKED** | protection `main` (403) ; PR #79 non fusionnée (§9) |

---

## 1. Statut réel de l'automation `6c3ed81d-9c20-4040-abad-13f26fe025f9`

Sondé via `GET /api/automation/v1/{id}` (OpenHands Cloud).

| Instant (UTC) | `state` | `plugin.ref` | `dry_run` | Note |
|---|---|---|---|---|
| 12:19 (début de session) | `INACTIVE` | `main` | `false` | tel que trouvé |
| 12:22 → 12:30 | `ACTIVE` | `fix/tel99-autonomy-confirmation-v2` | `false` | activation par l'opérateur (hors agent) |
| 12:30:37 | `INACTIVE` | `main` | `false` | `disabled_reason=manual` (hors agent) |
| 13:10 (fin) | `INACTIVE` | `main` | `false` | inchangé |

- Modèle : `openhands_deepseek-v4.1-flash` (profil `openhands_deepseek-v4.1-flash`) — **modèle gratuit**.
- Type : `plugin_spec`, `runner: script`, entrypoint
  `cd "$AUTOMATION_PLUGIN_ROOT" && python3 scripts/agents/automation/orchestrator.py`.
- Déclencheur : événement `issues.labeled`, source `github`, filtre
  `repository.full_name == 'khalidd692/telcoin-trading-intelligence99' && contains(issue.labels[].name, 'tel99-mission')`.
- Capacités plateforme : `maxAutomationTimeoutSeconds=1800`, `triggerKinds=[cron,event]`,
  `eventSources` inclut `github`. Un déclencheur **cron** est accepté (prouvé §5).
- **Correction vs `docs/agents/CLOUD_AUTONOMY_PROVEN_2026-11-16.md`** : ce document indiquait
  l'automation `INACTIVE`. Elle a été **activée le 16/11 vers 12:22Z** puis redésactivée à
  12:30:37Z. Son état ne doit pas être présumé d'une session à l'autre.

Runs observés (extrait, `GET /{id}/runs`) :

| Run | Statut | Source | Créé (UTC) | Terminé (UTC) | ref résolu | Erreur |
|---|---|---|---|---|---|---|
| `b26571d3` | **COMPLETED** | **event** | 12:22:11 | 12:27:04 | `0ac0b5d7` | — |
| `58126453` | **COMPLETED** | manual | 04:31:38 | 04:37:00 | `c6ef304c` | — |
| `9e5c3e33` | FAILED | manual | 04:22:49 | 04:27:12 | `9ca20105` | `orchestrator exit 2` |
| `5062beb6` | FAILED | manual | 03:29:29 | 03:41:45 | `853e03ca` | `Timed out` |
| `fb444aed` | FAILED | manual | 03:28:38 | 03:28:43 | `853e03ca` | `exit 3` (arrêt d'urgence) |
| `d98683ba`, `41988efd` | COMPLETED | manual | 03:26–03:28 | — | `853e03ca` | (dry-run) |

---

## 2. Validation indépendante de PR #79 (`fix/tel99-autonomy-confirmation-v2`, head `0ac0b5d7`)

PR #79 : `open`, **draft**, `mergeable: clean`, 4 fichiers
(`orchestrator.py +99/-38`, `run_pilot.py`, `tests/test_cloud_autonomy.py`, `tests/test_cloud_autonomy_e2e.py`).

### Bug 1 — `confirm_unknown: true` gèle le run non supervisé
- `main` (`orchestrator.py` blob `4b7ded4`) contient `"confirm_unknown": True`.
- `0ac0b5d7` (blob `de5299e`) le passe à `False` + abandon explicite si `confirmation_required`.
- **Preuve indirecte réelle** : run `5062beb6` (ref `main`) → `Timed out: command timed out or was killed`
  (fin `03:41:45Z`), alors que `timeout_at=03:41:33Z` : le run a brûlé tout son délai puis a été tué par
  la plateforme — signature d'un blocage en `waiting_for_confirmation`.

### Bug 2 — lecture des événements via le mauvais endpoint
- `main` lisait `GET /api/conversations/{cid}/events` (endpoint **batch** : exige une liste d'IDs dans le
  corps). `0ac0b5d7` ajoute `_iter_events()` sur `GET .../events/search` paginé.
- **Reproduction indépendante sur l'API réelle** (agent-server local v1.62.0) :

| Requête | Résultat mesuré |
|---|---|
| `GET /api/conversations/{cid}/events` (GET nu) | **HTTP 422** `{"detail":[{"type":"missing","loc":["body"],"msg":"Field required"}]}` |
| `GET /api/conversations/{cid}/events/search?limit=5` | **HTTP 200** — `keys=['items','next_page_id']`, `items=5`, `next_page_id` présent |

- **Preuve indirecte réelle** : run `9e5c3e33` (correctif v1, avant fix events) → verdict
  `roles 0/0/0`, `bus_outcome: failed`. Run `58126453` (après fix events, ref `c6ef304c`) →
  verdict `roles 1/1/1`, `COMPLETED`.

**Conclusion PR #79 : PASS** (les deux correctifs sont cohérents avec les API réelles). PR non fusionnée
→ `main` porte encore les deux bugs (§9).

---

## 3. Run 1 — mission cloud manuelle (déjà prouvée par #79, re-vérifiée)

| Champ | Valeur |
|---|---|
| Run | `58126453-02ec-43de-9b3d-b2bf15208377` |
| Statut | `COMPLETED` |
| Source | `manual` |
| Créé / terminé (UTC) | `2026-11-16T04:31:38Z` / `2026-11-16T04:37:00Z` |
| ref résolu | `c6ef304c` |
| Conversation | `a4cc1863-bb1b-4d58-884d-653f51d7028f` |
| Coût mesuré | `$0.032855` (métrique tokens, modèle gratuit) |
| Verdict | `validated=true`, `roles {development:1, quant:1, quality:1}` |

---

## 4. Run 2 — mission cloud déclenchée par ÉVÉNEMENT (sans PC)

Déclencheur : issue GitHub #81 créée puis labellisée `tel99-mission` à `12:22:09Z`
(acteur `khalidd692`) → l'automation a démarré **seule**.

| Champ | Valeur |
|---|---|
| Run | `b26571d3-55a8-4df1-b5a7-38e5dd58304c` |
| Statut | `COMPLETED` |
| Source | **`event`** |
| Créé / démarré / terminé (UTC) | `12:22:11Z` / `12:22:14Z` / `12:27:04Z` |
| ref résolu | `0ac0b5d7` (PR #79) |
| Sandbox | `EHgexwxUYkEMa26Iv50bC` |
| Conversation | `cca6b78b-90e9-432e-bb18-257f895d0f87` |
| Coût mesuré | `$0.026975` |
| Mission | issue #81 (lecture seule) |
| Verdict | `validated=true`, `roles {development:1, quant:1, quality:1}` |

Journal KV (extrait) :

```
12:22:18 run_start        dry_run=false
12:22:18 environment      agent_server_reachable=true, kv_lock_available=true,
                          kv_lock_capability{supported:true, has_version:true}
12:22:18 preflight_ok     checks=[guard, team_config]
12:22:18 quota            remaining=10
12:22:20 mission_selected issue=81
12:22:20 lock_acquired    owner=b26571d3…
12:22:20 bus_mission      action=opened, durable_across_container=true
12:22:20 payload_ok       sub_agents=[tel99-dev-122220, tel99-analyst-122220, tel99-verifier-122220]
12:22:21 conversation_started cca6b78b…
12:27:01 conversation_finished status=finished
12:27:01 outcome_verdict  validated=true roles 1/1/1
12:27:03 bus_outcome      mission_state=done
```

Preuves de rôles (extraites du bus, `tel99-bus.missions.msn-gh-81-430af7b3349e`) :

| Rôle | Sous-agent | Statut | Taille rapport | Placeholder |
|---|---|---|---|---|
| Analyste | `tel99-analyst-122220` | `completed` | 8201 car. | non |
| Développeur | `tel99-dev-122220` | `completed` | 7682 car. | non |
| Vérificateur | `tel99-verifier-122220` | `completed` | 5631 car. | non |

---

## 5. Run 3 — mission cloud PROGRAMMÉE (cron, non-production, auto-désactivée)

Objectif : prouver un déclenchement **programmé** indépendant du PC, sans cron permanent.

**Automation dédiée** (temporaire, non-production) :

| Champ | Valeur |
|---|---|
| ID | `fdffcbc4-4297-4276-a8dc-8e2b1cffad5f` |
| Nom | `TEL99 issue80 scheduled single-shot (auto-disable)` |
| Déclencheur | **cron `59 12 * * *` (UTC)** |
| ref plugin | `fix/tel99-autonomy-confirmation-v2` (`0ac0b5d7`) |
| Config | `dry_run=false`, `max_concurrent_missions=1`, `max_runtime_seconds=1200`, `max_budget_usd=1.0`, `agent_max_budget_usd=0.25`, `quota_min_remaining=2`, `emergency_stop=false` |
| Cycle de vie | créée `12:54:49Z` `ACTIVE` → **auto-désactivée `13:06:45Z` `INACTIVE`** |

| Champ du run | Valeur |
|---|---|
| Run | `eeb51ffe-36b7-421b-be7d-3e5ac9903a91` |
| Statut | **`COMPLETED`** |
| Source | **`cron`** |
| Prévu (schedule) / créé / démarré / terminé (UTC) | `12:59:00` / `12:59:51Z` / `12:59:51Z` / `13:06:25Z` |
| ref résolu | `0ac0b5d7` |
| Sandbox | `5W89bpE0wAK403ru7sJ5l4` |
| Conversation | `ee76a0a1-7ad5-44d9-8270-df1cda96234f` |
| Coût mesuré | `$0.031261` |
| Mission | issue #70 (lecture seule, la plus ancienne éligible) |
| Verdict | `validated=true`, `roles {development:1, quant:1, quality:1}`, coordinateur 6055 car. |

Journal KV (extrait) :

```
12:59:55 run_start      dry_run=false, owner=eeb51ffe…
12:59:56 preflight_ok   checks=[guard, team_config]
12:59:56 quota          remaining=5
12:59:57 mission_selected issue=70
12:59:57 lock_acquired  owner=eeb51ffe…
12:59:57 bus_mission    action=opened, msn-gh-70-f2dd9a84926f
12:59:57 payload_ok     sub_agents=[tel99-dev-125957, tel99-analyst-125957, tel99-verifier-125957]
12:59:58 conversation_started ee76a0a1…
13:06:23 conversation_finished status=finished
13:06:23 outcome_verdict validated=true roles 1/1/1
13:06:24 bus_outcome    mission_state=done
13:06:45 (hors run) AUTO-DISABLE  automation fdffcbc4 → INACTIVE
```

Preuves de rôles (bus `tel99-bus.missions.msn-gh-70-f2dd9a84926f`) :

| Rôle | Sous-agent | Statut | Taille rapport | Placeholder |
|---|---|---|---|---|
| Analyste | `tel99-analyst-125957` | `completed` | 7938 car. | non |
| Développeur | `tel99-dev-125957` | `completed` | 8492 car. | non |
| Vérificateur | `tel99-verifier-125957` | `completed` | 5475 car. | non |

**Auto-désactivation** : le plugin ne possède pas de mécanisme d'auto-désactivation propre ; elle a été
réalisée par un **chien de garde externe** (script local) qui surveille le run puis `PATCH {enabled:false}`.
C'est une limite à corriger côté produit (§9). Le résultat reste : un seul déclenchement, puis
`INACTIVE`.

**Portée honnête** : ces deux runs prouvent la **capacité cloud indépendante du PC** (le run ne dépend
d'aucune interaction Windows). Ils ne prouvent **pas** la lecture de l'état électrique du PC, ni
l'autonomie de Hermes Desktop, ni la coordination Hermes ↔ OpenHands ↔ Kilo (§7).

---

## 6. Verrou KV CAS, idempotence, reprise, arrêt d'urgence

### 6a. CAS prouvé sur le **KV cloud réel** (clé d'essai `tel99-verify-scratch-80`, libérée ensuite)

| Étape | Requête | Résultat mesuré |
|---|---|---|
| 1 | `PUT ?nx=true` (clé absente) | **HTTP 201** `created:true` |
| 2 | `GET ?meta=true` | `version=96`, `value={owner:run-a}` |
| 3 | `PUT ?nx=true` (clé existante) | **HTTP 409** `key_exists` |
| 4 | `PUT ?if_version=96` | **HTTP 200** |
| 5 | `PUT ?if_version=96` (périmé) | **HTTP 409** `version_mismatch` (expected 96, actual 97) |
| 6 | libération par `if_version` (tombstone) | **HTTP 200**, version 98 |

Le verrou de mission réel a été observé : version 85 détenue par `b26571d3` pendant son run, puis
libérée (tombstone `owner=""`, `released_by=b26571d3`) à `12:27:03Z`.

`verify_kv.py --local` (contrat documenté) → **PASS (10 checks)** : CAS, verrou, dédup, reprise, persistance.

### 6b. Idempotence / reprise (journal réel)

```
03:29:35 lock_acquired              owner=5062beb6… (run tué par timeout)
04:22:53 stale_active_reconciled    previous={issue:70,…}, note="lock expired or absent; mission re-queued"
04:22:53 resume                     "interrupted mission re-queued for resume"
```

`state.processed` finit à `[70, 81]` : une mission terminée n'est pas retraitée (dédup bus + `processed`).

### 6c. Arrêt d'urgence

```
03:28:42 emergency_stop  reason="KV key 'emergency_stop' is set", scope="next_run"
```

Le run `fb444aed` s'est terminé en **`exit 3`** (`03:28:43Z`) : le frein KV a stoppé le lancement
**avant** toute conversation et tout coût. Tests unitaires : `EmergencyStopTests` (13) + e2e
(`test_wait_for_interrupts_when_the_brake_is_set`, `test_brake_is_checked_before_any_network_probe`) — OK.

---

## 7. Guard runtime et restrictions

- Guard **exécuté en local** : `git push origin main` → `exit 2` (`BLOCKED (git push)`) ;
  `git status` → `exit 0`. Le `preflight` du run exécute réellement le guard (`preflight_ok`).
- Sous-agents : `tools=["terminal"]` uniquement, noms uniques par run (`…-HHMMSS`), hook `pre_tool_use`,
  `permission_mode` de confirmation, budgets plafonnés (`agent_max_budget_usd=0.25`).
- **Limite honnête** : les `base_state.json` des sous-agents du run cloud vivent dans le **sandbox du
  run** (`EHgexwxUYkEMa26Iv50bC`, `5W89bpE0wAK403ru7sJ5l4`), non monté dans cette session. La
  vérification `verify_runtime.py` (qui lit `/var/openhands/conversations`) n'a donc pas pu être
  rejouée sur le run cloud ; elle l'a été en local et par les tests. Le verdict de rôles 1/1/1 et le
  `payload_ok` (3 agents, terminal seul) constituent la preuve runtime disponible.

---

## 8. Intégrité production et sécurité

- **`main` non modifiée par cet agent** : elle n'avance que par les commits du bot de publication
  (`f66f8dde → 2f13c4a2 → cb7c59bb`, `Refresh published TEL/USDT market report [skip ci]`).
- Aucun merge, aucune PR fusionnée, aucun déploiement, aucun cron permanent, aucun ordre (réel ou simulé),
  aucune modification de Smart View, aucune donnée écrasée.
- **Aucun secret** dans les commits, journaux ou rapports : seuls des booléens de présence
  (`session_key_present`, `github_token_present`) apparaissent.
- Les deux automations sont laissées **`INACTIVE`** (`6c3ed81d…`, `fdffcbc4…`).
- Nettoyage : issue sonde #82 **fermée** (`not_planned`) et **désétiquetée** `tel99-mission` ; clé KV
  d'essai `tel99-verify-scratch-80` libérée par CAS ; automation sonde `87157121…` supprimée (HTTP 204).
- Tests : `python -m unittest discover -s tests` → **691 tests OK (6 skipped)**.

---

## 9. BLOCKED — interventions humaines exactes

| # | Blocage | Cause mesurée | Intervention humaine |
|---|---|---|---|
| B1 | `main` non protégée | `GET /branches/main/protection` → **403** ; `GET /rulesets` → `[]` (les deux jetons manquent le scope *Administration*) | Protéger `main` (PR obligatoire, CI, pas de force-push) dans Settings → Branches |
| B2 | Scheduler sur `main` inopérant | `main` porte encore les **deux bugs** (#79 non fusionnée) : `confirm_unknown:true` (blocage) + lecture `/events` (verdict 0/0/0) | Fusionner PR #79 (ou appliquer ses 2 correctifs sur `main`) |
| B3 | Auto-désactivation produit | Le plugin n'a pas de mécanisme « un seul déclenchement puis off » ; il a fallu un chien de garde externe | Ajouter une expiration/auto-désactivation au plugin avant tout usage permanent |
| B4 | Sandbox cloud non inspectable | Les artefacts runtime du run (base_state.json) ne sont pas exposés par l'API cloud publique | Exposer un endpoint d'inspection, ou lancer `verify_runtime.py` depuis le sandbox du run |

Aucun de B1–B4 n'a été contourné par un assouplissement de la sécurité.

---

## 10. Passation

### Vers Kilo (validation indépendante)
1. Rejouer la reproduction du bug 2 : `GET /api/conversations/{cid}/events` (nu) → attendu **422** ;
   `GET .../events/search?limit=5` → attendu **200** avec `items` + `next_page_id`.
2. Vérifier sur `0ac0b5d7` que `build_payload` porte `confirm_unknown: false` et que
   `wait_for` retourne `confirmation_required` après 3 sondages.
3. Confirmer les runs `58126453`, `b26571d3`, `eeb51ffe` (statuts, refs, conversations) via
   `GET /api/automation/v1/6c3ed81d-…/runs` et `GET /api/automation/v1/fdffcbc4-…/runs`.
4. Contrôler le CAS sur le KV cloud avec une clé d'essai dédiée (ne pas toucher `active_mission_lock`).
5. Statut proposé : **validé sous réserve** de B1/B2 (protection `main` + fusion #79).

### Vers Hermes (ingestion)
- Mission `msn-gh-81-430af7b3349e` et `msn-gh-70-f2dd9a84926f` : `state=done`, 3 étapes
  (development/quant/quality) complétées, résultat `success`.
- Statut à ingérer : **`proposé`** jusqu'à validation indépendante par Kilo.
- Ne pas déduire de « stratégie rentable » ni d'« autonomie Hermes » de ces runs : ils prouvent
  uniquement l'exécution cloud indépendante du PC.

---

## 11. Ce qui reste à faire (après B1/B2)

1. Fusionner PR #79 dans `main` (ou appliquer ses correctifs) — **autorisation humaine**.
2. Protéger `main` — **action humaine**.
3. Ajouter au plugin une auto-désactivation/expiration pour un usage programmé sûr (B3).
4. Alors seulement, considérer un régime planifié permanent, avec budget et quota surveillés.

Rollback à tout instant : poser `emergency_stop` (KV / env / sentinelle) puis désactiver l'automation.

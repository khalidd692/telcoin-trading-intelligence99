# Autonomie cloud — intégration, sécurité et passation

Ce document réconcilie et relie les composants existants. Il ne reconstruit rien.
Il enregistre des **faits mesurés**, chacun daté et rattaché à sa source.

## 1. Ce qui a été réconcilié

Deux branches portaient chacune une moitié du système, sans se connaître :

| Branche | Apport | État |
|---|---|---|
| `feat/cloud-autonomy-plugin-20261115` (PR #66) | orchestrateur cloud (`scripts/agents/automation/`), manifeste `.plugin/plugin.json` | intact, importé tel quel |
| `feat/agents-integration-bus-20261115` (PR #73) | protocole + bus (`scripts/agents/protocol/`) | intact |

La branche `feat/agents-cloud-autonomy-integration-20261115` réunit les deux. Les
fichiers de #66 sont repris **sans modification** ; le workflow d'audit d'équipe
est étendu à la branche d'équipe (PR + push) pour que la CI tourne enfin dessus.

## 2. Le pont bus ↔ orchestrateur

`scripts/agents/automation/bus_bridge.py` est le **seul** lien entre les deux.

- `correlation_id(repository, issue)` = `msn-gh-<n>-<sha256[:12]>` : **déterministe**,
  donc la même issue mappe toujours la même mission et la même branche de travail.
- `is_already_finished()` : une mission terminée sur le bus n'est **jamais**
  retraitée, même si un run ultérieur resélectionne l'issue.
- `open_or_resume()` : ouvre, ou reprend une mission interrompue.
- `record_outcome()` : écrit le résultat **et** un apprentissage validé.

L'orchestrateur ouvre la mission sur le bus **après** avoir pris le verrou KV :
un run refusé ne laisse donc **aucune** mission fantôme.

## 3. Persistance cloud

`scripts/agents/protocol/store.py` expose deux backends derrière la même interface :

| Backend | Quand | Survit à la destruction du conteneur |
|---|---|---|
| `FileStore` | local, tests | non |
| `KvStore` | `AUTOMATION_KV_TOKEN` + `AUTOMATION_API_URL` présents | **oui** |

`default_store()` choisit automatiquement. Le bus persiste missions, enveloppes,
résultats et apprentissages via ce store. C'est le seul stockage durable déjà
disponible pour un run de plugin-script : aucune infrastructure nouvelle n'est
installée.

**Le bus est obligatoire pour un run réel** (`require_durable_bus=true` par
défaut). Avant de démarrer une conversation, l'orchestrateur exige :

1. un store **durable** (`durable_across_container` = vrai) — un `FileStore`
   fait **refuser** le run ;
2. la **déduplication** lisible sur le bus (une mission `done` n'est jamais
   rejouée) ;
3. l'**ouverture** effective de la mission sur le registre (fail-closed : si
   l'ouverture échoue, aucune conversation n'est lancée).

En fin de run, l'**écriture durable finale** est également fail-closed : si elle
échoue, la mission n'est **ni** déclarée `done` **ni** marquée `processed`, donc
le run suivant la reprend. `require_durable_bus=false` (déconseillé, local
uniquement) rétablit l'ancien comportement non bloquant.

## 3bis. Validation des résultats — un statut `finished` n'est pas un succès

Un statut d'exécution `finished` dit seulement que la conversation s'est
arrêtée. Il ne prouve **ni** que les trois rôles ont tourné, **ni** qu'ils ont
produit un rapport. Après le run, l'orchestrateur collecte donc des **preuves**
observables via l'API agent-server :

- la réponse finale du coordinateur (`/agent_final_response`) ;
- chaque délégation de rôle faite par le coordinateur via l'outil
  `task_tool_set` : `TaskAction` (`subagent_type` = nom de l'agent) et
  l'observation correspondante `TaskObservation` (`subagent`, `status`,
  `content`) dans `/events` ;
- toute conversation enfant lancée (observations
  `StartChildConversationObservation`), comme signal secondaire.

`verify_outcome()` n'accepte la mission que si **toutes** ces conditions sont
vraies :

- conversation `finished` et réponse coordinateur non vide ;
- **chacun des trois rôles** (développeur, analyste, vérificateur) a laissé une
  preuve **distincte** : une `TaskObservation` nommant son agent, d'état
  `completed`, sans erreur et avec un résultat **réel**. Une seule preuve ne
  suffit plus (l'ancien seuil « ≥ 1 enfant » est rejeté) ;

  > **Piège vérifié dans le code du SDK** (`openhands-tools/…/task/impl.py`) :
  > quand un sous-agent ne renvoie rien, le `TaskExecutor` substitue un texte
  > **non vide** — `"Task completed with no result."` (ou `"Task failed."`,
  > `"Failed to execute task: …"`). Un simple contrôle de longueur accepterait
  > donc un rôle qui n'a rien produit. Ces placeholders sont reconnus
  > (`_is_placeholder_result`, comparaison insensible à la casse/espaces) et
  > **jamais** comptés comme une preuve. Preuve : tests
  > `test_the_sdk_placeholder_is_not_a_proof`,
  > `test_the_sdk_failure_placeholder_is_not_a_proof`,
  > `test_collect_evidence_marks_the_placeholder`.
- la mission déclare un **critère d'acceptation** (section « Critère
  d'acceptation » du corps de l'issue). Le critère est *porté* dans le verdict,
  il n'est jamais *présumé satisfait* : un humain ou un vérificateur indépendant
  tranche.

Sinon :

- la mission reste `failed`/`resumable` et **hors** `processed` (reprise) ;
- **aucun** apprentissage `verified: true` n'est écrit ;
- `bus_bridge.record_outcome(success=True)` **refuse** d'écrire un succès sans
  verdict validé (point d'étranglement unique).

## 4. Sécurité — résultats mesurés (2026-11-15)

| Précondition | Résultat | Preuve |
|---|---|---|
| Révocation du jeton exposé | **NON VÉRIFIABLE ici** | GitHub n'expose pas la liste des jetons ; le jeton n'apparaît nulle part dans le dépôt (grep `ghp_`/`github_pat_`/`gho_` = 0) |
| Protection de `main` | **ABSENTE** | `GET /branches/main` → `protected: false` ; `GET /rulesets` → `[]` ; `GET /branches/main/protection` → 403 (le PAT n'a pas la permission *Administration*) |
| Permissions/hooks sous-agents | **OK (statique + comportement)** | `preflight.preflight()` → `[]` ; le garde bloque `git push origin main` (exit 2) et laisse passer `git status` (exit 0) ; `team_config.validate()` → 3 agents terminal-only |
| Garde-fou — contournements fermés | **OK** | garde `26579ceb` : bloque `git -C … push`, `git -c … commit`, `timeout 5 rm -rf`, `nice -n 10 rm`, `xargs -I{} rm`, `find … -delete/-exec` ; laisse passer `git -C … status`, `find … -print`, `timeout 5 ls` |
| Preuve runtime des restrictions | outil prêt | `verify_runtime.py` relit `base_state.json` et ré-exécute le garde |
| Missions autorisées seulement | OK | `policy.select_mission` ne prend que les issues label `tel99-mission` ; 1 issue (#70) |
| Quota | OK | `remaining=10`, `daily_limit=20`, reset `2026-11-16` |
| Coût | borné | plafond global 5 USD ; coordinateur 1 USD ; 0,25 USD/agent ; 30 itérations ; 10/agent |
| Modèle gratuit | OK | routeur : `openhands/deepseek-v4.1-flash` choisi ; `gpt-5.6` rejeté (`cost_tier=unknown`, règle no-spend) |
| Modèle gratuit — verrou de charge utile | OK (fail-closed) | `preflight.check_model(payload)` refuse tout modèle hors allowlist codée en dur `FREE_MODEL_IDS` / `FREE_MODEL_ALLOWLIST` ; `team_config.validate()` échoue si `TEL99_LLM_MODEL` pointe un modèle payant. Le serveur agent de ce sandbox est configuré sur **`gpt-5.6`** (`/api/settings`, coût inconnu) : sans ce contrôle, un run réel dépenserait. Preuves : `test_a_paid_or_unknown_model_is_refused`, `test_team_config_refuses_a_paid_model_override` |
| Verrou atomique KV | **CAS** (`?nx=true` / `?if_version=N`, 409) | `GET ?meta=true` → `version` ; `PUT` conditionnel ; en cas de 409, relecture et nouvelle tentative. Fail-closed si le backend n'expose pas de version |
| Capacité CAS du KV | **À VÉRIFIER au 1er run** | `?meta=true`/`if_version`/`nx=true` sont documentés pour le namespace **user-scoped** (`X-Session-API-Key` + `?automation_id=`, cf. skill `github`), **pas** pour le KV per-run (`Bearer $AUTOMATION_KV_TOKEN`). Nouvelle sonde `kv_meta_probe()` (rapportée par `--diagnose`) : si le KV per-run n'expose pas `version`, le verrou **échoue fermé** et aucun run réel ne démarre |
| Verrou expiré repris | OK | un verrou expiré est **écrasé par CAS** (`if_version`), jamais supprimé ; un verrou frais d'un autre run n'est jamais écrasé ; la libération écrit un **tombstone conditionnel** et ne touche jamais un verrou repris sous nos pieds |

### Démonstration du fail-closed

Tentative de mission réelle depuis cette session (`dry_run=false`) :

```
[journal] mission_selected issue=70 work_branch=agent/mission-70-...
[journal] abort reason="mission lock not acquired"
          detail="no atomic KV lock available: refusing to start a real mission"
```

Le système **s'arrête avant toute dépense** parce qu'il ne peut pas prouver qu'un
autre run ne travaille pas sur la même mission. C'est le comportement exigé.

## 5. Ce qui reste bloqué (interventions humaines nécessaires)

1. **Révoquer le jeton GitHub exposé** — action humaine ; impossible à vérifier ici.
2. **Protéger `main`** — `main` est actuellement **non protégée**. Le PAT n'a pas la
   permission *Administration* pour l'activer. Recommandation : exiger une PR + au
   moins 1 revue + les checks obligatoires sur `main`.
3. **Lancer la mission cloud réelle** — exige le sandbox (KV + agent-server). Ne peut
   pas être déclenchée depuis cette session. Deux voies :
   - déployer l'automation plugin-spec (nécessite votre accord explicite), ou
   - exécuter `orchestrator.py` dans le sandbox.
4. **Cron permanent** — **non activé**, conformément à la consigne.

### Faits cloud mesurés (2026-11-15, cette session)

- **0 automation déployée** : `GET /api/automation/v1` → `{"automations":[],"total":0}`.
- `AUTOMATION_KV_TOKEN` / `AUTOMATION_API_URL` **absents** hors exécution
  d'automation → le KV per-run n'est pas atteignable depuis une session normale.
- Le KV cloud joignable via `OPENHANDS_API_KEY` est **scopé par automation** :
  `/api/automation/v1/kv/{key}?automation_id=<uuid>` → `404 Automation not found`
  pour tout UUID inexistant (sans automation, aucun namespace n'existe).
- Agent-server local `localhost:60000` → **HTTP 401** (clé de session requise).
- `/api/quota/status` → `daily_limit: 20, used_today: 0, remaining: 20`
  (le quota se lit avec `Authorization: Bearer $OPENHANDS_API_KEY`).
- `/api/settings` → modèle configuré **`gpt-5.6`** (coût inconnu) → d'où le verrou
  no-spend `check_model` (cf. §4).
- **1 seul profil** LLM disponible : `default` (`agent_kind: openhands`) ; le profil
  gratuit `openhands_deepseek-v4.1-flash` n'existe pas dans ce sandbox.

## 6. Limites de coût

- Modèle : `openhands/deepseek-v4.1-flash` (gratuit) ; tout modèle non prouvé gratuit
  est refusé.
- Quota conversations gratuites : 20/jour ; l'orchestrateur exige ≥ 2 restantes.
- Plafonds déclarés : coordinateur 1 USD, 0,25 USD/sous-agent, 30 itérations,
  10 itérations/sous-agent ; plafond dur de la conversation entière : 5 USD.
- Verrou KV + `max_concurrent_missions=1` : une seule mission à la fois.

## 7. Passation

### Hermes (routeur / mémoire / coordination)

- **Connecté**, en processus : `protocol/adapters/hermes.py` réutilise
  `intelligence/{router,memory,improvement}`. Aucun routeur concurrent n'a été écrit.
- Point d'entrée : `handle(envelope)` répond à `route`/`recall` par une enveloppe
  `result` ; toute intention non implémentée est une **erreur explicite**, jamais un
  faux succès.

### Kilo Code (validation indépendante / tests)

- **NON connecté** — vérifié : aucun composant Kilo dans le dépôt. L'adaptateur
  `protocol/adapters/kilo.py` déclare honnêtement `connected=false`.
- Pour le connecter : un runner qui lit `bus/inbox/kilo/*.json`, écrit
  `bus/outbox/kilo/*.json`, et passe `KiloConformanceTests`.
- Preuves à lui transmettre : `docs/agents/INTEGRATION_PROTOCOL.md`, le schéma
  `scripts/agents/protocol/schema/agent-message-v1.schema.json`, et
  `tests/test_agent_protocol.py`.

### OpenHands (intégration / autonomie cloud)

- Orchestrateur : `scripts/agents/automation/orchestrator.py` (`--offline`, `--diagnose`).
- Bus : `scripts/agents/protocol/cli.py {actors,ledger,mission,dispatch,resume,status,validate,demo}`.
- Manifeste : `.plugin/plugin.json` (runner `script`, LLM gratuit, budget borné).

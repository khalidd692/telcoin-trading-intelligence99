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

## 4. Sécurité — résultats mesurés (2026-11-15)

| Précondition | Résultat | Preuve |
|---|---|---|
| Révocation du jeton exposé | **NON VÉRIFIABLE ici** | GitHub n'expose pas la liste des jetons ; le jeton n'apparaît nulle part dans le dépôt (grep `ghp_`/`github_pat_`/`gho_` = 0) |
| Protection de `main` | **ABSENTE** | `GET /branches/main` → `protected: false` ; `GET /rulesets` → `[]` ; `GET /branches/main/protection` → 403 (le PAT n'a pas la permission *Administration*) |
| Permissions/hooks sous-agents | **OK (statique + comportement)** | `preflight.preflight()` → `[]` ; le garde bloque `git push origin main` (exit 2) et laisse passer `git status` (exit 0) ; `team_config.validate()` → 3 agents terminal-only |
| Preuve runtime des restrictions | outil prêt | `verify_runtime.py` relit `base_state.json` et ré-exécute le garde |
| Missions autorisées seulement | OK | `policy.select_mission` ne prend que les issues label `tel99-mission` ; 1 issue (#70) |
| Quota | OK | `remaining=10`, `daily_limit=20`, reset `2026-11-16` |
| Coût | borné | plafond global 5 USD ; coordinateur 1 USD ; 0,25 USD/agent ; 30 itérations ; 10/agent |
| Modèle gratuit | OK | routeur : `openhands/deepseek-v4.1-flash` choisi ; `gpt-5.6` rejeté (`cost_tier=unknown`, règle no-spend) |
| Verrou atomique KV | **ABSENT hors sandbox** | `kv_lock_available: false` → l'orchestrateur **refuse** toute mission réelle (fail-closed) |

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

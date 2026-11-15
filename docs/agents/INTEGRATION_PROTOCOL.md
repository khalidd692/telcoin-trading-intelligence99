# Protocole d'échange inter-environnements (v1)

Contrat commun, **versionné**, pour qu'OpenHands, Hermes et Kilo échangent une
mission distribuée : identifiants, états, résultats, preuves, erreurs,
apprentissages validés et informations de reprise.

- Schéma publié : `scripts/agents/protocol/schema/agent-message-v1.schema.json`
  (JSON Schema 2020-12).
- Implémentation de référence (stdlib) : `scripts/agents/protocol/envelope.py`.
- Bus d'intégration : `scripts/agents/protocol/bus.py`.
- Adaptateurs : `scripts/agents/protocol/adapters/`.

## Enveloppe (une mission = une enveloppe)

| Champ | Rôle |
|---|---|
| `protocol` | `{name, version}` — un lecteur refuse une version majeure inconnue |
| `envelope_id` | id unique de l'enveloppe |
| `correlation_id` | id **partagé par toutes les enveloppes d'une même mission** |
| `parent_envelope_id` | enveloppe qui a engendré cette sous-mission |
| `origin` / `target` | acteurs (`environment`, `id`, `capabilities`, `connected`) |
| `kind` | `mission`, `sub_mission`, `result`, `evidence`, `error`, `learning`, `resume`, `heartbeat` |
| `state` | `queued`, `claimed`, `running`, `blocked`, `awaiting_human`, `done`, `failed`, `cancelled` |
| `mission` | id, titre, critères d'acceptation, étapes, `read_only`, branche de travail |
| `result` | `status` (`success`/`partial`/`failure`/`not_run`), résumé, artefacts, métriques |
| `evidence` | commande, code de sortie, empreinte de sortie, reproductible |
| `errors` | code, message, `retryable`, `attempt`, `max_attempts`, `fatal` |
| `learnings` | apprentissages validés (id, texte, `kind`, `verified`) |
| `resume` | `resumable`, point de contrôle, prochaine étape, étapes faites, tentatives |
| `budget` | itérations, budget, durée, quota au départ, `free_only` |

## Validation

`validate(dict)` renvoie la **liste des problèmes** (vide = valide) ; il ne lève
jamais sur une entrée mal formée. Une enveloppe illisible est un **échec dur**.
La validation est **fail-closed** : une mission en état terminal **doit** porter
un `result`, sinon elle est refusée.

```bash
python -m scripts.agents.protocol.cli validate --file bus/envelopes/<id>.json
```

## États et transitions

```
queued → running → (done | failed)
queued → blocked        (acteur assigné non connecté)
running → queued        (échec non fatal, sous le plafond de tentatives)
* → cancelled           (annulation explicite)
```

## Règles du bus

- **Un acteur non connecté n'est jamais sollicité en direct.** Une étape
  assignée à un acteur `connected: false` met la mission en `blocked` et
  enregistre `bus.actor_not_connected` — on ne fait pas semblant d'avoir livré.
- **Reprise** : chaque enveloppe et chaque état de mission sont écrits sur
  disque (`bus/missions/`, `bus/envelopes/`). Après une interruption, `resume()`
  repart à la **prochaine étape non terminée**.
- **Anti-boucle** : au plus `MAX_STEPS_PER_MISSION = 50` étapes et
  `MAX_ATTEMPTS_PER_STEP = 3` tentatives par étape.
- **Erreurs** : une erreur `fatal` échoue immédiatement ; sinon on retente
  jusqu'au plafond, puis on échoue avec la raison enregistrée.
- **Apprentissages** : un résultat validé est écrit en mémoire partagée via
  l'adaptateur Hermes (boucle exécution → connaissance).

## Qui est connecté (au 15/11/2026)

| Environnement | `connected` | Transport réel |
|---|---|---|
| OpenHands | **oui** | agent-server local (`:60000`) + API Cloud (quota, automations) |
| Hermes | **oui** | en processus : routeur, mémoire, boucle d'amélioration existants |
| Kilo | **non** | aucun composant dans le dépôt → **bus de fichiers uniquement** |

Un futur runner Kilo devient « connecté » quand il lit `bus/inbox/kilo/*.json`,
écrit `bus/outbox/kilo/*.json` et passe `KiloConformanceTests`
(`tests/test_agent_protocol.py`).

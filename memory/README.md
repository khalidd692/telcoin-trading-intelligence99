# Mémoire partagée des agents

Mémoire versionnée de la couche d'intelligence (`scripts/agents/intelligence/memory.py`).
Ce dossier est **commité** : chaque entrée est revue comme du code.

## Structure

- `common.json` — procédures communes à tous les projets.
- `projects/<projet>.json` — connaissances propres à un projet (isolation en code).
- `measured_quality.json` — taux de réussite mesurés par modèle, **relus par le routeur**.

## Format d'une entrée

Chaque entrée porte sa **provenance** : `source`, `commit`, `author`,
`created_at`, `verified`, `verified_by`, `version`, `confidence`, et
`supersedes` / `superseded_by` pour garder une correction auditable.

## Règles

- Un projet ne lit que ses entrées et `common` (jamais celles d'un autre projet).
- Re-enregistrer un `id` incrémente la version ; rien n'est écrasé silencieusement.
- Une entrée remplacée (`superseded_by`) est exclue des recherches par défaut.
- Aucun secret, aucune donnée personnelle, aucun ordre de trading dans la mémoire.

## Persistance entre deux runs (mémoire inter-missions)

Par défaut, `MemoryStore` écrit les fichiers JSON ci-dessus, **locaux au sandbox** :
ils ne survivent pas à la destruction du conteneur (`FileStore.durable()` vaut
`False`). Pour une mémoire réellement inter-runs, `MemoryStore` accepte un
`backend` — le même contrat `get(key)` / `put(key, value)` que
`scripts/agents/protocol/store.py` :

```python
from protocol.store import default_store
from intelligence import memory

store = memory.MemoryStore(backend=default_store())  # KV durable si dispo
```

`default_store()` renvoie le KV de l'automation (`KvStore`, `durable() == True`)
quand `AUTOMATION_API_URL` + `AUTOMATION_KV_TOKEN` sont injectés par le run, et
retombe sinon sur `FileStore`. La CLI (`cli.py remember/recall`) et l'adaptateur
Hermes choisissent ce backend automatiquement ; `--memory-root` / `root=` forcent
le stockage fichier. Les clés du backend vivent sous l'espace `memory/…`, distinct
de `missions/` et `envelopes/` du bus.

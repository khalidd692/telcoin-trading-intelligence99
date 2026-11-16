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

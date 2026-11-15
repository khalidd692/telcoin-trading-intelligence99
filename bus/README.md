# Bus d'agents TEL99

Répertoire d'échange **versionné** entre les environnements (OpenHands, Hermes,
Kilo). Chaque fichier est une enveloppe JSON du protocole v1
(voir `docs/agents/INTEGRATION_PROTOCOL.md`).

## Arborescence

- `envelopes/` — toutes les enveloppes échangées (mission, sous-mission,
  résultat, erreur, apprentissage, reprise).
- `missions/` — l'état persistant de chaque mission (étapes, tentatives,
  erreurs, résultat). C'est le substrat de la **reprise**.
- `inbox/kilo/` — enveloppes déposées **pour** Kilo (personne ne les consomme :
  Kilo n'est pas connecté).
- `outbox/kilo/` — enveloppes déposées **par** Kilo (vide aujourd'hui).

## Utilisation

```bash
python -m scripts.agents.protocol.cli actors
python -m scripts.agents.protocol.cli mission --title "Audit lecture seule"
python -m scripts.agents.protocol.cli dispatch --correlation-id <id>
python -m scripts.agents.protocol.cli resume   --correlation-id <id>
python -m scripts.agents.protocol.cli status   --correlation-id <id>
```

## Règles

- Aucun ordre financier, aucun merge, aucun déploiement, aucun secret.
- Une étape assignée à un acteur non connecté **bloque** la mission.
- Les fichiers d'exemple sont des **modèles** ; les vrais sont générés à
  l'exécution (et peuvent rester hors versionnage si volumineux).

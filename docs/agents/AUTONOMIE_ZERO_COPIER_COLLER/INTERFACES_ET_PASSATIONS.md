# CONTRATS DE PASSATION — COMMENT LES CHEFS SE PARLENT DIRECTEMENT

## But

Le propriétaire ne transporte plus de prompts, de comptes rendus ou de fichiers entre trois conversations ChatGPT et trois applications. Les agents utilisent le protocole du dépôt et les issues/PR GitHub pour toute passation. Ce fichier décrit le CONTRAT A LIVRER, pas une communication inter-environnements aujourd'hui prouvée.

## Un seul coordinateur de mission

Le système conserve une autorité unique de statut de mission et le verrou CAS existant, pas trois chefs pouvant se déclarer simultanément propriétaires. Les transactions sur labels GitHub ne sont pas atomiques. Une opération de création de fichier GitHub ne doit pas être présentée comme un lock CAS sans test. Le transport peut livrer un message plusieurs fois ; **le récepteur doit dédupliquer** sur un request_id stable.

### Enveloppe minimum

| Propriété | Contrat |
|---|---|
| schema_version | version du schéma existant, migrable |
| project_id | espace isolé; les règles TEL99 ne s'appliquent pas partout |
| mission_id / request_id | IDs stables à travers reprises et retries |
| correlation_id | rattache plusieurs étapes d'une mission |
| producer / target | rôle enregistré et acteur GitHub autorisé |
| type | REQUEST / ACK / RESULT / EVIDENCE / BLOCKED |
| issue_ref / approved_content_hash | mission et critères approuvés |
| attempt / expires_at | budget de reprises et TTL |
| work_branch / commit_sha | artefact testé et cible du verdict |
| acceptance_criteria | critères vérifiables, sans auto-déclaration |
| evidence_refs | logs/CI/diff/artefacts sous contrôle |
| security_scope | outils/branches/fichiers autorisés |
| status | état factuel ; aucune invention de PASS |

Réutiliser scripts/agents/protocol/envelope.py et les adaptateurs réels ; ne pas créer une version concurrente du bus si l'enveloppe existante répond à ces besoins.

## Parcours visé, sans copier-coller

1. Le propriétaire crée UNE mission via notre application ou une issue autorisée.
2. Le coordinateur attribue mission_id et critères. Hermes propose plan/Skills depuis une mémoire versionnée.
3. OpenHands exécute le travail cloud si pertinent ; Kilo récupère le travail Windows via une lecture sortante GitHub lorsqu'il est allumé.
4. Kilo ou un vérificateur déterministe exécute des tests réels. Il n'utilise pas le texte « tout est vert » du développeur comme preuve.
5. OpenHands agrège les preuves et fait MISSION_ACCEPTED ou BLOCKED/NEEDS_HUMAN.
6. Hermes écrit en mémoire uniquement une connaissance vérifiée, avec provenance, et récupérable en session neuve.
7. Une nouvelle tâche admissible est récupérée automatiquement par un exécuteur réellement connecté.
8. Le propriétaire voit le résultat et les demandes sensibles, pas une succession de prompts à transférer.

## Sécurité des permissions

Pour les premiers tests Kilo, préférer un token à accès unique dépôt permettant Issues lecture/écriture et lecture du code, pas Contents write global. Un PAT fine-grained n'est pas limité nativement à un répertoire de fichiers. L'exécution de code entrant nécessite un sandbox sans secrets. Aucune liaison entrante à ouvrir sur la box.

Le cloud ne doit jamais considérer les communications non signées ou non attribuées à un acteur autorisé comme des instructions exécutables. Les hashes d'approbation protègent contre l'édition silencieuse des missions. Une conversation 404/unknown nécessite décision de fail-close prudente.

## Test du pont

- Émettre REQUEST à un chef distant depuis le dépôt.
- Réception enregistrée sans action du propriétaire.
- ACK idempotent ; doublon n'entraîne qu'une exécution.
- RESULT avec SHA + preuves indépendantes et absence de fuite de secrets.
- PC éteint : WAITING_REMOTE, aucun faux FAILED ni coût ; reprise au retour.
- Pas de copie manuelle ou de message ChatGPT intermédiaire.
- La mission suivante est automatiquement choisie, sans redémarrage à la main du chef.

## Passage de relais en cas d'arrêt

A la fin de la fenêtre d'exécution, laisser sur GitHub un événement avec ce qu'il faut reprendre exactement ; si le consommateur ne fonctionne pas, marquer BLOCKED plutôt que demander au propriétaire de recopier ce document ailleurs. L'ultime objectif est de supprimer le besoin de dépendre d'OpenHands/Hermes/Kilo au runtime du moteur.

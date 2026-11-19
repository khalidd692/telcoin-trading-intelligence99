# Mémoire légère TEL99 — `.kilo/memory/`

Ce dossier stocke les connaissances vérifiées acquises au fil des missions, pour permettre leur récupération dans une nouvelle session sans recalcul ni redemande.

## Format d'une entrée (`knowledge.json`)

Chaque entrée comporte :
- `id` : identifiant unique de la forme `kilo-YYYYMMDD-NNN`
- `project` : nom du dépôt concerné
- `mission` : ID de la mission d'origine
- `source` : fichier ou commande qui prouve la connaissance
- `date` : horodatage ISO-8601 de l'enregistrement
- `evidence` : liste de preuves brutes (commandes + sorties)
- `validation_degree` : `proven` | `unproven` | `uncertain`
- `version` : numéro de version de l'entrée
- `contradictions` : liste des IDs d'entrées contredisant celle-ci

## Règles

- Une connaissance n'est enregistrée que si elle a été prouvée par une commande et sa sortie brute.
- Aucun secret, clé API, token ou donnée privée n'est stocké ici.
- Les entrées ne sont jamais supprimées ; on ajoute une nouvelle entrée avec `contradictions` pour corriger.
- Une entrée avec `validation_degree: "uncertain"` ne doit pas être utilisée comme preuve dans une mission ultérieure sans revérification.

## Utilisation

À l'ouverture d'une nouvelle session, lire `.kilo/memory/knowledge.json` pour retrouver le contexte vérifié. À la fin d'une mission, ajouter les connaissances nouvellement prouvées.

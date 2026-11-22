# Contrôles de sécurité et de qualité V1

## Instantanés du cockpit

```sh
python -B -m scripts.agents.cockpit --kit "$AtlasKit" --status "$Status" --plan "$Plan"
```

En mode kit, le dépôt et le projet viennent du profil validé. Le filtre conserve seulement les missions du projet. Un état global, un reçu ou un journal sans association explicite au projet ne renseigne pas l'activité du kit. Les fichiers en entrée sont des instantanés fournis par l'opérateur. Un lien GitHub affiché reste un lien vers sa source.

Le serveur filtre les champs, écarte les clés JSON dupliquées et les valeurs non finies. Les descriptions d'outils, erreurs libres, corps de rapports, chemins locaux et secrets de configuration ne sont pas publiés. Le DOM traite toutes les valeurs comme texte. Le projet n'ajoute aucune dépendance d'exécution tierce pour le cockpit, le kit ou le laboratoire. La lecture de données non approuvées ne charge ni outil ni commande.

## Vérifier une preuve native

Conserver le SHA-256 du `journal.json` dans un reçu séparé au moment de l'acceptation. La commande nécessite ce SHA de confiance et le kit correspondant.

```sh
python -B -m scripts.agents.project_kit verify --directory "$AtlasKit" \
  --mission-id "$MissionId" --journal-sha256 "$PinnedJournalSha"
```

`VERIFIED_ARTIFACTS` atteste que les éléments présents sont identiques aux octets couverts par le journal, qui enregistre une mission acceptée et ses contrôles. La commande vérifie le projet, la mission, les champs de succès, le contrat, les noms, la taille et les empreintes des artefacts avec le vérificateur du noyau. Elle ne relance pas les commandes contenues dans le journal. Pour reproduire la justesse métier d'un résultat, exécuter le banc de vérification dans l'environnement autorisé du projet.

```sh
python -B -m unittest tests.test_agent_platform_security tests.test_agent_cockpit tests.test_agent_project_kit
```

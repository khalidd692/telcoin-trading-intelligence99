# Kit de projet V1

Le kit prépare un deuxième projet avec les mêmes modules. Il applique des listes de rôles, de Skills et de modèles gratuits au planificateur existant. La référence du dépôt est descriptive. Elle ne donne aucun droit GitHub.

```json
{
  "schema_version": 1,
  "project": "atlas-lab",
  "repository": "example/atlas",
  "roles": ["quant", "development", "quality"],
  "skills": ["plan-verification"],
  "approved_models": ["openhands/deepseek-v4.1-flash"]
}
```

Enregistrer le profil localement dans un fichier JSON. Choisir une nouvelle destination privée, hors du répertoire de travail Git.

```sh
python -B -m scripts.agents.project_kit init --directory "$AtlasKit" --profile "$AtlasProfile"
python -B -m scripts.agents.project_kit status --directory "$AtlasKit"
python -B -m scripts.agents.project_kit plan --directory "$AtlasKit" --contract "$AtlasContract"
```

Le contrat vient de [la documentation du planificateur](AGENT_CAPABILITY_PLANNING.md). Son champ `project` doit correspondre au profil. Appliquer les mêmes étapes à un profil `boreal-lab` dans une autre destination. Le kit refuse un répertoire existant, un contrat hors projet et les champs supplémentaires, notamment une clé ou un endpoint.

Les chemins `state`, `memory` et `artifacts` sont des sous-répertoires propres au kit. `plan` réutilise le MemoryStore de ce kit. La commande prépare un plan et ne réserve aucun worker. Les accès GitHub et fournisseur restent côté opérateur.

```sh
python -B -m unittest tests.test_agent_project_kit
```

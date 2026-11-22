# Préparer une mission multi-rôle hors ligne

La commande `roles` expose les douze profils de `team_config.py`, dont trois actifs et neuf réservés. Une mission configure sa séquence de rôles et ses estimations. Les propriétés des profils, les outils et les permissions restent définis dans le catalogue du dépôt. Le plan ne produit aucune activation.

```sh
python -B -m scripts.agents.intelligence.cli roles
python -B -m scripts.agents.intelligence.cli plan --contract /chemin/vers/mission.json
```

Exemple minimal de contrat pour un projet fictif

```json
{
  "project": "atlas-lab",
  "mission_id": "catalogue-1",
  "approved_models": ["openhands/deepseek-v4.1-flash"],
  "budget": {
    "max_calls": 3,
    "quota_remaining": 15,
    "reserve": 12,
    "max_seconds": 30,
    "max_context_tokens": 4500
  },
  "steps": [
    {"role": "quant", "estimated_tokens": 1500, "estimated_seconds": 10},
    {"role": "development", "estimated_tokens": 1500, "estimated_seconds": 10},
    {"role": "quality", "estimated_tokens": 1500, "estimated_seconds": 10,
     "skills": ["plan-verification"]}
  ],
  "verification": {
    "budget": 5,
    "obligations": ["syntax", "behavior"],
    "mandatory": ["syntax"],
    "checks": [
      {"id": "syntax", "cost": 2, "covers": ["syntax"]},
      {"id": "combined", "cost": 3, "covers": ["syntax", "behavior"]},
      {"id": "behavior", "cost": 6, "covers": ["behavior"]}
    ]
  }
}
```

Le routeur existant filtre les suggestions selon le catalogue gratuit, l'autorisation, la taille du contexte et les outils. Le budget est évalué avant le Skill, avec un appel prévu par rôle et un plafond séparé pour le temps et le contexte. Le quota du fichier est une estimation opérateur pour la simulation. Le résultat conserve `PROVIDER_PENDING`, y compris quand le plan est prêt. Le routeur cloud refuse le contexte déclaré confidentiel.

Chaque transmission réutilise `Envelope` et porte un identifiant déterministe, le lien au parent et un plafond individuel. L'empreinte lie le contenu et le projet. Le plan est en lecture seule et ne publie aucun message. Les étapes des rôles réservés restent des propositions.

Le Skill `plan-verification` de #132–#134 est autorisé pour coordination, qualité ou évaluation. Un seul rôle porte son contrat. L'adaptateur lance uniquement le script livré avec le dépôt et transmet des données JSON. Les identifiants de contrôles ne sont pas des commandes. Dans l'exemple, les contrôles retenus coûtent 5 unités estimées au lieu de 11 pour le catalogue pertinent. Les preuves actuelles du Skill restent détaillées dans #132–#134.

Codes de sortie du planificateur

- `0` pour `PLANNED`.
- `2` pour un contrat invalide, un champ inconnu ou un Skill non autorisé.
- `3` pour `BLOCKED`. Le JSON indique notamment `QUOTA_UNKNOWN`, `QUOTA_RESERVE`, `CALL_BUDGET`, `TIME_BUDGET`, `CONTEXT_BUDGET`, `MODEL_UNAVAILABLE` ou `VERIFICATION_UNAVAILABLE`.

Le routeur CLI Codex reprend également le code et les tests de #131. Ses vérifications utilisent des fixtures. Le planificateur générique ne déclenche ni découverte réseau ni exécution de ce routeur.

```sh
python -B -m unittest tests.test_agent_capabilities tests.test_agent_intelligence \
  tests.test_codex_model_router tests.test_verification_plan_skill
```

# Contexte, cache et évaluation par projet

Ce lot prolonge le [planificateur multi-rôle](AGENT_CAPABILITY_PLANNING.md). Les exemples Atlas et Boréal utilisent les mêmes rôles, le même protocole et le même code d'exécution.

## Préparer deux projets isolés

Choisir un identifiant de projet et des répertoires privés d'état et de mémoire pour chaque dépôt. Utiliser `atlas-lab` et `boreal-lab` pour la recette fictive. Les clés de fournisseur éventuelles appartiennent à l'environnement du projet. Les contrats de planification ne prennent ni clés, ni endpoints, ni options d'outils.

Ajouter `"context":{"query":"index précis","limit":3}` au contrat de planification, puis utiliser une racine de mémoire explicite.

```sh
python -B -m scripts.agents.intelligence.cli --memory-root "$AtlasMemory" \
  plan --contract "$AtlasContract"
python -B -m scripts.agents.intelligence.cli --memory-root "$BorealMemory" \
  plan --contract "$BorealContract"
```

Le plan renvoie les identifiants, versions et empreintes des entrées pertinentes du projet, avec un plafond de huit références. Une entrée doit porter une vérification et son auteur de vérification. Les textes de mémoire restent hors des transmissions. Le stockage conserve le format précédent et sérialise les écritures concurrentes via le verrou de fichiers existant. Le partage démontré concerne des processus qui utilisent le même stockage local.

Le [noyau natif](../../scripts/agents/native/mission.py) accepte déjà une configuration `--project`, `--state`, `--memory`. Un résultat est réutilisable lorsque l'empreinte du contrat et les artefacts d'une réussite correspondent. Changer le prompt, le contrôle, la limite ou la liste d'artefacts exige un nouvel identifiant. Les anciens journaux sans empreinte restent consultables dans `status` et sont refusés comme preuves de cache. En réparation, le noyau transmet les noms des contrôles et un extrait plafonné à 4 000 caractères au total des seuls fichiers déclarés. Cet extrait constitue des données non fiables du modèle.

## Évaluer et faire relire une proposition

Créer un fichier JSON d'observations appariées. Chaque ligne comporte `task_id`, `model_id`, `success`, éventuellement `tokens`, `seconds`, `cost_units`, `provider_calls` et `evidence`. L'unité de coût doit être commune à l'ensemble des paires. Une mesure absente reste inconnue pour le coût et les appels. Les tests utilisent des unités synthétiques, sans facturation.

```sh
python -B -m scripts.agents.intelligence.cli improve \
  --baseline reference --candidate proposal --outcomes "$Outcomes" --measured-out "$Report"
python -B -m scripts.agents.intelligence.cli review-evaluation \
  --report "$Report" --sha256 "$ReviewedReportSha256"
```

Le rapport contient les observations et les écarts appariés de qualité, échecs, appels, jetons, temps et coût. À qualité égale, une proposition d'économie exige des coûts connus pour toutes les paires, aucun surcoût individuel et un nombre suffisant de gains. La relecture SHA recalcule les résultats. Elle ne publie aucune modification de politique ni de score de routage. Pour un changement, joindre le rapport et le SHA dans un brouillon de revue, mesurer les régressions, puis désigner un vérificateur distinct. En cas de régression, conserver la référence et écarter le brouillon. Les rapports d'évaluation restent auditables.

## Preuves déterministes

| Vérification | Résultat de la fixture |
| --- | --- |
| Recherche Atlas / Boréal | Une référence vérifiée pertinente dans chaque projet. Brouillons, entrées communes, textes libres et projet voisin absents. |
| Écritures concurrentes | 24 entrées et 24 lignes d'historique conservées. |
| Cache natif | Zéro appel lors d'une reprise identique. Changement du prompt ou du contrôle refusé avant tout deuxième appel. |
| Réparation | L'extrait contient le code de l'artefact déclaré. Une instruction hors artefact présente dans la réponse initiale ne figure plus dans le second prompt. |
| Évaluation appariée | Dix tâches, aucune perte de qualité, 30 → 20 unités et appels simulés dans la fixture. Coût inconnu et verdict falsifié refusés. |
| Portabilité | Même identifiant de mission dans Atlas et Boréal avec des artefacts, contrôles et verdicts distincts. |

```sh
python -B -m unittest tests.test_agent_capabilities tests.test_agent_intelligence \
  tests.test_agent_native tests.test_agent_handoff
```

Le fournisseur natif utilisé par ces tests est un fournisseur scripté ou une fixture HTTP locale. Les mesures live, les quotas fournisseurs et les identités natives restent `PROVIDER_PENDING` ou `WINDOWS_PENDING`.

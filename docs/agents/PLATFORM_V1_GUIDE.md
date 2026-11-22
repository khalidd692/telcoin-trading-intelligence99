# Guide de la plateforme d'agents V1

La V1 prépare et vérifie des missions, puis affiche les résultats exportés dans un cockpit français. Son kit isole l'état et la mémoire pour chaque projet. Le laboratoire mesure les changements avec des tâches fixes. La démonstration utilise un travailleur scripté, des contrôles distincts et des fichiers locaux.

## Installation

Depuis le checkout de la chaîne V1, utiliser Python 3.12 ou une version compatible. Le cockpit, le kit et le laboratoire utilisent la bibliothèque standard. [Configurer un deuxième dépôt et son espace privé](PROJECT_KIT_V1.md).

```sh
python -B -m unittest tests.test_agent_cockpit tests.test_agent_project_kit \
  tests.test_agent_evaluation_lab tests.test_agent_platform_security tests.test_agent_platform_demo
```

## Démonstration guidée

```sh
DemoRoot=$(mktemp -d)
Kit="$DemoRoot/atlas"
python -B -m scripts.agents.platform_demo --directory "$Kit"
python -B -m scripts.agents.cockpit --kit "$Kit" \
  --status "$Kit/status.json" --plan "$Kit/plan.json"
```

1. Ouvrir `http://127.0.0.1:8787/` sur la machine qui exécute le serveur. Le cockpit annonce « données simulées ». En vue étroite, les sections se consultent en défilement vertical.
2. Ouvrir la mission `demo-double` et son empreinte. Le programme livré double un entier. Un processus Python distinct a contrôlé le résultat pour l'entrée 7.
3. Ouvrir Rôles. Analyse, développement et vérification sont prévus par le plan. Le catalogue comporte douze profils. Aucun rôle n'est démarré par la consultation.
4. Examiner les estimations. La démonstration a consommé une réponse scriptée. Le quota d'un fournisseur externe et les PR apparaissent comme inconnus.
5. Pour reproduire le contrôle d'intégrité, relever le SHA rendu par `platform_demo` et suivre la commande [Vérifier une preuve native](PLATFORM_SECURITY_V1.md#vérifier-une-preuve-native). Les données et preuves restent dans le nouveau kit.

Pour un second exemple, utiliser une nouvelle destination et ajouter `--project boreal-lab --repository example/boreal` à la commande de démonstration. Les deux profils partagent le code de la plateforme et conservent des états séparés.

## Usage courant

- [Consulter le cockpit](COCKPIT_MOBILE_V1.md) à partir des sorties locales de statut, de plan et des reçus GitHub déjà exportés.
- [Préparer une mission](AGENT_CAPABILITY_PLANNING.md) et examiner les coûts estimés, les Skills autorisés et les transmissions prévues.
- [Comparer des résultats](EVALUATION_LAB_V1.md) et isoler le gain obtenu du coût en appels et en contexte.
- [Contrôler une preuve](PLATFORM_SECURITY_V1.md) et conserver le SHA du journal dans le reçu de revue.

La V1 n'expose pas d'API de commande, de déploiement ou de connexion fournisseur. Le cockpit écoute seulement sur la boucle locale. Le suivi sur appareil physique, les modèles réellement appelés et l'activité native des douze agents restent hors de la démonstration.

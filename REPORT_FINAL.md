# TEL99 — Rapport de livraison du 25 novembre 2026

Base vérifiée `328c180adb5fd45a434c85a20c21dac9e8721776`, branche
`agents/tel99-antigravity-v2-20261124`, [PR brouillon #208](https://github.com/khalidd692/telcoin-trading-intelligence99/pull/208).

## PROVEN

- Le routeur trie tous les candidats admissibles par score décroissant. L’effort élevé reste réservé aux tâches difficiles. Les tests discriminants donnent la victoire tantôt à Hydrogen Medium, tantôt à Neon High selon la qualité mesurée. Ils ont échoué avant la correction. Les hausses de prior non mesurées du dernier commit ont été retirées. Neon Medium réutilise le prior de référence de Hydrogen Medium.
- L’endpoint `/health` répond 200 en loopback et rejette un hôte externe avec 403 sur le serveur de test. Il indique que le processus HTTP répond. À 00:42 UTC, le processus déjà en écoute sur 8765 servait encore `/` avec 200 et `/health` avec 404. Il faut démarrer le cockpit corrigé lors d’une fenêtre où le port est libre.
- Les transactions de bail attendent brièvement une contention du verrou système avant de relire le CAS. Le test concurrent Windows vérifie un détenteur, un conflit et un événement de passation. Les écritures restent sérialisées.
- 90 tests ciblés passés le 25 novembre, dont le catalogue des 12 rôles, les permissions des briefs, les contrôles HTTP, les limites de routage, le CAS et la reprise. `render_agents.py --check` confirme que les 13 fichiers de définition générés correspondent à `team_config.py`.
- Deux interruptions réelles de processus Python dans des répertoires temporaires avec un worker de test. Sortie forcée 55 après reçu durable pour `isolated-crash-receipt` et pendant l’exécution pour `isolated-crash-uncertain`. Deux redémarrages par scénario. Respectivement `WORKER_EXITED → ACCEPTED` et `RUNNING → AWAITING_HUMAN`. Une seule invocation du worker par mission, comptée sur disque.
- Diagnostic à 00:38:35 UTC. Accès GitHub propriétaire avec permission de push, Ollama local et image Docker épinglée disponibles, 5 422 Mio de RAM libre au moment de la mesure.
- Deux propositions de recette publiées, [A #210](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/210) puis [B #209](https://github.com/khalidd692/telcoin-trading-intelligence99/issues/209) dans l’ordre fonctionnel.

## PARTIAL

- Les rôles sont sélectionnables et leurs briefs sont contrôlés hors ligne. La mobilisation des 12 rôles au travers des applications et le passage réel IDE → CLI → Codex restent à observer. La présence des exécutables et la concurrence entre processus de test sont des preuves distinctes.
- Le routeur connaît les profils Neon Medium pour l’orchestration et Hydrogen Medium pour l’exécution. Leur disponibilité effective et leur quota sur l’abonnement Antigravity restent à mesurer. La campagne GitHub actuelle admet seulement les contrats Ollama locaux. La préférence Antigravity demeure conditionnée à l’autorisation d’abonnement et aux garde-fous de confidentialité.
- La suite hors ligne couvre l’enchaînement, la réparation, la mémoire, les indisponibilités et le refus après quota. La preuve d’interruption utilise un worker synthétique. Il manque une panne contrôlée sur une campagne réelle avec mémoire et publication GitHub.

## BLOCKED

- Les propositions #210 et #209 précèdent un contrôleur signé. Le récepteur exige un contrôleur propriétaire, son commentaire de mandat `tel99-code-campaign/v1`, une base dédiée épinglée et deux issues **créées après ce mandat**, chacune avec approbation propriétaire `tel99-code-mission/v1`. Les deux propositions servent de spécifications. La recette exécutable doit reprendre ces spécifications dans des tickets postérieurs au mandat. Voir [le protocole existant](docs/agents/TEL99_OWNER_AUTOFEED_20261124.md).
- L’observation de la coordination native et de la boucle GitHub de bout en bout dépend d’une exécution sur ces nouveaux contrats. L’intégration SDK reste à valider dès qu’une interface utilisable est disponible.

## NOT_EXECUTED

- Campagne live sur les deux nouvelles spécifications, résultats GitHub autonomes, validation multi-applications et endurance de 60 minutes. Les prérequis de l’endurance restent ouverts.
- La CI verte observée sur `328c180a` concerne ce SHA. Les vérifications du commit de livraison sont à lire sur la PR.

## Usage quotidien sous PowerShell

Depuis la racine du worktree, définir le lanceur et le Python observé sur ce PC. Le lanceur lit le dossier d’état historique dans sa configuration.

```powershell
$tel99 = '.\scripts\agents\automation\tel99-agent.ps1'
$env:TEL99_PYTHON = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
pwsh -NoProfile -File $tel99 -Mode Preflight -AutoFeed
pwsh -NoProfile -File $tel99 -Mode Run -AutoFeed -IsolateBlocked -ExitWhenDone -Minutes 60 -PollInterval 30
```

Démarrer `Run` seulement pour un nouveau mandat admissible, après contrôle des contrôleurs retournés par le pré-vol. Pour la recette de ce mandat, exclure les tickets #205, #206 et #207 de tout lancement. L’option `-ExitWhenDone` borne la session à la fin du travail admissible.

Dans une autre console, définir les deux mêmes variables puis superviser ou demander l’arrêt.

```powershell
pwsh -NoProfile -File $tel99 -Mode Status
pwsh -NoProfile -File $tel99 -Mode Leases
pwsh -NoProfile -File $tel99 -Mode Cockpit -Port 8765
# Dans une autre console une fois le cockpit démarré
Invoke-RestMethod http://127.0.0.1:8765/health
pwsh -NoProfile -File $tel99 -Mode Stop
pwsh -NoProfile -File $tel99 -Mode Recover
```

Ouvrir le cockpit à l’adresse `http://127.0.0.1:8765/`. Arrêter son serveur avec Ctrl+C dans sa propre console. Après un arrêt volontaire, utiliser `Recover -ClearStop` uniquement après avoir vérifié les baux et les checkpoints. Conserver le même dossier d’état en exploitation.

## Reproduire les tests

```powershell
& $env:TEL99_PYTHON -B -m unittest tests.test_provider_router tests.test_autonomous_platform_e2e tests.test_antigravity_ide_integration tests.test_autonomy_runtime tests.test_github_owner_feed tests.test_github_multi_mandate_session
& $env:TEL99_PYTHON -B scripts/agents/render_agents.py --check
git diff --check
```

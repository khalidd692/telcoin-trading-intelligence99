# Suivre une campagne GitHub TEL99 sur Windows

Depuis le worktree contenant le cockpit, ouvrir PowerShell 7 et choisir le dossier d’état de la campagne.

```powershell
$tel99CampaignState = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_GITHUB_CODE_STATE_20261123"
python -B -m scripts.agents.night_lab_20261123 serve --github-state $tel99CampaignState --port 8791
```

Ouvrir [http://127.0.0.1:8791/](http://127.0.0.1:8791/). Le serveur actualise la projection toutes les quatre secondes. Le registre du 23 novembre donne accès aux missions déjà livrées et à leurs liens GitHub. Ce démarrage du cockpit est en lecture seule et préserve les octets du registre. Le serveur écoute uniquement sur le PC qui détient l’état. Un navigateur à fenêtre étroite dispose de la même vue.

## Observer une nouvelle campagne

Pointer le cockpit vers le dossier d’état dédié aux nouvelles missions autorisées. Le dossier peut encore être absent. Démarrer la campagne dans un deuxième terminal avec le lanceur GitHub ou le superviseur existant, en lui indiquant le même dossier et le nouveau mandat. Le cockpit projette la file à partir de l’admission CAS et distingue la vérification locale de la livraison GitHub. Une mission acceptée localement reste en publication tant que la PR et les reçus concordants manquent.

Les sections de mission montrent le fichier et la fonction approuvés, la tentative, le checkpoint horodaté, les contrôles Docker et les liens vers les reçus. Chaque fiche d’agent présente son périmètre, son moteur et les reçus associés aux missions. Les données de génération et de vérification apparaissent quand elles sont inscrites dans le checkpoint. Les champs privés du ledger restent sur le disque.

Un heartbeat de plus de 30 secondes, une date invalide ou un processus introuvable retire le statut actif. Les deux rôles Ollama travaillent dans le même worker. En l’absence de télémétrie individuelle, le cockpit affiche l’étape commune et distingue leurs contributions par les reçus du worker. La vérification est attribuée à Docker dès qu’un heartbeat de vérification corrélé est disponible. Les rôles dont aucun exécuteur ou reçu n’est disponible apparaissent indisponibles.

## Demander un arrêt propre

Pour une campagne **en cours** que l’opérateur souhaite piloter, démarrer le cockpit avec l’option `--allow-stop`. Le terminal affiche un code propre au processus du cockpit. Dans la section **Pilotage**, ouvrir **Demander un arrêt propre**, saisir ce code puis cocher la confirmation. Le serveur local crée le même marqueur `stop.request` que l’action d’arrêt du superviseur. Il indique la demande jusqu’à confirmation de l’arrêt par le heartbeat. L’opérateur examine ensuite les checkpoints avant toute reprise avec le lanceur dédié.

Pour fermer uniquement le cockpit, presser `Ctrl+C` dans son terminal.

## Tests

```powershell
python -B -m unittest -v tests.test_night_lab tests.test_night_lab_github_cockpit
node --check scripts/agents/night_lab_ui/dashboard.js
```

Le scénario navigateur est exécuté lorsque Chromium et Playwright sont disponibles. Les tests HTTP utilisent un registre temporaire et vérifient notamment la fraîcheur, les liens corrélés, l’absence d’écriture par la lecture et le refus d’un arrêt sans confirmation.

# Windows / PowerShell — reprise sans appel modèle

## Périmètre
Le chemin le plus court à viser après récupération est Linux dans WSL2 ou Docker Desktop, piloté par PowerShell. Aucune commande A→B précise ne peut être attestée sans a5112413 et ses fichiers. Le présent dossier est exécutable pour diagnostiquer/récupérer, pas pour reproduire une démonstration perdue. Le socle main et PR #158 ne sont pas des substituts.

## Checkout documentaire neuf
Exécuter dans une console PowerShell utilisateur ; Git doit être installé. Aucun worktree existant n'est changé.
~~~powershell
$ErrorActionPreference = 'Stop'
$relayDir = Join-Path $env:TEMP ('tel99-relay-' + [guid]::NewGuid().ToString('N'))
git clone --single-branch --branch 'handoff/a5112413-source-recovery-20261123' 'https://github.com/khalidd692/telcoin-trading-intelligence99.git' "$relayDir"
if ($LASTEXITCODE -ne 0) { throw 'Clone échoué ; vérifier accès GitHub' }
git -C "$relayDir" rev-parse HEAD
& (Join-Path "$relayDir" 'docs/agents/RELAIS_A5112413_20261123/REPRISE.ps1') -Action Diagnose -Repository "$relayDir"
# Sortie 2 attendue actuellement : source absente. Ne pas lancer RUN.
~~~
Lancer avec powershell.exe -NoProfile -File ou pwsh -NoProfile -File selon l'installation. Le script ne requiert que PowerShell >= 5.1 et Git. Il vérifie les empreintes de tous les fichiers du dossier avant les opérations Git. SHA256SUMS.json n'est pas une signature : comparer le SHA du commit de relais au reçu GitHub.

## Inventaire sans installation ni réseau modèle
~~~powershell
$PSVersionTable.PSVersion
Get-Command git,gh,py,python,pwsh,node,npm,docker,wsl,'llama-cli','llama-server' -ErrorAction SilentlyContinue | Select-Object Name,Source
git --version
gh --version
py -0p
$managedPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (Test-Path -LiteralPath "$managedPython") { & "$managedPython" --version }
wsl --list --verbose
wsl --status
docker --host 'npipe:////./pipe/docker_engine' version
docker --host 'npipe:////./pipe/docker_engine' image ls --digests
~~~
Les erreurs d'absence d'outil ci-dessus sont des diagnostics, pas des demandes d'installation automatique. Le PC indiqué par le mandat est Ryzen 7 5700U, 16 Go, sans GPU dédié : viser CPU, une seule inférence à la fois. GGUF exact/quantification, contexte, threads, délai et RAM doivent venir de la configuration d'origine, pas d'une supposition « Qwen ».

## Dépendances
- Récupération : Git et PowerShell 5.1+ ; GitHub CLI est optionnel si Git HTTPS fonctionne.
- Diagnostic du socle publié : Python sélectionné explicitement par -Python ; son diagnostic utilise la bibliothèque standard. Ce n'est pas le mode CODE manquant.
- Reproduction : versions Python/Node, paquets pip/npm, image Docker/digest, build llama.cpp, GGUF et SHA256 **inconnus** jusqu'à l'export. Ne pas installer de liste inventée ni de modèle de remplacement.
- Docker CLI détecté ici mais moteur arrêté ; WSL observé = docker-desktop seulement. Ne pas exécuter de shell utilisateur dans cette distribution interne.
- Aucun téléchargement, achat, pull d'image, activation WSL ni appel de fournisseur effectué pendant ce relais. Installation éventuelle explicite après lecture des verrous d'origine.
- Pour une machine neuve, identifier les paquets disponibles sans installer : winget search --id Git.Git --exact ; winget search --id Microsoft.PowerShell --exact ; winget search --id Docker.DockerDesktop --exact. Les versions et exigences doivent être vérifiées chez l'éditeur avant installation ; ne pas supposer leur compatibilité.

## Import du bundle d'origine (après récupération)
Exiger un bundle complet, son empreinte SHA256 et le SHA complet du commit transmis indépendamment. Le script ne choisit pas de modèle et n'exécute pas le code importé.
~~~powershell
$bundlePath = 'C:\chemin\export-origine\a5112413.bundle'
$sourceFullSha = 'REMPLACER_PAR_SHA_GIT_COMPLET_A5112413'
$bundleSha256 = 'REMPLACER_PAR_SHA256_BUNDLE'
$destination = Join-Path $env:TEMP ('tel99-a5112413-' + [guid]::NewGuid().ToString('N'))
& "$relayDir\docs\agents\RELAIS_A5112413_20261123\REPRISE.ps1" -Action ImportBundle -BundlePath "$bundlePath" -ExpectedSourceSha "$sourceFullSha" -ExpectedBundleSha256 "$bundleSha256" -Destination "$destination"
~~~
Le script refuse un répertoire déjà existant. Il ne supprime rien en cas d'échec. Lire son reçu et le code source avant toute commande --help ou test : même un --help Python peut exécuter du code.

## Lancement / arrêt / reprise A→B : gate
BLOQUÉ : pas de chemin CLI, fichier CODE, hash d'approbation ni config disponibles pour a5112413. Ne pas ajouter --local-code au lanceur Windows historique : son paramétrage inspecté ne le déclare pas.
Après export : relever la commande originale et la transposer **littéralement** depuis le guide livré avec a5112413 ; confirmer --local-code dans le code sans exécuter, établir les volumes/UID/permissions et le confinement. Ne démarrer qu'un intégrateur.
Pour STOP : utiliser la commande originale récupérée ; préserver marker, registre, ledger, mémoire et reçus. Ne jamais supprimer un claim pour « débloquer ». Si résultat incertain : AWAITING_HUMAN. Ne déplacer un marker STOP qu'après inspection et selon le protocole réel du runtime.
Pour les journaux : chemins exacts attendus de l'export ; le socle historique écrit sous .tel99-automation-state, mais cela ne prouve pas le chemin du démonstrateur Linux.

## Preuve attendue du prochain atelier autorisé
SOURCE_SHA et parent/base, hash GGUF/build/config non secrète, commandes exactes et exit codes, durées UTC/durée monotone, contrat et empreinte approuvée, rouge sur base et vert sur candidats A/B, patch/candidat/SHA256, reçus indépendants et écriture mémoire, B réclamée après acceptation A, STOP/reprise puis replay sans nouvelle inférence, compte d'appels et coût API nul observés. Aucune intervention humaine entre A et B. Archiver avant relance et conserver l'état historique.
Cette mission n'autorise aucune nouvelle démonstration : ce sont les critères à utiliser lors du prochain atelier expressément autorisé, après récupération. Tant que ces preuves manquent : NON TESTÉ Windows.

# TEL99 — Ollama natif, sans Kilo

Branche d'integration de la PR #165. Elle reutilise le superviseur Windows,
le registre de missions scelle, les checkpoints, le verificateur Docker et la
memoire de preuves. Aucun logiciel supplementaire ni service payant.

Etat : code et tests publies; la chaine du superviseur n'est PAS encore
revalidee sur Windows. Ne pas annoncer une autonomie prouvee avant la campagne.

## Installer la branche dans un worktree separe

Depuis PowerShell sur le poste Windows, avec Docker, Python, PowerShell 7
et Ollama deja installes :

~~~powershell
$repo = "$HOME\Desktop\telcoin-trading-intelligence99"
$branch = "agents/tel99-ollama-native-route-20261123"
$checkout = "$HOME\Desktop\TEL99_OLLAMA_NATIVE_20261123"
git -C $repo fetch origin "refs/heads/$branch"
if ($LASTEXITCODE -ne 0) { throw "Fetch impossible" }
git -C $repo worktree add --detach $checkout FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw "Worktree impossible" }
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Test
~~~

Le mode Test ne genere aucune proposition de code. Il doit reussir
avant toute campagne.

## Campagne Gemma 4 — cinq missions epinglees

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Gemma
~~~

Ce mode scelle un registre NEUF et lance cinq missions approuvees
sur gemma4:e4b-tel99-8k via http://127.0.0.1:11434/api/generate.
L'ancien registre et les anciens checkpoints restent intacts.
Limite une heure; aucun push ni merge; aucun ordre de trading.
Garder la console ouverte pendant le test.
Deux propositions maximum par mission, puis verdict Docker independant.

## Nouvelle campagne Qwen2.5-Coder 7B (comparaison indépendante)

Après les trois ACCEPTED et deux BLOCKED de Gemma (deuxième campagne),
tester le modèle de programmation spécialisé sans modifier les anciens
checkpoints, sans changer les tests et sans assouplir la sécurité :

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Coder
~~~

Le lanceur scelle cinq nouvelles identités et cinq contrats fixes sur
qwen2.5-coder:7b. Le superviseur, les vérifications Docker et les journaux
restent les mêmes. Les preuves anciennes sont conservées.
Il est également possible d'exécuter une campagne séparée avec
-Mode Qwen35, mais elle n'est pas encore validée sur le PC.

Attention : la mission Gemma 04 a deux refus de tests Docker.
La mission Gemma 05 a un refus Docker suivi d'un refus de forme du
correctif. Le routeur strict n'autorise donc pas encore l'escalade
automatique de la 05 : ne pas contourner la règle de deux échecs Docker.

## Routeur trois modeles — apres validation du mode Gemma

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Route
~~~

Les candidats sont gemma4:e4b-tel99-8k, qwen2.5-coder:7b et
qwen3.5:9b-q4_K_M. Le routeur selectionne un modele par mission
et lie son choix au checkpoint. Une seule mission successeur,
explicitement autorisee, est admissible apres deux rejets Docker,
et seulement si un autre modele est pret.
Les modeles sont utilises successivement, avec keep_alive=0s.
Les scores qualite du catalogue sont des priorites provisoires,
PAS des taux de reussite mesures.

## Resultats, arret et reprise

Les dossiers TEL99_AUTONOMIE_NUIT_* du Bureau contiennent MISSIONS.json,
PREUVES.json, journaux et diff verifies. Le cockpit n'est disponible que
pendant la campagne sur http://127.0.0.1:8791/.

Pour stopper proprement, depuis une seconde console PowerShell :

~~~powershell
$session = "CHEMIN_EXACT_DU_DOSSIER_A_ARRETER"
python -B "$checkout\scripts\agents\night_lab_20261123.py" stop --session $session
~~~

Ne pas supprimer les checkpoints existants. Les missions RUNNING
interrompues ne sont pas rejouees aveuglement : reconciliation humaine
necessaire. Pour reprendre, utiliser le meme worktree, le registre
initial, son SHA-256 et le dossier de session de la campagne.

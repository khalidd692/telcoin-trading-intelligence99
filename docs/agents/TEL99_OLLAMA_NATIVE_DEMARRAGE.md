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

## Selection par preuves : une seule campagne avec deux modeles

Les deux campagnes Windows achevees le 23 novembre 2026 montrent une
couverture complementaire : Gemma a valide 01/02/03, Qwen Coder a valide
02/04/05. Le mode Evidence ne se contente PAS de lire les statuts affiches :
il reverifie les deux sessions, leurs registres SHA-256, les contrats
independants, les reçus workers, les correctifs, les tests Docker et les
preuves de chaque mission via compare_local_code. Il accepte deux checkouts
HEAD differents UNIQUEMENT si les cinq sources et tests epingles sont
strictement les memes. Le comparateur historique reste inchangé.

Il prepare alors cinq NOUVEAUX contrats fixes, chacun liant le modele
ayant effectivement reussi son test Docker, et scelle les autorisations.
La selection choisit une reussite en moins de tentatives, puis le temps
de generation observe quand disponible. Elle refuse le lancement si une
seule mission n'a pas de reussite verifiable, si les preuves divergent,
ou si une source historique a ete modifiee.

Lancer depuis la nouvelle branche de travail, apres tests :

~~~powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "$checkout\scripts\agents\automation\run_ollama_native.ps1" -Mode Evidence
~~~

Le lanceur utilise les deux dossiers de preuves du 23 novembre et leurs
empreintes SHA-256 connues. Il affiche la selection fonction -> modele
avant le demarrage. Le meme superviseur Night Lab executera les cinq
missions a la suite ; Docker verifiera chaque proposition. Une nouvelle
session avec checkpoints et preuves est creee ; les preuves historiques
restent intouchables.

Cette campagne teste la reutilisation pratique de resultats fiables pour
une file connue. Elle ne prouve pas la generalisation du routage a de
nouvelles tâches ni le changement dynamique de modele pendant une mission.
Aucune fusion Git, aucune publication de correctifs et aucun trading.

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

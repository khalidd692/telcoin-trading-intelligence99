# Intégration P0 des agents TEL99

**État de la recette native** `WINDOWS_LIVE_PENDING`

## Socle intégré

La branche d’intégration part de #144 (`d57e87a8`), qui contient #128 et le superviseur #124. Les branches #141 et #144 ont pour ancêtre commun `49827e20`. L’intégration reprend le contenu final de #141 et les ajouts de #145 et #146. Le chemin historique de #142 reste dans sa branche. Son récepteur, son test destructeur et l’ancien runner actif de #140 ne font pas partie de cette livraison.

Le lanceur Kilo est [`start-agents.ps1`](../../start-agents.ps1). Avec une issue, il appelle `kilo_github_adapter.py`. Avec un registre local, il appelle `autonomy_runtime.py`. Hermes utilise `hermes_github_adapter.py` avec le même `Runtime` et un état distinct. Garder un état dédié par recette et par transport. Le marqueur `stop.request` s’applique à l’état choisi. Le lanceur et les deux workers honorent aussi le marqueur historique `.kilo/STOP` du worktree actif. Un reçu worker durable permet de reprendre la vérification. Un checkpoint RUNNING ambigu exige une réconciliation.

## Cinq couches et sept capacités

| Couche | État et preuve |
| --- | --- |
| Prompt | **INTÉGRÉ / TESTÉ**. Le routeur GitHub limite le contrat aux rôles et à la sortie synthétique explicitement approuvés. Les consignes et identités chargées dans Agent Manager restent **BLOCKED** jusqu’à l’inspection des sessions natives. |
| Context | **INTÉGRÉ / TESTÉ**. Inbox, empreinte de contrat, reçus et MemoryStore conservent provenance et isolation. La relecture sélective est disponible dans le noyau natif. La synchronisation entre ateliers reste à démontrer. |
| Harness | **INTÉGRÉ / TESTÉ**. Verrou, CAS, STOP, journaux, options de coût et vérificateurs en sous-processus. Deux worktrees temporaires de code exécutent des contrôles déterministes. Les outils d’édition du développeur natif et leur isolation restent **BLOCKED**. |
| Loop | **INTÉGRÉ / TESTÉ**. Accords, ACK, exécution, vérification, résultat et reprise. Le noyau natif existant couvre les réparations bornées et son cache. Un reçu ambigu suspend l’effet externe. |
| Graph | **INTÉGRÉ / TESTÉ**. Dépendances A→B, refus des cycles avant claim, périmètre d’issue et réconciliation des doubles publications. La revue d’une PR de développement produite en autonomie reste **BLOCKED**. |

| Capacité | État et preuve |
| --- | --- |
| Auto-amélioration contrôlée | **EXISTE / TESTÉ**. `intelligence.improvement` compare des paires d’évaluations, conserve les décisions et propose une amélioration mesurée. L’approbation d’une promotion reste humaine. |
| Routage économique | **EXISTE / TESTÉ**. `intelligence.router` tient compte des compétences, de la difficulté, de la disponibilité et du quota. Les scores hors plage ou non numériques sont ignorés. Les chemins Kilo et Hermes conservent leur modèle épinglé et leurs contrôles de coût. La sélection automatique entre fournisseurs vérifiés en temps réel reste **BLOCKED**. |
| Collaboration | **INTÉGRÉ / TESTÉ avec fixtures**. Analyste puis développeur, vérificateur indépendant en processus fixe. Trois profils actifs sont définis et neuf profils sont réservés. La délégation réelle à une session spécialisée et son ACK natif restent **BLOCKED**. |
| Mémoire partagée | **INTÉGRÉ / TESTÉ** sur un même état. Provenance du vérificateur, versionnement, recherche, isolation et préservation d’un fichier illisible. Partage entre machines **BLOCKED**. |
| Skills et outils | **EXISTE / TESTÉ** pour le garde d’outils et le rendu des définitions. Chargement, permissions et usages réels des Skills Kilo **BLOCKED** jusqu’à contrôle du runtime Windows. |
| Planification sous budget | **EXISTE / INTÉGRÉ / TESTÉ**. Le graphe, le quota, l’échéance, l’état durable et le cache du noyau natif limitent les répétitions. |
| Réutilisation multi-projets | **EXISTE / TESTÉ** dans le noyau natif et la mémoire. L’admission GitHub de cette livraison reste épinglée à TEL99 et aux contrats synthétiques. Un deuxième dépôt nécessitera sa propre autorisation et une validation des barrières. |

## Rejouer les preuves hors ligne

```powershell
$env:TEL99_LIVE_PROBES = '0'
python -B -m unittest discover -s tests -q
python -B -m unittest discover -s collector -p 'test_*.py' -q
pwsh -NoProfile -File tests/test_start_agents.ps1
node tests/test_dashboard.js
node tests/test_realtime.js
python -B scripts/agents/render_agents.py --check
```

Le test `test_dependency_waits_for_actual_draft_publisher_and_receipt` exerce le vrai récepteur, le superviseur, le vérificateur et le code de publication avec réponses GitHub et fournisseur simulés. Le worker de fixture modifie un module Python dans deux worktrees Git temporaires. Un autre processus observe successivement les valeurs 4 et 8 et chaque changement possède son propre commit local. Le publieur appelle l’API simulée pour deux brouillons d’artefact texte. Les compteurs et les commits restent stables au redémarrage. Le test séparé des processus contrôle STOP, concurrence et crash. Aucun de ces essais ne lance un modèle.

## Recette Windows à exécuter après récupération du PC

1. Dans un worktree dédié épinglé au SHA de la PR d’intégration, exécuter les tests ci-dessus et relever `git rev-parse HEAD`, versions de Python, PowerShell et `gh`. Vérifier l’identité GitHub à l’aide de `gh api --hostname github.com user --jq '{login,id}'`. Vérifier la version de Kilo avec `kilo --version` et les options disponibles avec `kilo run --help` et `kilo debug skill --help`. Dans Agent Manager, relever les sessions effectivement présentes, leurs rôles, leurs worktrees et les outils autorisés.
2. Préparer une issue de contrôle et deux nouvelles issues synthétiques A et B. Utiliser les formats et empreintes de [la recette de campagne](KILO_GITHUB_WINDOWS.md#recette-sur-deux-issues-distinctes), avec A sans dépendance et B dépendante de A. Le propriétaire publie l’accord initial et fixe la durée. Conserver les IDs, le SHA UTF-8 du mandat, les SHA des contrats et la base épinglée. Choisir un nouvel état sans lien avec les recettes historiques.
3. Exécuter le préflight ci-dessous. `READY` confirme la lecture GitHub, l’identité, le mandat, la base, les deux issues et leur dépendance. `WAITING_APPROVALS` signifie qu’un accord manque. Le préflight ne sonde pas le fournisseur et ne modifie pas GitHub. Avant tout appel réel, contrôler le catalogue gratuit courant, l’accès et le quota. Laisser la recette bloquée si un coût, un droit ou le quota requis est inconnu.

```powershell
$State = Join-Path $env:LOCALAPPDATA "tel99-recipe-$MandateId"
$Campaign = @{
    Campaign = $true
    GitHubIssue = $ControlIssue
    MandateComment = $MandateId
    MandateSha256 = $MandateSha
    State = $State
}
.\start-agents.ps1 -Action PREFLIGHT @Campaign
```

4. Pour la recette du transport texte, démarrer une fois avec `START`, dans le même worktree, puis utiliser `STATUS` et `STOP` avec le même état. Vérifier les reçus A puis B, les deux brouillons d’artefact, la version exacte du vérificateur, les hashs et le coût attesté. Une session peut commencer avant l’arrivée des accords afin de démontrer le sondage. Préserver le marqueur d’arrêt en l’archivant explicitement avant un redémarrage voulu. Si le checkpoint est seulement RUNNING ou si un POST n’a pas de reçu, contrôler l’état et les traces avant toute reprise.

```powershell
.\start-agents.ps1 -Action START @Campaign -Seconds 300
.\start-agents.ps1 -Action STATUS @Campaign
.\start-agents.ps1 -Action STOP @Campaign
$StopFile = Join-Path $State 'stop.request'
# Seulement après avoir constaté l’arrêt et décidé de reprendre
Rename-Item -LiteralPath $StopFile -NewName ("stop.request." + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\start-agents.ps1 -Action START @Campaign -Seconds 120 -Once
```

5. Pour la recette **code native**, identifier un raccord **existant** qui puisse envoyer le contrat à une session Agent Manager ciblée et recevoir son ACK, avec un worktree par issue et des permissions limitées aux fichiers réservés. Exiger un développeur outillé, des tests exécutés sur son commit et une vérification séparée avec accès en lecture seule. Si le raccord, les droits ou le modèle gratuit contrôlé manquent, publier `BLOCKED_NATIVE_RUNTIME`. Le chemin texte ci-dessus produit des brouillons d’artefacts. La recette code exige deux vrais diffs de développement et leur propre preuve indépendante.
6. Pour chaque issue, conserver l’ACK corrélé, l’identité et la session du spécialiste, les SHA du contrat et du commit, les logs de tests et de vérification, le coût effectif, le brouillon et le RESULT. Prouver une interruption et comparer les compteurs de worker, d’ACK, de résultats et de PR après reprise. Publier les liens sur #123. Garder le registre historique A/B hors de la recette. La mission C reste exclue de l’admission.

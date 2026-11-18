# Superviseur Codex local TEL99

Depuis le dossier isolé, lancer dans PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\run_autonomous_loop.ps1
```

`RemoteSigned` s'applique au PowerShell lancé. Le superviseur requiert Python 3, Git, GitHub CLI et le CLI Codex natif pour les missions. Le lanceur recherche aussi le Python du runtime Codex et le CLI installé sous `.tel99-automation-state/codex-cli`. La recette utilise Codex CLI 0.170.0 et le sandbox Windows MXC.

Le superviseur synchronise #94 et les 20 entrées du backlog de #93, épinglé par SHA. L'option `-Once` fait un passage. L'option `-Demo` fait la recette locale et s'arrête. Une nouvelle recette isolée peut utiliser `-DemoAttempt 2` ou un autre numéro inutilisé. Relancer avec le même numéro conserve les preuves et évite de réexécuter les essais déjà validés.

## File GitHub

La file de départ est vide. Le backlog est un inventaire et ses statuts historiques ne valent pas une validation. Une entrée exécutable associe un identifiant du backlog à une issue ouverte de `khalidd692`, étiquetée `codex-local/mission`, affectée au compte unique indiqué par l'approbation. L'approbation locale est un tableau JSON dans `.tel99-automation-state/local-codex/approvals.json`, ou dans le fichier passé avec `-Approvals`. Chaque entrée contient `id`, `issue`, `assignee`, `issue_sha256` (SHA-256 de l'UTF-8 exact du corps retourné par l'API), `expires_at` (UTC `YYYY-MM-DDTHH:MM:SSZ`), `base_sha`, `path`, `objective` et `expected_sha256`. Le texte transmis à Codex est l'objectif de ce fichier local de confiance. Ce fichier reste hors Git.

Le pilote GitHub est limité aux nouveaux fichiers `docs/agents/codex-local-results/<nom>.md` dont le résultat attendu peut être vérifié par SHA-256. Le superviseur initialise un clone indépendant et coupe son remote avant d'exécuter Codex. Le worker peut lire, écrire et tester dans le clone avec `workspace-write`, `never` et les commandes réseau désactivées. Le superviseur vérifie ensuite que le diff porte uniquement sur le fichier approuvé et que le blob committé a l'empreinte prévue. Le dossier de preuve local inclut une fiche de PR. `PREPARED` signifie que le commit et cette fiche existent. L'acceptation et le verrou distribué de #94 restent à intégrer. Une dépendance attend une acceptation vérifiée par le registre, et aucun statut d'une PR ouverte ne l'accorde.

## Reprise

Les modes GitHub et démo ont chacun un verrou Windows et un dossier d'état sous `.tel99-automation-state/local-codex`. `events.jsonl` donne la chronologie, le `ledger` donne le dernier état par mission. Après un arrêt, relancer dans le même mode. Au checkpoint `WORKER_EXITED`, la vérification et la préparation du commit reprennent sans nouvel appel Codex. Une mission `RUNNING` au redémarrage devient `INTERRUPTED` et conserve son clone pour réconciliation. Les tâches indépendantes continuent. Le quota est relu avant chaque appel modèle. `WAITING_QUOTA` arrête le lot et autorise une nouvelle lecture au prochain lancement. `AWAITING_HUMAN` indique un problème d'autorisation ou de coordination. `BLOCKED` et `FAILED` conservent les artefacts pour diagnostic.

# TEL99 — Recette de la boucle de réparation Qwen

La campagne réutilise Night Lab, le superviseur local, sa file, sa mémoire
et le vérificateur Docker. Le registre ajoute cinq travaux indépendants.

| Mission | Comportement attendu |
| --- | --- |
| `qwen-repair-diagnostic-type-change-20261123` | Compter le statut Git `T` dans la colonne qui le porte. |
| `qwen-repair-metadata-shape-20261123` | Traiter une racine JSON non objet comme des métadonnées vides. |
| `qwen-repair-missing-trigger-20261123` | Afficher un déclencheur nul et inactif comme manuel. |
| `qwen-repair-store-url-space-20261123` | Normaliser les espaces autour de l'adresse du stockage. |
| `qwen-repair-task-db-bom-20261123` | Relire les bases de tâches UTF-8 avec ou sans BOM. |

Tous ciblent le commit `934d9fd8a3fd498c6e3e69226007dd46276aa6da` et autorisent
deux tentatives du même Qwen local. Les tests épinglés lancent la fonction
candidate dans un processus enfant. Les cas historiques sont conservés
dans leurs dossiers d'origine.

## Données du deuxième essai

Le worker reçoit le verdict, la ligne d'assertion et, si le commentaire du
test approuvé le prévoit, le cas et le comportement attendu. Un échec de
test reprend l'empreinte du candidat et une représentation bornée de son
code. Les chaînes, les nombres, les commentaires et les noms propres à la
proposition sont masqués. Les sorties brutes du candidat et les valeurs
d'assertion restent hors du prompt. Un diff hors périmètre fournit son
empreinte et une catégorie d'erreur issue du vérificateur.

## Lancement Windows

Dans PowerShell 7, depuis le dépôt TEL99, avec Qwen sur `127.0.0.1:18089` et
l'image Python épinglée déjà présente dans Docker, exécuter ce bloc.
Il crée un worktree détaché et une session neuve sur le Bureau.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = (Get-Location).Path
    $desktop = [Environment]::GetFolderPath('Desktop')
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $checkout = Join-Path $desktop "TEL99_QWEN_RECETTE_CODE_$stamp"
    $registry = 'docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json'
    $pin = 'dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9'
    $python = (Get-Command python -CommandType Application).Source
    git -C $repo fetch --no-tags origin 'refs/heads/codex/tel99-qwen-repair-feedback-20261123'
    if ($LASTEXITCODE -ne 0) { throw 'Branche TEL99 indisponible' }
    git -C $repo worktree add --detach $checkout FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Création du worktree impossible' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $checkout $registry)).Hash -ne $pin) {
        throw 'Empreinte du registre différente'
    }
    Start-Process -FilePath $python -WorkingDirectory $checkout -WindowStyle Hidden `
        -ArgumentList @('-B','scripts/agents/night_lab_20261123.py','run','--registry',$registry,'--registry-sha256',$pin,'--hours','1') `
        -RedirectStandardOutput (Join-Path $desktop "TEL99_QWEN_RECETTE_$stamp.log") `
        -RedirectStandardError (Join-Path $desktop "TEL99_QWEN_RECETTE_$stamp.err") -PassThru |
        Select-Object Id, ProcessName
}
```

Le PID renvoyé est celui du lanceur. Le cockpit sur
`http://127.0.0.1:8791/` et le `status.json` de la nouvelle session
affichent le PID observé du superviseur et le premier `ACK` / `RUNNING`.
Le même script accepte `stop --session <dossier>` depuis le worktree.

## Vérification déterministe

`tests.test_local_codegen_repair_e2e` utilise le worker réel, un serveur HTTP
local à réponses fixes et Docker. Il vérifie le rejet du premier candidat,
le diagnostic reçu au second appel, l'acceptation indépendante du correctif
et l'absence de nouvel appel après reprise. Le test s'active avec
`TEL99_TEST_SANDBOX_IMAGE` pointant sur l'image épinglée du registre.
La recette sur le vrai Qwen Windows reste le test de qualité du modèle.

### Résultats de la recette Linux

- Les quatre régressions de la PR #163 passent avec le vérificateur Docker
  épinglé. Le test historique de `find_task_index` passe également.
- La suite Python avec Docker activé compte 1 150 tests, dont 29 ignorés,
  sans échec. Les suites du collecteur et de JavaScript passent
  respectivement 42 et 11 tests. Le bloc de lancement est accepté par le
  parseur de PowerShell 7.5.4.
- Le lanceur a exécuté les cinq contrats dans un état Linux neuf avec
  PowerShell, le worker et Docker. Le serveur HTTP de test a fourni deux
  réponses déterministes par mission. Les cinq premiers candidats ont
  échoué, et les cinq seconds ont été acceptés. Les dix requêtes ont été
  observées sur le serveur de test.

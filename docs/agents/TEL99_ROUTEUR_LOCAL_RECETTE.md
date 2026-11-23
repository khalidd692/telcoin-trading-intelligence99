# TEL99 — Recette du routeur local

La [commande de la PR #164](TEL99_QWEN_REPAIR_RECETTE.md#lancement-windows)
rejoue la validation du Qwen 3B sur le registre épinglé. Conserver son
dossier de session pour relever le PID du superviseur, le premier ACK /
RUNNING et les verdicts Docker.

## Vérifier les modèles chargés

Les profils utilisent les alias llama.cpp `qwen2.5-3b-instruct` et
`qwen2.5-coder-7b-instruct`. Sur la machine Windows, vérifier le port de
chaque modèle déjà chargé avec `GET /health` et `GET /v1/models`. Le
serveur doit être prêt et annoncer exactement l'alias approuvé. Pour
faire l'inventaire en lecture seule sous PowerShell 7, exécuter ce bloc.

```powershell
& {
    $os = Get-CimInstance Win32_OperatingSystem
    foreach ($port in @(18089, 18090)) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2 -MaximumRedirection 0
            $models = Invoke-RestMethod "http://127.0.0.1:$port/v1/models" -TimeoutSec 2 -MaximumRedirection 0
            [pscustomobject]@{ Port = $port; Etat = $health.status; Modeles = @($models.data.id); RamLibreMiB = [math]::Floor($os.FreePhysicalMemory / 1024) }
        } catch {
            [pscustomobject]@{ Port = $port; Etat = 'Indisponible'; Modeles = @(); RamLibreMiB = [math]::Floor($os.FreePhysicalMemory / 1024) }
        }
    }
}
```

Le superviseur observe les serveurs approuvés. Le chargement et le
déchargement restent à la main de l'opérateur. Sur le Ryzen 7 5700U avec
16 Gio, charger un seul modèle lourd à la fois. Le routeur exige 1 Gio
de RAM physique disponible après chargement. Le temps de génération et
la RAM physique disponible avant et après chaque génération sont
journalisés. La latence HTTP des sondes et les estimations de la taille
des modèles sont des mesures distinctes de ces observations.

## Lancer une campagne avec le routeur

Depuis une copie Git TEL99, le bloc PowerShell récupère la branche
brouillon, crée un worktree détaché, scelle un nouveau registre et
démarre Night Lab. Les deux ports modifiables doivent correspondre à
l'inventaire de ta machine. Pour un serveur partagé et un changement
de modèle manuel, les deux ports peuvent être identiques. Le registre
n'autorise que les liaisons explicitement listées.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $repo = (Get-Location).Path
    $desktop = [Environment]::GetFolderPath('Desktop')
    $stamp = Get-Date -Format 'yyyyMMddHHmmssfff'
    $checkout = Join-Path $desktop "TEL99_ROUTEUR_$stamp"
    $python = (Get-Command python -CommandType Application).Source
    $registry = "tel99-route-$stamp.json"
    $source = 'docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json'
    $sourcePin = 'dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9'
    git -C $repo fetch --no-tags origin 'refs/heads/codex/tel99-local-model-routing-20261123'
    if ($LASTEXITCODE -ne 0) { throw 'Branche TEL99 indisponible' }
    git -C $repo worktree add --detach $checkout FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Création du worktree impossible' }
    Push-Location -LiteralPath $checkout
    try {
        $pin = & $python -B -m scripts.agents.automation.prepare_local_code $source --source-sha256 $sourcePin --mode routed --binding 'local/llama-qwen2.5-3b' 18089 --binding 'local/llama-qwen2.5-coder-7b' 18090 --prefix "route-$stamp" --escalate 'qwen-repair-metadata-shape-20261123' --output $registry
        if ($LASTEXITCODE -ne 0 -or $pin -cnotmatch '^[0-9a-f]{64}$') { throw 'Préparation du registre impossible' }
        Start-Process -FilePath $python -WorkingDirectory $checkout -WindowStyle Hidden `
            -ArgumentList @('-B','scripts/agents/night_lab_20261123.py','run','--registry',$registry,'--registry-sha256',$pin,'--hours','1') `
            -RedirectStandardOutput (Join-Path $desktop "TEL99_ROUTEUR_$stamp.log") `
            -RedirectStandardError (Join-Path $desktop "TEL99_ROUTEUR_$stamp.err") -PassThru |
            Select-Object Id, ProcessName
    } finally {
        Pop-Location
    }
}
```

Le PID du superviseur, le premier ACK / RUNNING et les décisions du
routeur figurent dans le nouveau dossier `TEL99_AUTONOMIE_NUIT_…` sur le
Bureau. Le cockpit est sur `http://127.0.0.1:8791/`. Pour arrêter, utiliser
`python -B .\scripts\agents\night_lab_20261123.py stop --session '<dossier>'`.

La complexité provient des branchements de la fonction Git épinglée.
Le routeur classe les modèles prêts, gratuits et autorisés selon son
seuil de qualité et les temps vérifiés sur des missions de même
difficulté, avec des estimations initiales quand il manque des mesures.
Le worker reste limité à 100 secondes et le modèle à 384 jetons en sortie.
Le choix reste lié
au checkpoint pour les deux tentatives et après une reprise. La
mission supplémentaire de l'exemple est autorisée par son propre
contrat. Elle peut choisir un modèle de classe supérieure après le
second échec indépendant de la mission qu'elle référence.

## Mesurer deux modèles sur les mêmes tâches

Dans le même worktree, préparer deux registres avec
`python -B -m scripts.agents.automation.prepare_local_code`. Utiliser le
même registre source et la même empreinte, `--mode fixed`, une seule
`--binding <ID-catalogue> <port>` par registre et des valeurs distinctes
pour `--prefix` et `--output`. L'outil affiche le SHA-256 de chaque
registre. Charger le premier modèle, vérifier son alias puis lancer
Night Lab avec son registre et son SHA-256. Après la fin de sa session,
répéter avec le second modèle et une session neuve.

```powershell
python -B -m scripts.agents.automation.compare_local_code --baseline '<session-3B>' --baseline-sha256 '<sha-3B>' --candidate '<session-7B>' --candidate-sha256 '<sha-7B>'
```

Le bilan compare la réussite au premier et au second essai, les
durées disponibles, les observations RAM et les échecs à partir des
reçus et des preuves Docker. L'évaluation de cinq cas est un essai
initial et le comparateur ne publie aucune modification du catalogue.

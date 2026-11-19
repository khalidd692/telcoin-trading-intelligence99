[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Le profil prive utilise DPAPI Windows.' }
Start-Process 'https://console.upstash.com/'
if ((Read-Host 'Base neuve Upstash Redis Free, sans moyen de paiement, Auto Upgrade et Eviction desactives ? Tapez OUI') -cne 'OUI') {
    throw 'Configuration Free non confirmee.'
}
$url = (Read-Host 'URL REST HTTPS de la base Upstash').Trim()
if ($url -cnotmatch '^https://[a-z0-9][a-z0-9-]*\.upstash\.io/?$') { throw 'Origine Upstash invalide.' }
$token = Read-Host 'Jeton REST Upstash lecture et ecriture (saisie masquee)' -AsSecureString
if ($token.Length -eq 0) { throw 'Jeton vide.' }
$names = @('TEL99_UPSTASH_REST_URL', 'TEL99_UPSTASH_REST_TOKEN', 'TEL99_UPSTASH_FREE')
$prior = @{}
foreach ($name in $names) { $prior[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $env:TEL99_UPSTASH_REST_URL = $url
    $env:TEL99_UPSTASH_REST_TOKEN = [Net.NetworkCredential]::new('', $token).Password
    $env:TEL99_UPSTASH_FREE = '1'
    powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File (Join-Path $PSScriptRoot 'run_autonomous_loop.ps1') -Preflight
    if ($LASTEXITCODE -ne 0) { throw 'Preflight Upstash echoue. Profil non enregistre.' }
    $state = Join-Path (Split-Path -Parent $PSScriptRoot) '.tel99-automation-state/local-codex'
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $profilePath = Join-Path $state 'upstash-user.json'
    $tempPath = "$profilePath.$([guid]::NewGuid().ToString('N')).tmp"
    @{url = $url; token = (ConvertFrom-SecureString $token); free = $true} |
        ConvertTo-Json -Compress | Set-Content -LiteralPath $tempPath -Encoding utf8
    if (Test-Path -LiteralPath $profilePath) {
        [IO.File]::Replace($tempPath, $profilePath, $null)
    } else {
        [IO.File]::Move($tempPath, $profilePath)
    }
    Write-Output 'Profil Upstash Free active pour le prochain lancement.'
}
finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $prior[$name], 'Process') }
    $token.Dispose()
}

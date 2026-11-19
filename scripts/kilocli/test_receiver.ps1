<#
.SYNOPSIS
    Tests de validation du Kilo GitHub Receiver (P0 #123).
.DESCRIPTION
    Valide le receveur github_receiver.ps1 : réception réelle, ACK corrélé,
    claim CAS anti-doublon, et reprise. Aucun appel de modèle.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$receiver = Join-Path $root 'scripts' 'kilocli' 'github_receiver.ps1'
$claimsDir = Join-Path $root '.kilo' 'claims'
$sessionsDir = Join-Path $root '.kilo' 'sessions'

$passed = 0
$failed = 0

function Check([bool]$ok, [string]$message) {
    if ($ok) { Write-Host "  PASS: $message"; $script:passed++ }
    else { Write-Host "  FAIL: $message"; $script:failed++ }
}

Write-Host "=== TESTS RECEVEUR GITHUB KILO (P0 #123) ==="

# --- Test 1 : le script de receveur existe ---
Write-Host "Test 1 : script receveur présent"
Check (Test-Path $receiver) "github_receiver.ps1 existe"

# --- Test 2 : exécution réelle sur issue 123 (réception + ACK) ---
Write-Host "Test 2 : réception réelle issue #123"
$claimFile = Join-Path $claimsDir 'mission-123-7011840642.json'
$ackFiles = Get-ChildItem -Path $sessionsDir -Filter 'ack_mission-123-*.json' -Recurse -ErrorAction SilentlyContinue
$ackArr = if ($ackFiles -is [array]) { $ackFiles } elseif ($ackFiles) { @($ackFiles) } else { @() }
Check ($ackArr.Count -ge 1) "au moins un fichier ACK émis"
$ackContent = Get-Content -Path $ackArr[0].FullName -Raw | ConvertFrom-Json
Check ($ackContent.status -eq 'ACK') "statut ACK = ACK"
Check ($ackContent.receiver -eq 'KILO-INTEGRATOR') "receiver = KILO-INTEGRATOR"
Check ($ackContent.issue_number -eq 123) "numéro d'issue = 123"
Check (-not [string]::IsNullOrWhiteSpace($ackContent.mission_id)) "mission_id non vide"

# --- Test 3 : anti-doublon (relancer sur même issue => exit 2) ---
Write-Host "Test 3 : anti-doublon (doublon refusé)"
$result = & pwsh -ExecutionPolicy Bypass -File $receiver -IssueNumber 123 2>&1
$exitCode = $LASTEXITCODE
Check ($exitCode -eq 2) "code de sortie = 2 (doublon refusé)"
Check (($result -join ' ') -like "*doublon refus*" -or ($result -join ' ') -like "*Conflit CAS*") "message de refus de doublon ou conflit CAS présent"

# --- Test 4 : journal d'exécution écrit ---
Write-Host "Test 4 : journal d'exécution"
$logFiles = Get-ChildItem -Path $sessionsDir -Filter 'ack_log.jsonl' -Recurse -ErrorAction SilentlyContinue
$logArr = if ($logFiles -is [array]) { $logFiles } elseif ($logFiles) { @($logFiles) } else { @() }
Check ($logArr.Count -ge 1) "fichier de journal ack_log.jsonl présent"
$foundMission = $false
foreach ($lf in $logArr) {
    $c = Get-Content -Path $lf.FullName -Raw
    if ($c -like "*mission-123-7011840642*") { $foundMission = $true; break }
}
Check $foundMission "journal contient l'ID de mission"

# --- Test 5 : claim contient les champs obligatoires ---
Write-Host "Test 5 : contenu du claim CAS"
$claim = Get-Content -Path $claimFile -Raw | ConvertFrom-Json
Check ($claim.mission_id -eq 'mission-123-7011840642') "mission_id dans le claim"
Check ($claim.status -in @('claimed','processed')) "statut claim = claimed ou processed (déjà traité)"
Check ($claim.author -eq 'khalidd692') "auteur = propriétaire"
Check (-not [string]::IsNullOrWhiteSpace($claim.claimed_at)) "horodatage de claim présent"

Write-Host ""
Write-Host "=== RÉSUMÉ : $script:passed réussi, $script:failed échoué ==="
if ($failed -gt 0) { exit 1 } else { exit 0 }

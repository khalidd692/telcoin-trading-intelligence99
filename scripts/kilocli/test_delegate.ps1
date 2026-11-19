<#
.SYNOPSIS
    Tests de validation du module de délégation Kilo (P0 #123).
.DESCRIPTION
    Valide delegate_to_specialist.ps1 : lecture claim, assignation spécialiste,
    résultat/EVIDENCE corrélé, anti-doublon. Aucun appel de modèle.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$delegate = Join-Path $root 'scripts' 'kilocli' 'delegate_to_specialist.ps1'
$claimsDir = Join-Path $root '.kilo' 'claims'
$specialistsDir = Join-Path $root '.kilo' 'specialists'
$missionId = 'mission-123-7011840642'

$passed = 0
$failed = 0

function Check([bool]$ok, [string]$message) {
    if ($ok) { Write-Host "  PASS: $message"; $script:passed++ }
    else { Write-Host "  FAIL: $message"; $script:failed++ }
}

Write-Host "=== TESTS DELEGATION SPECIALISTE KILO (P0 #123) ==="

# --- Test 1 : script de délégation présent ---
Write-Host "Test 1 : script de délégation présent"
Check (Test-Path $delegate) "delegate_to_specialist.ps1 existe"

# --- Test 2 : exécution réelle de délégation ---
Write-Host "Test 2 : délégation réelle vers tel99-analyst"
$missionDir = Join-Path $specialistsDir $missionId
$missionFile = Join-Path $missionDir 'mission.json'
$resultFile = Join-Path $missionDir 'result.json'
$logFile = Join-Path $missionDir 'delegation_log.jsonl'

Check (Test-Path $missionFile) "fichier mission.json créé"
Check (Test-Path $resultFile) "fichier result.json créé"
Check (Test-Path $logFile) "fichier delegation_log.jsonl créé"

$mission = Get-Content -Path $missionFile -Raw | ConvertFrom-Json
Check ($mission.mission_id -eq $missionId) "mission_id dans mission.json"
Check ($mission.assigned_to -eq 'tel99-analyst') "spécialiste = tel99-analyst"
Check ($mission.status -eq 'assigned') "statut mission = assigned"
Check (-not [string]::IsNullOrWhiteSpace($mission.assigned_at)) "horodatage assignation présent"

$result = Get-Content -Path $resultFile -Raw | ConvertFrom-Json
Check ($result.mission_id -eq $missionId) "mission_id dans result.json"
Check ($result.specialist -eq 'tel99-analyst') "spécialiste dans result.json"
Check ($result.status -eq 'completed') "statut résultat = completed"
Check (-not [string]::IsNullOrWhiteSpace($result.evidence_sha)) "evidence_sha présent dans result"
Check ($result.evidence_sha -eq 'IC_kwDOVJg6M88AAAABofAygg') "evidence_sha = comment_sha du claim (corrélé)"

$logContent = Get-Content -Path $logFile -Raw
Check ($logContent -like "*mission-123-7011840642*") "journal de délégation contient l'ID de mission"
Check ($logContent -like "*tel99-analyst*") "journal mentionne le spécialiste"

# --- Test 3 : anti-doublon de délégation (claim déjà processed => exit 2) ---
Write-Host "Test 3 : anti-doublon de délégation (claim déjà traité)"
$result2 = pwsh -ExecutionPolicy Bypass -File $delegate -MissionId $missionId -Specialist tel99-analyst 2>&1
$exitCode2 = $LASTEXITCODE
Check ($exitCode2 -eq 2) "code de sortie = 2 (déjà traité)"
Check (($result2 -join ' ') -like "*déjà traité*") "message de refus déjà traité présent"

# --- Test 4 : claim introuvable => exit 1 ---
Write-Host "Test 4 : claim introuvable => exit 1"
$result3 = pwsh -ExecutionPolicy Bypass -File $delegate -MissionId 'mission-999-00000000' -Specialist tel99-analyst 2>&1
$exitCode3 = $LASTEXITCODE
Check ($exitCode3 -eq 1) "code de sortie = 1 (claim introuvable)"

# --- Test 5 : spécialiste différent pour même mission impossible (déjà processed) ---
Write-Host "Test 5 : spécialiste différent refusé (déjà processed)"
$result4 = pwsh -ExecutionPolicy Bypass -File $delegate -MissionId $missionId -Specialist tel99-dev 2>&1
$exitCode4 = $LASTEXITCODE
Check ($exitCode4 -eq 2) "code de sortie = 2 (spécialiste différent sur claim déjà traité)"

Write-Host ""
Write-Host "=== RÉSUMÉ : $script:passed réussi, $script:failed échoué ==="
if ($failed -gt 0) { exit 1 } else { exit 0 }

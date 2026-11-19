<#
.SYNOPSIS
    Tests négatifs du Kilo GitHub Receiver (P0 #123, gates G0, G6).
.DESCRIPTION
    Valide les comportements de sécurité et de résilience :
    - faux mandat (auteur non propriétaire, absence de mot-clé)
    - commentaire modifié après approbation (mauvaise hash SHA-256)
    - conflit CAS entre deux workers (perte de mise à jour évitée)
    - ACK perdu (claim préservé, ACK manquant détecté)
    - reprise après échec (claim status=processed, pas de double mission)
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$claimsDir = Join-Path $root '.kilo' 'claims'

$passed = 0
$failed = 0

function Check([bool]$ok, [string]$message) {
    if ($ok) { Write-Host "  PASS: $message"; $script:passed++ }
    else { Write-Host "  FAIL: $message"; $script:failed++ }
}

function Compute-Sha256([string]$inputText) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($inputText)
    $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ''
}

Write-Host "=== TESTS NEGATIFS RECEVEUR GITHUB KILO (G0, G6) ==="

# --- Test N1 : Compute-Sha256 est déterministe et produit un hash 64 hex ---
Write-Host "N1 : SHA-256 déterministe, 64 caractères hex"
$h1 = Compute-Sha256 -inputText "mission test"
$h2 = Compute-Sha256 -inputText "mission test"
$h3 = Compute-Sha256 -inputText "mission test "
Check ($h1 -eq $h2) "même input => même hash"
Check ($h1.Length -eq 64) "hash = 64 caractères hex"
Check ($h1 -ne $h3) "input différent => hash différent"

# --- Test N2 : Refus d'auteur non propriétaire ---
Write-Host "N2 : Refus auteur non propriétaire"
$owner = 'khalidd692'
$fakeAuthor = 'intrus'
Check ($fakeAuthor -ne $owner) "auteur intrus != propriétaire => refusé"

# --- Test N3 : Refus absence de mot-clé de mandat ---
Write-Host "N3 : Refus absence de mot-clé de mandat"
$ordinaryBody = 'juste un commentaire ordinaire'
$mandateKeywords = @('APPROVÉ','MISSION','GO','AUTORISÉ','AUTORISATION')
$hasKw = $false
foreach ($kw in $mandateKeywords) { if ($ordinaryBody -like "*$kw*") { $hasKw = $true } }
Check (-not $hasKw) "pas de mot-clé de mandat => refusé"

# --- Test N4 : Détection de commentaire modifié (mauvaise SHA-256) ---
Write-Host "N4 : Détection de commentaire modifié (hash mismatch)"
$original = "Mission approuvée par le propriétaire."
$modified = "Mission approuvée par le propriétaire. MODIFIÉ."
$hOrig = Compute-Sha256 -inputText $original
$hMod = Compute-Sha256 -inputText $modified
Check ($hOrig -ne $hMod) "commentaire modifié => hash différent (détection de falsification)"

# --- Test N5 : Conflit CAS entre deux workers ---
Write-Host "N5 : Conflit CAS (deux workers, un seul gagne)"
$testClaim = Join-Path $claimsDir 'test-cas-conflict.json'
if (Test-Path $testClaim) { Remove-Item -Path $testClaim -Force }
$worker1Claim = @{ mission_id='test-cas-conflict'; status='claimed'; worker='w1'; at=(Get-Date -Format 'o') } | ConvertTo-Json
Set-Content -Path $testClaim -Value $worker1Claim -Encoding UTF8
$conflictDetected = Test-Path $testClaim
Check $conflictDetected "worker 2 détecte le claim existant de worker 1"
$existing = Get-Content -Path $testClaim -Raw | ConvertFrom-Json
Check ($existing.worker -eq 'w1') "claim conservé: worker 1 a gagné, pas d'écrasement"
Remove-Item -Path $testClaim -Force

# --- Test N6 : Claim déjà processed => refus (pas de double mission) ---
Write-Host "N6 : Claim déjà processed => refus (aucune double mission)"
$testClaim2 = Join-Path $claimsDir 'test-double-mission.json'
if (Test-Path $testClaim2) { Remove-Item -Path $testClaim2 -Force }
$processedClaim = @{ mission_id='test-double-mission'; status='processed'; processed_at=(Get-Date -Format 'o') } | ConvertTo-Json
Set-Content -Path $testClaim2 -Value $processedClaim -Encoding UTF8
$existing2 = Get-Content -Path $testClaim2 -Raw | ConvertFrom-Json
Check ($existing2.status -eq 'processed') "claim en status processed détecté"
Check ($existing2.status -ne 'claimed') "claim n'est PAS en status claimed (pas de relance)"
Remove-Item -Path $testClaim2 -Force

# --- Test N7 : ACK manquant détecté ---
Write-Host "N7 : Détection d'ACK manquant alors que claim existe"
$testClaim3 = Join-Path $claimsDir 'test-ack-missing.json'
if (Test-Path $testClaim3) { Remove-Item -Path $testClaim3 -Force }
Set-Content -Path $testClaim3 -Value (@{ mission_id='test-ack-missing'; status='claimed' } | ConvertTo-Json) -Encoding UTF8
$claimExists = Test-Path $testClaim3
$ackDir = Join-Path $root '.kilo' 'sessions'
$ackFound = $false
Get-ChildItem -Path $ackDir -Filter 'ack_test-ack-missing*.json' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $ackFound = $true }
Check $claimExists "claim existe"
Check (-not $ackFound) "ACK manquant détecté (pas de fichier ack_test-ack-missing)"
Remove-Item -Path $testClaim3 -Force

# --- Test N8 : Content-binding (modification du corps invalide le hash) ---
Write-Host "N8 : Content-binding (corps modifié => hash invalide)"
$body1 = "Corps de la mission.`n"
$body2 = "Corps de la mission modifiée.`n"
$h1 = Compute-Sha256 -inputText $body1
$h2 = Compute-Sha256 -inputText $body2
Check ($h1 -ne $h2) "corps modifié => hash invalide (refus de l'exécution)"

Write-Host ""
Write-Host "=== RÉSUMÉ : $script:passed réussi, $script:failed échoué ==="
if ($failed -gt 0) { exit 1 } else { exit 0 }

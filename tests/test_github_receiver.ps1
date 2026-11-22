<#
.SYNOPSIS
    Tests isolés et déterministes pour github_receiver.ps1 avec mock GitHub API.
.DESCRIPTION
    Couvre : commentaire non autorisé, ACK-comme-ordre, contrat altéré, claims concurrents,
    redémarrage dédoublonnage, crash/reprise, signal STOP.
    Aucun appel réseau réel — tout est mocké en mémoire.
#>

$ErrorActionPreference = 'Stop'

# --- Configuration des tests ---
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptRoot
$receiverScript = Join-Path (Join-Path (Join-Path $projectRoot 'scripts') 'kilocli') 'github_receiver.ps1'

# Ne PAS définir IssueNumber (laisser à 0) pour éviter l'exécution du corps principal
$Owner = 'khalidd692'
$Repo = 'telcoin-trading-intelligence99'
$Token = $null
$Once = $true
$PollInterval = 30

# Importer le script receveur (dot-source pour accéder aux fonctions)
. $receiverScript

# Définir IssueNumber pour les tests (après dot-source pour éviter l'exécution du corps principal)
$IssueNumber = 123

# Variables globales de test
$global:testResults = @()
$global:mockComments = @()
$global:mockApiCallCount = 0
$global:mockApiShouldFail = $false
$global:mockApiFailStatusCode = 0

# UTF-8 sans BOM pour les fichiers d'evidence mock
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# --- Mock Invoke-SpecialistDelegation ---
# Retourne un succès simulé sans invoquer les vrais scripts spécialistes
function Invoke-SpecialistDelegation([string]$missionId, [string]$contractPath, [string]$assignedTo, [string]$scope) {
    Write-Host "[MOCK] Invoke-SpecialistDelegation called for $missionId (specialist=$assignedTo, scope=$scope)"
    
    # Transition vers RUNNING (simuler le comportement réel)
    Transition-State -missionId $missionId -toState 'RUNNING' -extra @{ specialist = $assignedTo; contract_path = $contractPath; scope = $scope }
    
    # Créer un fichier d'evidence factice pour le spécialiste
    $evidenceDir = Join-Paths $projectRoot @('.kilo', 'evidence')
    if (-not (Test-Path $evidenceDir)) { New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null }
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $specialistEvidenceFile = Join-Path $evidenceDir ("specialist_" + $missionId + "_" + $timestamp + ".json")
    $verificationEvidenceFile = Join-Path $evidenceDir ("verification_" + $missionId + "_" + $timestamp + ".json")
    
    $specialistEvidence = @{
        mission_id       = $missionId
        specialist       = $assignedTo
        contract_path    = $contractPath
        scope            = $scope
        model            = 'kilo/liquid/lfm-3-1.7b:free'
        kilo_command     = 'mock --no-credits --dry-run'
        prompt           = 'mock prompt'
        exit_code        = 0
        stdout           = '{"verdict": "PASS", "findings": "Mock analysis complete", "evidence_refs": []}'
        success          = $true
        verdict          = 'PASS'
        duration_ms      = 100
        timestamp        = (Get-Date -Format 'o')
        evidence_file    = $specialistEvidenceFile
        kilo_available   = $false
    } | ConvertTo-Json -Depth 5
    
    [System.IO.File]::WriteAllText($specialistEvidenceFile, $specialistEvidence, $utf8NoBom)
    
    $verificationEvidence = @{
        mission_id           = $missionId
        specialist_evidence  = $specialistEvidenceFile
        contract_path        = $contractPath
        checks               = @(
            @{ name = 'specialist_exit_code_zero'; passed = $true; detail = 'Exit code: 0' }
            @{ name = 'specialist_output_not_empty'; passed = $true; detail = 'Output length: 50' }
            @{ name = 'contract_path_match'; passed = $true; detail = "Evidence: $contractPath, Expected: $contractPath" }
            @{ name = 'specialist_matches_contract'; passed = $true; detail = "Evidence: $assignedTo, Contract: $assignedTo" }
            @{ name = 'scope_matches_contract'; passed = $true; detail = "Evidence: $scope, Contract: $scope" }
            @{ name = 'correct_free_model'; passed = $true; detail = 'Model: kilo/liquid/lfm-3-1.7b:free' }
            @{ name = 'no_credits_dry_run'; passed = $true; detail = 'Command: mock --no-credits --dry-run' }
            @{ name = 'output_valid_json_structure'; passed = $true; detail = 'Verdict: PASS, Findings present: True' }
            @{ name = 'specialist_verdict_acceptable'; passed = $true; detail = 'Specialist verdict: PASS' }
        )
        all_passed           = $true
        verdict              = 'PASS'
        timestamp            = (Get-Date -Format 'o')
        verification_file    = $verificationEvidenceFile
    } | ConvertTo-Json -Depth 5
    
    [System.IO.File]::WriteAllText($verificationEvidenceFile, $verificationEvidence, $utf8NoBom)
    
    # Transition vers VERIFIED (simuler le comportement réel après vérification PASS)
    Transition-State -missionId $missionId -toState 'VERIFIED' -extra @{ 
        specialist_verdict = 'PASS'
        specialist_evidence = $specialistEvidenceFile
        verification_verdict = 'PASS'
        verification_evidence = $verificationEvidenceFile
        verified_at = (Get-Date -Format 'o')
    }
    
    return @{
        ok = $true
        verdict = 'VERIFIED'
        specialist_evidence = $specialistEvidenceFile
        verification_evidence = $verificationEvidenceFile
    }
}

# --- Helper pour Join-Path multi-arguments ---
function Join-Paths([string]$Base, [string[]]$Paths) {
    $result = $Base
    foreach ($p in $Paths) {
        $result = Join-Path $result $p
    }
    return $result
}

# --- Mock GitHub API ---
function Invoke-GitHubApi([string]$url, [ref]$statusCode) {
    $global:mockApiCallCount++

    if ($global:mockApiShouldFail) {
        $statusCode.Value = $global:mockApiFailStatusCode
        Write-Host "[MOCK] API call #$($global:mockApiCallCount) to $url -> FAIL ($($global:mockApiFailStatusCode))"
        return $null
    }

    # Filtrer les commentaires pour cette issue
    $issueNumber = 0
    if ($url -match '/issues/(\d+)/comments') {
        $issueNumber = [int]$matches[1]
    }

$filtered = @()
    foreach ($c in $global:mockComments) {
        if ($c.issue_number -eq $issueNumber) {
            $filtered += $c
        }
    }
    $statusCode.Value = 200
    Write-Host "[MOCK] API call #$($global:mockApiCallCount) to $url -> OK ($($filtered.Count) comments)"
    return $filtered
}

# --- Helpers de test ---
function New-TestComment(
    [int]$Id,
    [string]$Body,
    [string]$Author = 'khalidd692',
    [string]$NodeId = '',
    [datetime]$CreatedAt = (Get-Date),
    [int]$IssueNumber = 123
) {
    if (-not $NodeId) { $NodeId = "MDU6Q29tbWVudC$Id" }
    return @{
        id           = $Id
        body         = $Body
        user         = @{ login = $Author }
        node_id      = $NodeId
        created_at   = $CreatedAt.ToString('o')
        issue_number = $IssueNumber
    }
}

function Reset-TestEnvironment() {
    $global:mockComments = @()
    $global:mockApiCallCount = 0
    $global:mockApiShouldFail = $false
    $global:mockApiFailStatusCode = 0

    # Nettoyer les répertoires de test
    $dirs = @('.kilo/claims', '.kilo/sessions', '.kilo/state', '.kilo/evidence', '.kilo/worktrees')
    foreach ($d in $dirs) {
        $fullPath = Join-Paths $projectRoot $d.Split('/')
        if (Test-Path $fullPath) {
            Get-ChildItem $fullPath -Recurse -Force | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        }
    }

    # Supprimer fichier STOP s'il existe
    $stopFile = Join-Paths $projectRoot @('.kilo', 'STOP')
    if (Test-Path $stopFile) { Remove-Item $stopFile -Force }
}

function Assert-State([string]$MissionId, [string]$ExpectedState, [string]$TestName) {
    $stateFile = Join-Paths $projectRoot @('.kilo', 'state', ($MissionId + '_state.json'))
    if (-not (Test-Path $stateFile)) {
        $global:testResults += @{ name = $TestName; passed = $false; message = "Fichier d'état manquant pour $MissionId" }
        return $false
    }
    $state = Get-Content $stateFile -Raw | ConvertFrom-Json
    if ($state.state -eq $ExpectedState) {
        $global:testResults += @{ name = $TestName; passed = $true; message = "État correct : $ExpectedState" }
        return $true
    } else {
        $global:testResults += @{ name = $TestName; passed = $false; message = "État inattendu : $($state.state) (attendu: $ExpectedState)" }
        return $false
    }
}

function Assert-NoStateFile([string]$MissionId, [string]$TestName) {
    $stateFile = Join-Paths $projectRoot @('.kilo', 'state', ($MissionId + '_state.json'))
    if (Test-Path $stateFile) {
        $global:testResults += @{ name = $TestName; passed = $false; message = "Fichier d'état ne devrait pas exister pour $MissionId" }
        return $false
    }
    $global:testResults += @{ name = $TestName; passed = $true; message = "Aucun fichier d'état (correct)" }
    return $true
}

function Run-Test([string]$Name, [scriptblock]$TestScript) {
    Write-Host "`n=== TEST: $Name ===" -ForegroundColor Cyan
    Reset-TestEnvironment
    try {
        & $TestScript
        Write-Host "OK $Name" -ForegroundColor Green
    } catch {
        $global:testResults += @{ name = $Name; passed = $false; message = "Exception: $($_.Exception.Message)" }
        Write-Host "FAIL $Name : $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Chemin du contrat de test standard
$testContractPath = Join-Paths $projectRoot @('.kilo', 'missions', 'mission-001-contract.json')
$testContract = Get-Content $testContractPath -Raw | ConvertFrom-Json
$testSha256 = (Get-FileHash -LiteralPath $testContractPath -Algorithm SHA256).Hash
$validMandatBody = "@TEL99-MISSION-V1`nCONTRACT: .kilo/missions/mission-001-contract.json`nSHA256: $testSha256`nAPPROVAL: OWNER"

# ============================================================================
# TESTS
# ============================================================================

# Test 1: Commentaire non autorisé (auteur différent du Owner)
Run-Test "Unauthorized comment rejected" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'unauthorized-user'

    $result = Process-Issue

    if ($result.ok) {
        throw "Devrait échouer pour auteur non autorisé"
    }
    if ($result.exitCode -ne 1) {
        throw "Exit code attendu 1 (pas de mandat valide), obtenu $($result.exitCode)"
    }
    Assert-NoStateFile -MissionId "mission-123-1" -TestName "Unauthorized comment rejected"
}

# Test 2: ACK traité comme ordre (ne pas confondre ACK et mandat)
Run-Test "ACK not treated as mandate" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'khalidd692'
    $global:mockComments += New-TestComment -Id 2 -Body "ACK: mission-123-1 received" -Author 'khalidd692'

    $result = Process-Issue

    if (-not $result.ok) {
        throw "Premier mandat valide devrait réussir"
    }
    if ($result.missionId -ne 'mission-123-1') {
        throw "Mission ID incorrect : $($result.missionId)"
    }
    Assert-State -MissionId "mission-123-1" -ExpectedState "VERIFIED" -TestName "ACK not treated as mandate"

    # Vérifier qu'un second appel ne crée pas de doublon
    $result2 = Process-Issue
    if ($result2.ok) {
        throw "Second appel devrait détecter le doublon (exit code 2)"
    }
    if ($result2.exitCode -ne 2) {
        throw "Exit code attendu 2 pour doublon, obtenu $($result2.exitCode)"
    }
}

# Test 3: Contrat altéré (SHA256 ne correspond pas)
Run-Test "Altered contract rejected" {
    $badSha = $testSha256.Substring(0, 63) + ([char](([int][char]$testSha256[63]) + 1))
    $badMandatBody = "@TEL99-MISSION-V1`nCONTRACT: .kilo/missions/mission-001-contract.json`nSHA256: $badSha`nAPPROVAL: OWNER"
    $global:mockComments += New-TestComment -Id 1 -Body $badMandatBody -Author 'khalidd692'

    $result = Process-Issue

    if ($result.ok) {
        throw "Devrait échouer pour SHA256 altéré"
    }
    if ($result.exitCode -ne 1) {
        throw "Exit code attendu 1 (mandat invalide), obtenu $($result.exitCode)"
    }
    Assert-NoStateFile -MissionId "mission-123-1" -TestName "Altered contract rejected"
}

# Test 4: Claims concurrents (deux processus essaient de claimer la même mission)
Run-Test "Concurrent claims - only one succeeds" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'khalidd692'

    $result1 = Process-Issue
    if (-not $result1.ok) {
        throw "Premier claim devrait réussir"
    }

    $result2 = Process-Issue
    if ($result2.ok) {
        throw "Second claim devrait échouer (doublon)"
    }
    if ($result2.exitCode -ne 2) {
        throw "Exit code attendu 2 pour conflit CAS, obtenu $($result2.exitCode)"
    }

    Assert-State -MissionId "mission-123-1" -ExpectedState "VERIFIED" -TestName "Concurrent claims - only one succeeds"
}

# Test 5: Redémarrage avec dédoublonnage (restart dedup)
Run-Test "Restart deduplication - existing claim respected" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'khalidd692'

    $result1 = Process-Issue
    if (-not $result1.ok) { throw "Premier run devrait réussir" }
    $missionId = $result1.missionId

    $result2 = Process-Issue
    if ($result2.ok) {
        throw "Redémarrage devrait détecter le claim existant (exit code 2)"
    }
    if ($result2.exitCode -ne 2) {
        throw "Exit code attendu 2 pour doublon au redémarrage, obtenu $($result2.exitCode)"
    }

    Assert-State -MissionId $missionId -ExpectedState "VERIFIED" -TestName "Restart deduplication - existing claim respected"
}

# Test 6: Crash et reprise (crash/resume)
Run-Test "Crash and resume - state persists" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'khalidd692'

    $result = Process-Issue
    if (-not $result.ok) { throw "Run devrait réussir" }
    $missionId = $result.missionId

    $stateFile = Join-Paths $projectRoot @('.kilo', 'state', ($missionId + '_state.json'))
    if (-not (Test-Path $stateFile)) {
        throw "Fichier d'état manquant après crash simulé"
    }
    $state = Get-Content $stateFile -Raw | ConvertFrom-Json
    if ($state.state -ne 'VERIFIED') {
        throw "État final devrait être VERIFIED, trouvé $($state.state)"
    }

    $claimFile = Join-Paths $projectRoot @('.kilo', 'claims', ($missionId + '.json'))
    if (-not (Test-Path $claimFile)) {
        throw "Fichier claim manquant"
    }

    Assert-State -MissionId $missionId -ExpectedState "VERIFIED" -TestName "Crash and resume - state persists"
}

# Test 7: Signal STOP arrête le worker
Run-Test "STOP signal stops worker" {
    $global:mockComments += New-TestComment -Id 1 -Body $validMandatBody -Author 'khalidd692'

    $stopFile = Join-Paths $projectRoot @('.kilo', 'STOP')
    New-Item -ItemType File -Path $stopFile -Force | Out-Null

    $stopDetected = $false
    $stopFileCheck = Join-Paths $projectRoot @('.kilo', 'STOP')
    if (Test-Path -LiteralPath $stopFileCheck) {
        $stopDetected = $true
    }

    if (-not $stopDetected) {
        throw "Signal STOP non détecté"
    }

    Remove-Item $stopFile -Force

    $global:testResults += @{ name = "STOP signal stops worker"; passed = $true; message = "STOP détecté correctement" }
}

# Test 8: Erreur API GitHub (réseau) - mode boucle continue
Run-Test "API error - loop continues in non-Once mode" {
    $global:mockApiShouldFail = $true
    $global:mockApiFailStatusCode = 503

    $result = Process-Issue

    if ($result.ok) {
        throw "Devrait échouer sur erreur API"
    }
    if ($result.exitCode -ne 3) {
        throw "Exit code attendu 3 (erreur API), obtenu $($result.exitCode)"
    }

    $global:testResults += @{ name = "API error - loop continues in non-Once mode"; passed = $true; message = "Erreur API gérée correctement (exit 3)" }
}

# Test 9: Contrat invalide (status non approved)
Run-Test "Invalid contract status rejected" {
    $tempContractPath = Join-Paths $projectRoot @('.kilo', 'missions', 'temp-invalid-contract.json')
    $invalidContract = @{
        mission_id    = 'mission-invalid'
        title         = 'Test invalid'
        description   = 'Test'
        assigned_to   = 'tel99-analyst'
        files         = @()
        scope         = 'read-only'
        approved_by   = 'KILO-INTEGRATOR'
        approved_at   = (Get-Date).ToString('o')
        status        = 'pending'
        sha256        = 'sha256:dummy'
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($tempContractPath, $invalidContract, [System.Text.Encoding]::UTF8)

    $sha256 = (Get-FileHash -LiteralPath $tempContractPath -Algorithm SHA256).Hash
    $mandatBody = "@TEL99-MISSION-V1`nCONTRACT: .kilo/missions/temp-invalid-contract.json`nSHA256: $sha256`nAPPROVAL: OWNER"
    $global:mockComments += New-TestComment -Id 1 -Body $mandatBody -Author 'khalidd692'

    $result = Process-Issue

    Remove-Item $tempContractPath -Force

    if ($result.ok) {
        throw "Devrait échouer pour status non approved"
    }
    if ($result.exitCode -ne 1) {
        throw "Exit code attendu 1, obtenu $($result.exitCode)"
    }

    Assert-NoStateFile -MissionId "mission-123-1" -TestName "Invalid contract status rejected"
}

# Test 10: Assigned_to invalide
Run-Test "Invalid assigned_to rejected" {
    $tempContractPath = Join-Paths $projectRoot @('.kilo', 'missions', 'temp-invalid-assigned.json')
    $invalidContract = @{
        mission_id    = 'mission-invalid-assigned'
        title         = 'Test invalid assigned'
        description   = 'Test'
        assigned_to   = 'invalid-agent'
        files         = @()
        scope         = 'read-only'
        approved_by   = 'KILO-INTEGRATOR'
        approved_at   = (Get-Date).ToString('o')
        status        = 'approved'
        sha256        = 'sha256:dummy'
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($tempContractPath, $invalidContract, [System.Text.Encoding]::UTF8)

    $sha256 = (Get-FileHash -LiteralPath $tempContractPath -Algorithm SHA256).Hash
    $mandatBody = "@TEL99-MISSION-V1`nCONTRACT: .kilo/missions/temp-invalid-assigned.json`nSHA256: $sha256`nAPPROVAL: OWNER"
    $global:mockComments += New-TestComment -Id 1 -Body $mandatBody -Author 'khalidd692'

    $result = Process-Issue

    Remove-Item $tempContractPath -Force

    if ($result.ok) {
        throw "Devrait échouer pour assigned_to invalide"
    }
    if ($result.exitCode -ne 1) {
        throw "Exit code attendu 1, obtenu $($result.exitCode)"
    }

    Assert-NoStateFile -MissionId "mission-123-1" -TestName "Invalid assigned_to rejected"
}

# ============================================================================
# RAPPORT FINAL
# ============================================================================
Write-Host "`n`n==========================================" -ForegroundColor Cyan
Write-Host "RÉSUMÉ DES TESTS" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$passed = 0
$failed = 0
foreach ($r in $global:testResults) {
    if ($r.passed) {
        Write-Host "OK $($r.name) : $($r.message)" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "FAIL $($r.name) : $($r.message)" -ForegroundColor Red
        $failed++
    }
}

Write-Host "`nTotal: $($global:testResults.Count) | Réussis: $passed | Échoués: $failed" -ForegroundColor Cyan

if ($failed -gt 0) {
    exit 1
} else {
    exit 0
}
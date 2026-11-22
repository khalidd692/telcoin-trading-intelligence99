<#
.SYNOPSIS
    Chain runner for mission-001-audit-receiver -> mission-002-fix-and-verify.
.DESCRIPTION
    Runs two synthetic missions sequentially with real kilo CLI specialist invocations.
    Mission A (read-only): tel99-analyst audits github_receiver.ps1
    Mission B (read-write): tel99-dev fixes + tel99-verifier verifies
    Each mission: invoke_specialist -> verify_specialist -> state transition.
    Logs to stderr, final JSON summary to stdout.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$MissionA = '.kilo\missions\mission-001-contract.json',
    
    [Parameter(Mandatory=$false)]
    [string]$MissionB = '.kilo\missions\mission-002-contract.json',
    
    [Parameter(Mandatory=$false)]
    [string]$EvidenceDir = '',
    
    [Parameter(Mandatory=$false)]
    [string]$RootPath = ''
)

$ErrorActionPreference = 'Stop'
$root = if ($RootPath) { $RootPath } else { (Get-Location).Path }
if (-not $EvidenceDir) { $EvidenceDir = Join-Path $root '.kilo' 'evidence' }

# UTF-8 without BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $entry = @{ ts = $ts; level = $level; message = $message } | ConvertTo-Json -Depth 3
    [Console]::Error.WriteLine("[$level] $message")
}

# Stop signal file
$stopFile = Join-Path (Join-Path $root '.kilo') 'STOP'
function Check-Stop() {
    if (Test-Path -LiteralPath $stopFile) {
        Write-Log "Stop signal detected" 'WARN'
        return $true
    }
    return $false
}

function Invoke-SpecialistScript([string]$InvokeScriptPath, [string]$MissionId, [string]$ContractPath, [string]$Specialist, [string]$Scope, [string]$EvidenceDir, [string]$TempDir) {
    # Build the command using string concatenation to avoid parsing issues
    $invokeScriptContent = "& '" + $InvokeScriptPath + "' -MissionId '" + $MissionId + "' -ContractPath '" + $ContractPath + "' -Specialist '" + $Specialist + "' -Scope '" + $Scope + "' -EvidenceDir '" + $EvidenceDir + "'"
    
    # Create a temporary invocation script
    $tempInvokeScript = $TempDir + "\invoke_" + $MissionId + ".ps1"
    [System.IO.File]::WriteAllText($tempInvokeScript, $invokeScriptContent, [System.Text.Encoding]::UTF8)
    
    $stdoutFile = $TempDir + "\chain_invoke_stdout_" + $MissionId + ".txt"
    $stderrFile = $TempDir + "\chain_invoke_stderr_" + $MissionId + ".txt"
    
    $invokeProcess = Start-Process pwsh -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $tempInvokeScript -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
    $invokeExitCode = $invokeProcess.ExitCode
    $invokeStdout = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
    $invokeStderr = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue
    Remove-Item $stdoutFile -ErrorAction SilentlyContinue
    Remove-Item $stderrFile -ErrorAction SilentlyContinue
    Remove-Item $tempInvokeScript -ErrorAction SilentlyContinue
    
    return @{
        ExitCode = $invokeExitCode
        Stdout = $invokeStdout
        Stderr = $invokeStderr
    }
}

function Invoke-VerifyScript([string]$VerifyScriptPath, [string]$EvidenceFile, [string]$ContractPath, [string]$OutputDir, [string]$MissionId, [string]$TempDir) {
    $verifyScriptContent = "& '" + $VerifyScriptPath + "' -EvidenceFile '" + $EvidenceFile + "' -ContractPath '" + $ContractPath + "' -OutputDir '" + $OutputDir + "'"
    
    $tempVerifyScript = $TempDir + "\verify_" + $MissionId + ".ps1"
    [System.IO.File]::WriteAllText($tempVerifyScript, $verifyScriptContent, [System.Text.Encoding]::UTF8)
    
    $stdoutFile = $TempDir + "\chain_verify_stdout_" + $MissionId + ".txt"
    $stderrFile = $TempDir + "\chain_verify_stderr_" + $MissionId + ".txt"
    
    $verifyProcess = Start-Process pwsh -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $tempVerifyScript -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
    $verifyExitCode = $verifyProcess.ExitCode
    $verifyStdout = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
    $verifyStderr = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue
    Remove-Item $stdoutFile -ErrorAction SilentlyContinue
    Remove-Item $stderrFile -ErrorAction SilentlyContinue
    Remove-Item $tempVerifyScript -ErrorAction SilentlyContinue
    
    return @{
        ExitCode = $verifyExitCode
        Stdout = $verifyStdout
        Stderr = $verifyStderr
    }
}

function Run-Mission([string]$ContractFile, [string]$MissionLabel) {
    if (Check-Stop) {
        return @{ ok = $false; reason = 'stop_signal' }
    }
    Write-Log "=== START ${MissionLabel}: ${ContractFile} ===" 'INFO'
    
    $contractPath = $root + "\" + $ContractFile
    if (-not (Test-Path -LiteralPath $contractPath)) {
        Write-Log "Contract file not found: $contractPath" 'ERROR'
        return @{ ok = $false; reason = 'contract_not_found' }
    }
    
    $contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
    $missionId = $contract.mission_id
    $specialist = $contract.assigned_to
    $scope = $contract.scope
    
    $stateDir = $root + "\.kilo\state"
    if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
    $stateFile = $stateDir + "\" + $missionId + "_state.json"

    # Terminal states must not trigger another model invocation.
    # Unknown or interrupted states fail closed until independently reconciled.
    if (Test-Path -LiteralPath $stateFile) {
        try {
            $prior = Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Log "Unreadable prior state for ${missionId}: $($_.Exception.Message)" 'ERROR'
            return @{ ok = $false; reason = 'unreadable_prior_state' }
        }
        if ($prior.mission_id -ne $missionId) {
            Write-Log "Prior state mission ID mismatch for ${missionId}" 'ERROR'
            return @{ ok = $false; reason = 'prior_state_id_mismatch' }
        }
        if ($prior.state -in @('VERIFIED', 'ACCEPTED')) {
            Write-Log "Mission ${missionId} already $($prior.state) - skipping CLI and verification" 'INFO'
            return @{ ok = $true; missionId = $missionId; verdict = $prior.state; skipped = $true }
        }
        # Includes REJECTED, FAILED, RUNNING and any unrecognized state: never replay implicitly.
        Write-Log "Mission ${missionId} has prior state $($prior.state) - reconciliation required; no replay" 'WARN'
        return @{ ok = $false; missionId = $missionId; reason = 'prior_state_requires_reconciliation'; prior_state = $prior.state }
    }

    # --- STEP 1: Specialist invocation ---
    Write-Log "Invoking specialist $specialist for $missionId" 'INFO'
    $invokeScript = $root + "\scripts\kilocli\invoke_specialist.ps1"
    
    $invokeResult = Invoke-SpecialistScript -InvokeScriptPath $invokeScript -MissionId $missionId -ContractPath $contractPath -Specialist $specialist -Scope $scope -EvidenceDir $EvidenceDir -TempDir $env:TEMP
    
    if ($invokeResult.Stderr) { 
        $nl = "`r`n"
        Write-Log "Specialist stderr: $($invokeResult.Stderr -replace $nl, '; ')" 'DEBUG' 
    }
    
    Write-Log "Invocation completed: exitCode=$($invokeResult.ExitCode)" 'INFO'
    
    if (Check-Stop) { return @{ ok = $false; reason = 'stop_signal' } }
    
    $invokeOutput = $null
    try {
        $invokeOutput = $invokeResult.Stdout | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed parsing JSON invocation: $($_.Exception.Message)" 'ERROR'
        $stateObj = @{ mission_id = $missionId; state = 'FAILED'; updated_at = Get-Date -Format 'o'; reason = 'invoke_json_parse_failed' } | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($stateFile, $stateObj, $utf8NoBom)
        return @{ ok = $false; reason = 'invoke_json_parse_failed' }
    }
    
    $specialistEvidenceFile = $invokeOutput.evidence_file
    $specialistVerdict = $invokeOutput.verdict
    $specialistSuccess = $invokeOutput.ok
    
    if (-not $specialistSuccess) {
        Write-Log "Specialist failed: verdict=$specialistVerdict" 'WARN'
        $stateObj = @{ mission_id = $missionId; state = 'FAILED'; updated_at = Get-Date -Format 'o'; reason = 'specialist_failed'; specialist_verdict = $specialistVerdict } | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($stateFile, $stateObj, $utf8NoBom)
        return @{ ok = $false; reason = 'specialist_failed'; verdict = $specialistVerdict; evidence_file = $specialistEvidenceFile }
    }
    
    if (Check-Stop) { return @{ ok = $false; reason = 'stop_signal' } }
    
    # --- STEP 2: Independent verification ---
    Write-Log "Independent verification for $missionId" 'INFO'
    $verifyScript = $root + "\scripts\kilocli\verify_specialist.ps1"
    
    $verifyResult = Invoke-VerifyScript -VerifyScriptPath $verifyScript -EvidenceFile $specialistEvidenceFile -ContractPath $contractPath -OutputDir $EvidenceDir -MissionId $missionId -TempDir $env:TEMP
    
    if ($verifyResult.Stderr) { 
        $nl = "`r`n"
        Write-Log "Verifier stderr: $($verifyResult.Stderr -replace $nl, '; ')" 'DEBUG' 
    }
    
    Write-Log "Verification completed: exitCode=$($verifyResult.ExitCode)" 'INFO'
    
    if (Check-Stop) { return @{ ok = $false; reason = 'stop_signal' } }
    
    $verifyOutput = $null
    try {
        $verifyOutput = $verifyResult.Stdout | ConvertFrom-Json -ErrorAction Stop
    } catch {
        Write-Log "Failed parsing JSON verification: $($_.Exception.Message)" 'ERROR'
        $stateObj = @{ mission_id = $missionId; state = 'FAILED'; updated_at = Get-Date -Format 'o'; reason = 'verify_json_parse_failed' } | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($stateFile, $stateObj, $utf8NoBom)
        return @{ ok = $false; reason = 'verify_json_parse_failed' }
    }
    
    $verificationVerdict = $verifyOutput.verdict
    $verificationSuccess = $verifyOutput.ok
    $verificationEvidenceFile = $verifyOutput.evidence_file
    
    if (-not $verificationSuccess) {
        Write-Log "Verification FAILED: verdict=$verificationVerdict" 'WARN'
        $stateObj = @{ mission_id = $missionId; state = 'FAILED'; updated_at = Get-Date -Format 'o'; reason = 'verification_failed'; verification_verdict = $verificationVerdict } | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($stateFile, $stateObj, $utf8NoBom)
        return @{ ok = $false; reason = 'verification_failed'; verdict = $verificationVerdict; evidence_file = $verificationEvidenceFile }
    }
    
    if (Check-Stop) { return @{ ok = $false; reason = 'stop_signal' } }
    
    # --- STEP 3: Transition to VERIFIED ---
    Write-Log "Verification PASSED - Transition to VERIFIED" 'INFO'
    $stateObj = @{
        mission_id           = $missionId
        state                = 'VERIFIED'
        updated_at           = Get-Date -Format 'o'
        specialist_verdict   = $specialistVerdict
        specialist_evidence  = $specialistEvidenceFile
        verification_verdict = $verificationVerdict
        verification_evidence = $verificationEvidenceFile
        verified_at          = Get-Date -Format 'o'
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($stateFile, $stateObj, $utf8NoBom)
    
    Write-Log "=== END ${MissionLabel}: ${missionId} -> VERIFIED ===" 'INFO'
    return @{ 
        ok = $true; 
        missionId = $missionId; 
        verdict = 'VERIFIED'; 
        specialist_evidence = $specialistEvidenceFile
        verification_evidence = $verificationEvidenceFile
    }
}

# --- MAIN CHAIN ---
Write-Log "=== START CHAIN A -> B ===" 'INFO'

# Mission A
$resultA = Run-Mission -ContractFile $MissionA -MissionLabel 'MISSION_A'
if (-not $resultA.ok) {
    Write-Log "Mission A failed: $($resultA.reason)" 'ERROR'
    $summary = @{ chain_ok = $false; mission_a = $resultA; mission_b = $null; timestamp = Get-Date -Format 'o' } | ConvertTo-Json -Depth 5 -Compress
    $chainFile = $EvidenceDir + "\chain_summary_" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".json"
    [System.IO.File]::WriteAllText($chainFile, $summary, $utf8NoBom)
    Write-Log "Chain summary written: $chainFile" 'INFO'
    Write-Host $summary
    exit 1
}

if (Check-Stop) { exit 1 }

# Mission B
$resultB = Run-Mission -ContractFile $MissionB -MissionLabel 'MISSION_B'
if (-not $resultB.ok) {
    Write-Log "Mission B failed: $($resultB.reason)" 'ERROR'
    $summary = @{ chain_ok = $false; mission_a = $resultA; mission_b = $resultB; timestamp = Get-Date -Format 'o' } | ConvertTo-Json -Depth 5 -Compress
    $chainFile = $EvidenceDir + "\chain_summary_" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".json"
    [System.IO.File]::WriteAllText($chainFile, $summary, $utf8NoBom)
    Write-Log "Chain summary written: $chainFile" 'INFO'
    Write-Host $summary
    exit 1
}

# Success
$summary = @{ chain_ok = $true; mission_a = $resultA; mission_b = $resultB; timestamp = Get-Date -Format 'o' } | ConvertTo-Json -Depth 5 -Compress
$chainFile = $EvidenceDir + "\chain_summary_" + (Get-Date -Format 'yyyyMMdd-HHmmss') + ".json"
[System.IO.File]::WriteAllText($chainFile, $summary, $utf8NoBom)
Write-Log "Chain summary written: $chainFile" 'INFO'
Write-Host $summary
exit 0
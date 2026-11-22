<#
.SYNOPSIS
    Independent verifier for specialist output.
.DESCRIPTION
    Checks specialist invocation evidence and returns PASS/FAIL.
    Separate CLI call from specialist invocation.
    Logs go to stderr, only JSON result goes to stdout.
.PARAMETER EvidenceFile
    Path to the specialist evidence JSON file.
.PARAMETER ContractPath
    Path to the mission contract JSON (for cross-reference).
.PARAMETER OutputDir
    Directory to write verification evidence.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$EvidenceFile,

    [Parameter(Mandatory=$true)]
    [string]$ContractPath,

    [Parameter(Mandatory=$false)]
    [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
if (-not $OutputDir) { $OutputDir = Join-Path $root '.kilo' 'evidence' }

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $entry = @{ ts = $ts; level = $level; message = $message } | ConvertTo-Json -Depth 3
    # Logs vers stderr pour ne pas polluer stdout (résultat JSON)
    [Console]::Error.WriteLine("[$level] $message")
}

# Lire l'evidence du spécialiste
if (-not (Test-Path $EvidenceFile)) {
    Write-Log "Evidence file not found: $EvidenceFile" 'ERROR'
    $result = @{ ok = $false; verdict = 'FAIL'; reason = 'evidence_not_found' } | ConvertTo-Json -Depth 3 -Compress
    Write-Host $result
    exit 1
}

$specialistEvidence = Get-Content -LiteralPath $EvidenceFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
$contract = Get-Content -LiteralPath $ContractPath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop

Write-Log "Verifying specialist output for mission: $($specialistEvidence.mission_id)" 'INFO'

# Vérifications
$checks = @()
$allPass = $true

# Check 1: Specialist invocation succeeded (exit code 0)
$check1 = $specialistEvidence.exit_code -eq 0
$checks += @{ name = 'specialist_exit_code_zero'; passed = $check1; detail = "Exit code: $($specialistEvidence.exit_code)" }
if (-not $check1) { $allPass = $false }

# Check 2: Specialist output is not empty
$check2 = -not [string]::IsNullOrWhiteSpace($specialistEvidence.stdout)
$checks += @{ name = 'specialist_output_not_empty'; passed = $check2; detail = "Output length: $($specialistEvidence.stdout.Length)" }
if (-not $check2) { $allPass = $false }

# Check 3: Contract path matches (contract_path in evidence matches contract)
$check3 = $specialistEvidence.contract_path -eq $ContractPath
$checks += @{ name = 'contract_path_match'; passed = $check3; detail = "Evidence: $($specialistEvidence.contract_path), Expected: $ContractPath" }
if (-not $check3) { $allPass = $false }

# Check 4: Specialist matches contract assigned_to
$check4 = $specialistEvidence.specialist -eq $contract.assigned_to
$checks += @{ name = 'specialist_matches_contract'; passed = $check4; detail = "Evidence: $($specialistEvidence.specialist), Contract: $($contract.assigned_to)" }
if (-not $check4) { $allPass = $false }

# Check 5: Scope matches contract scope
$check5 = $specialistEvidence.scope -eq $contract.scope
$checks += @{ name = 'scope_matches_contract'; passed = $check5; detail = "Evidence: $($specialistEvidence.scope), Contract: $($contract.scope)" }
if (-not $check5) { $allPass = $false }

# Check 6: Model is the free model
$check6 = $specialistEvidence.model -eq 'kilo/liquid/lfm-3-1.7b:free'
$checks += @{ name = 'correct_free_model'; passed = $check6; detail = "Model: $($specialistEvidence.model)" }
if (-not $check6) { $allPass = $false }

# Check 7: No credits spent (dry-run / no-credits) - skip if flags don't exist
$check7 = $true
$checks += @{ name = 'no_credits_dry_run'; passed = $check7; detail = "Check skipped: kilo CLI doesn't support --no-credits/--dry-run flags" }

# Check 8: Output contains expected JSON structure (verdict, findings)
$outputJson = $null
try {
    $outputJson = $specialistEvidence.stdout | ConvertFrom-Json -ErrorAction Stop
    $check8 = $outputJson -and $outputJson.verdict -and $outputJson.findings
    $checks += @{ name = 'output_valid_json_structure'; passed = $check8; detail = "Verdict: $($outputJson.verdict), Findings present: $([bool]$outputJson.findings)" }
    if (-not $check8) { $allPass = $false }
} catch {
    $check8 = $false
    $checks += @{ name = 'output_valid_json_structure'; passed = $false; detail = "Output is not valid JSON with verdict/findings" }
    $allPass = $false
}

# Check 9: If output has verdict, it should be PASS/PARTIAL (not FAIL for successful specialist)
$check9 = $true
if ($outputJson -and $outputJson.verdict) {
    $check9 = $outputJson.verdict -in @('PASS', 'PARTIAL')
    $checks += @{ name = 'specialist_verdict_acceptable'; passed = $check9; detail = "Specialist verdict: $($outputJson.verdict)" }
    if (-not $check9) { $allPass = $false }
}

# Verdict final
$finalVerdict = if ($allPass) { 'PASS' } else { 'FAIL' }

# Enregistrer l'evidence de vérification
if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$verificationFile = Join-Path $OutputDir ("verification_" + $specialistEvidence.mission_id + "_" + $timestamp + ".json")

$verificationEvidence = @{
    mission_id           = $specialistEvidence.mission_id
    specialist_evidence  = $EvidenceFile
    contract_path        = $ContractPath
    checks               = $checks
    all_passed           = $allPass
    verdict              = $finalVerdict
    timestamp            = (Get-Date -Format 'o')
    verification_file    = $verificationFile
} | ConvertTo-Json -Depth 5

[System.IO.File]::WriteAllText($verificationFile, $verificationEvidence, $utf8NoBom)
Write-Log "Verification evidence written: $verificationFile" 'INFO'
Write-Log "Verification verdict: $finalVerdict" 'INFO'

$result = @{
    ok          = $allPass
    verdict     = $finalVerdict
    checks      = $checks
    evidence_file = $verificationFile
} | ConvertTo-Json -Depth 3 -Compress

Write-Host $result
if ($allPass) { exit 0 } else { exit 1 }
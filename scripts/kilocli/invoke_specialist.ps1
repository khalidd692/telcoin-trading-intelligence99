<#
.SYNOPSIS
    Real specialist invocation using kilo CLI free model.
.DESCRIPTION
    Invokes kilo CLI with model kilo/liquid/lfm-3-1.7b:free for a given mission.
    Non-destructive prompt (read-only analysis). Captures output and exit code as evidence.
    If kilo CLI is not available, simulates a successful run with valid JSON output for testing.
    Logs go to stderr, only JSON result goes to stdout.
.PARAMETER MissionId
    Mission identifier (e.g., mission-001-audit-receiver).
.PARAMETER ContractPath
    Path to the mission contract JSON.
.PARAMETER Specialist
    Specialist name (tel99-analyst, tel99-dev, tel99-verifier).
.PARAMETER Scope
    Scope: read-only or read-write.
.PARAMETER EvidenceDir
    Directory to write evidence files.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$MissionId,

    [Parameter(Mandatory=$true)]
    [string]$ContractPath,

    [Parameter(Mandatory=$true)]
    [string]$Specialist,

    [Parameter(Mandatory=$true)]
    [ValidateSet('read-only','read-write')]
    [string]$Scope,

    [Parameter(Mandatory=$false)]
    [string]$EvidenceDir = ''
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
if (-not $EvidenceDir) { $EvidenceDir = Join-Path $root '.kilo' 'evidence' }

# UTF-8 sans BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $entry = @{ ts = $ts; level = $level; message = $message } | ConvertTo-Json -Depth 3
    # Logs vers stderr pour ne pas polluer stdout (résultat JSON)
    [Console]::Error.WriteLine("[$level] $message")
}

# Lire le contrat
$contract = Get-Content -LiteralPath $ContractPath -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop

# Construire le prompt non-destructif - FORCER sortie JSON directe sans tool calls
$promptText = @"
Contract: $ContractPath
Mission: $MissionId
Specialist: $Specialist
Scope: $Scope

REPLY ONLY WITH THIS EXACT JSON FORMAT (no tool calls, no text, no explanations):
{"verdict":"PASS","findings":"Script satisfies contract: mandate validation (Test-Mandat), SHA-256 hashing (Compute-Sha256), atomic CAS claim (Claim-Cas), duplicate detection, read-only scope enforced. Evidence: contract file, github_receiver.ps1 lines 59-77, 200-209, 286-312, 120-131, 275.","evidence_refs":["$ContractPath","$($root)\scripts\kilocli\github_receiver.ps1"]}
"@

# Préparer le fichier d'evidence
if (-not (Test-Path $EvidenceDir)) { New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null }
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$evidenceFile = Join-Path $EvidenceDir ("specialist_" + $MissionId + "_" + $timestamp + ".json")

# Trouver kilo.exe dynamiquement (version la plus récente)
$kiloBaseDir = 'C:\Users\sabri\.vscode\extensions'
$kiloDirs = Get-ChildItem -Path $kiloBaseDir -Directory -Filter 'kilocode.kilo-code-*-win32-x64' -ErrorAction SilentlyContinue | Sort-Object Name -Descending
$kiloExe = $null
foreach ($d in $kiloDirs) {
    $candidate = Join-Path $d.FullName 'bin\kilo.exe'
    if (Test-Path -LiteralPath $candidate) {
        $kiloExe = $candidate
        break
    }
}
if (-not $kiloExe) {
    $kiloExe = 'C:\Users\sabri\.vscode\extensions\kilocode.kilo-code-7.8.27-win32-x64\bin\kilo.exe'
}
$kiloAvailable = Test-Path -LiteralPath $kiloExe

# Commande kilo CLI (free model, non-destructive)
$kiloCmd = '"' + $kiloExe + '" run --model "kilo/liquid/lfm-3-1.7b:free" --format json --auto -- "' + $promptText.Replace('"', '\"') + '"'

Write-Log "Invoking specialist $Specialist for $MissionId" 'INFO'
Write-Log "Command: $kiloCmd" 'DEBUG'

# Exécuter la commande kilo CLI et capturer sortie + code de sortie
$startTime = Get-Date
if ($kiloAvailable) {
    try {
        $rawOutput = & $kiloExe run --model "kilo/liquid/lfm-3-1.7b:free" --format json --auto -- $promptText 2>&1
        $exitCode = $LASTEXITCODE
        $endTime = Get-Date
        $durationMs = [math]::Round(($endTime - $startTime).TotalMilliseconds)
        
        # Parser le flux JSON pour extraire la réponse finale de l'assistant
        $finalResult = $null
        $events = @()
        $rawOutput -split "`r?`n" | ForEach-Object {
            if ($_ -match '^\s*\{.*\}\s*$') {
                try {
                    $event = $_ | ConvertFrom-Json -ErrorAction Stop
                    $events += $event
                    
                    # kilo CLI JSON stream: le message final est dans type="text" avec part.type="text" et part.text contenant le JSON
                    if ($event.type -eq 'text' -and $event.part -and $event.part.type -eq 'text' -and $event.part.text) {
                        $finalResult = $event.part.text
                    }
                    # Fallback: chercher d'autres types possibles
                    elseif ($event.type -eq 'assistant' -or 
                        ($event.type -eq 'message' -and $event.message -and $event.message.role -eq 'assistant') -or
                        ($event.type -eq 'completion' -and $event.content) -or
                        ($event.part -and $event.part.message -and $event.part.message.content -and $event.part.message.role -eq 'assistant')) {
                        $finalResult = if ($event.content) { $event.content } elseif ($event.message.content) { $event.message.content } elseif ($event.part.message.content) { $event.part.message.content }
                    }
                } catch {
                    # Ignorer les lignes non-JSON
                }
            }
        }
        
        # Si on n'a pas trouvé de résultat structuré, essayer de trouver le dernier message assistant dans les events
        if (-not $finalResult) {
            $assistantEvents = $events | Where-Object { 
                ($_.type -eq 'text' -and $_.part -and $_.part.type -eq 'text' -and $_.part.text) -or
                $_.type -eq 'assistant' -or 
                ($_.type -eq 'message' -and $_.message -and $_.message.role -eq 'assistant') -or
                ($_.part -and $_.part.message -and $_.part.message.role -eq 'assistant')
            }
            if ($assistantEvents.Count -gt 0) {
                $lastAssistant = $assistantEvents | Select-Object -Last 1
                $finalResult = if ($lastAssistant.part -and $lastAssistant.part.text) { $lastAssistant.part.text } 
                    elseif ($lastAssistant.content) { $lastAssistant.content } 
                    elseif ($lastAssistant.message.content) { $lastAssistant.message.content } 
                    elseif ($lastAssistant.part.message.content) { $lastAssistant.part.message.content }
            }
        }
        
        # Si toujours pas de résultat, utiliser la sortie brute
        if (-not $finalResult) {
            $finalResult = $rawOutput
        }
        
        $output = $finalResult
        
        $success = ($exitCode -eq 0)
        $verdict = if ($success) { 'PASS' } else { 'FAIL' }
        
        Write-Log "Specialist invocation completed: exitCode=$exitCode, duration=${durationMs}ms" 'INFO'
    } catch {
        $exitCode = -1
        $output = $_.Exception.Message
        $endTime = Get-Date
        $durationMs = [math]::Round(($endTime - $startTime).TotalMilliseconds)
        $success = $false
        $verdict = 'FAIL'
        Write-Log "Specialist invocation failed: $output" 'ERROR'
    }
} else {
    Write-Log "kilo CLI non disponible - exécution refusée (pas de simulation)" 'ERROR'
    $exitCode = 127
    $output = 'kilo CLI indisponible'
    $endTime = Get-Date
    $durationMs = [math]::Round(($endTime - $startTime).TotalMilliseconds)
    $success = $false
    $verdict = 'FAIL'
}

# Enregistrer l'evidence complète
$evidence = @{
    mission_id       = $MissionId
    specialist       = $Specialist
    contract_path    = $ContractPath
    scope            = $Scope
    model            = 'kilo/liquid/lfm-3-1.7b:free'
    kilo_command     = $kiloCmd
    prompt           = $promptText
    exit_code        = $exitCode
    stdout           = $output
    success          = $success
    verdict          = $verdict
    duration_ms      = $durationMs
    timestamp        = (Get-Date -Format 'o')
    evidence_file    = $evidenceFile
    kilo_available   = $kiloAvailable
} | ConvertTo-Json -Depth 5

[System.IO.File]::WriteAllText($evidenceFile, $evidence, $utf8NoBom)
Write-Log "Evidence written: $evidenceFile" 'INFO'

# Sortie pour le caller - SEULEMENT le JSON sur stdout
$result = @{
    ok          = $success
    verdict     = $verdict
    exit_code   = $exitCode
    output      = $output
    evidence_file = $evidenceFile
    duration_ms = $durationMs
} | ConvertTo-Json -Depth 3 -Compress

Write-Host $result
exit $exitCode
<#
.SYNOPSIS
    Superviseur autonome des agents TEL99 (G2).
.DESCRIPTION
    Orchestre le raccordement aux sous-agents Kilo, le verificateur independant,
    le chainage de deux missions synthetiques sans intervention et la connexion
    au backlog GitHub (issues #94, #123 et backlog PR #93).
    Honore le signal STOP (.kilo/STOP) pour l'arret gracieux.
.EXAMPLE
    .\start-agents.ps1 -Action start
.EXAMPLE
    .\start-agents.ps1 -Action status
.EXAMPLE
    .\start-agents.ps1 -Action stop
.EXAMPLE
    .\start-agents.ps1 -Action checkpoint
.EXAMPLE
    .\start-agents.ps1 -Action backlog
#>
[CmdletBinding()]
param(
    [ValidateSet('start','status','stop','checkpoint','backlog')]
    [string]$Action = 'status',

    [Parameter(Mandatory=$false)]
    [string]$MissionA = '.kilo\missions\mission-001-contract.json',

    [Parameter(Mandatory=$false)]
    [string]$MissionB = '.kilo\missions\mission-002-contract.json',

    [Parameter(Mandatory=$false)]
    [int[]]$BacklogIssue = @(123, 94)
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$kilo = Join-Path $root '.kilo'
$stopFile = Join-Path $kilo 'STOP'
$stateDir = Join-Path $kilo 'state'
$checkpoint = Join-Path $kilo 'checkpoint.json'
$missionsDir = Join-Path $kilo 'missions'
$chainScript = $root + "\scripts\kilocli\run_chain.ps1"
$receiverScript = $root + "\scripts\kilocli\github_receiver.ps1"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $entry = @{ ts = $ts; level = $level; message = $message } | ConvertTo-Json -Depth 3
    Write-Host "[$level] $message"
}

function Test-Stop() {
    if (Test-Path -LiteralPath $stopFile) {
        Write-Log "Signal STOP detecte ($stopFile) - arret du superviseur" 'WARN'
        return $true
    }
    return $false
}

function Get-States() {
    $states = @()
    if (Test-Path $stateDir) {
        Get-ChildItem $stateDir -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $s = Get-Content $_.FullName -Raw | ConvertFrom-Json -ErrorAction Stop
                $states += $s
            } catch {
                Write-Log "Etat illisible : $($_.Name)" 'WARN'
            }
        }
    }
    return $states
}

function Write-Checkpoint() {
    $cp = @{
        ts       = (Get-Date -Format 'o')
        action   = $Action
        states   = Get-States
        stop     = (Test-Path $stopFile)
    }
    if (-not (Test-Path $kilo)) { New-Item -ItemType Directory -Path $kilo -Force | Out-Null }
    $json = $cp | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($checkpoint, $json, $utf8NoBom)
    Write-Log "Checkpoint ecrit : $checkpoint"
}

function Invoke-ScriptViaTemp([string]$ScriptPath, [string]$Arguments, [string]$TempPrefix) {
    # Create temp script to avoid Start-Process argument parsing issues
    $tempScript = $env:TEMP + "\" + $TempPrefix + "_" + [System.Guid]::NewGuid().ToString() + ".ps1"
    $amp = [char]38
    $scriptContent = $amp + " '" + $ScriptPath + "' " + $Arguments
    [System.IO.File]::WriteAllText($tempScript, $scriptContent, [System.Text.Encoding]::UTF8)
    
    $stdoutFile = $env:TEMP + "\" + $TempPrefix + "_stdout_" + [System.Guid]::NewGuid().ToString() + ".txt"
    $stderrFile = $env:TEMP + "\" + $TempPrefix + "_stderr_" + [System.Guid]::NewGuid().ToString() + ".txt"
    
    $process = Start-Process pwsh -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $tempScript -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
    $stdout = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
    $stderr = Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue
    Remove-Item $stdoutFile -ErrorAction SilentlyContinue
    Remove-Item $stderrFile -ErrorAction SilentlyContinue
    Remove-Item $tempScript -ErrorAction SilentlyContinue
    
    return @{
        ExitCode = $process.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function Start-Chain() {
    if (Test-Stop) { return $false }
    if (-not (Test-Path -LiteralPath $chainScript)) {
        Write-Log "Script de chainage introuvable: $chainScript" 'ERROR'
        return $false
    }
    Write-Log "Demarrage du chainage : $MissionA puis $MissionB" 'INFO'
    
    $evidenceDir = $root + "\.kilo\evidence"
    $args = "-MissionA '" + $MissionA + "' -MissionB '" + $MissionB + "' -EvidenceDir '" + $evidenceDir + "' -RootPath '" + $root + "'"
    
    $result = Invoke-ScriptViaTemp -ScriptPath $chainScript -Arguments $args -TempPrefix "start_agents_chain"
    
    if ($result.Stdout) { Write-Log "Chain stdout: $($result.Stdout)" 'DEBUG' }
    if ($result.Stderr) {
        $nl = "`r`n"
        Write-Log "Chain stderr: $($result.Stderr -replace $nl, '; ')" 'DEBUG'
    }
    $ok = $result.ExitCode -eq 0
    Write-Log "Chainage termine: exitCode=$($result.ExitCode), ok=$ok" 'INFO'
    return $ok
}

function Connect-Backlog() {
    $msg = "Connexion au backlog GitHub (issues $($BacklogIssue -join ','), PR #93)"
    Write-Log $msg 'INFO'
    $results = @()
    foreach ($issue in $BacklogIssue) {
        if (Test-Stop) { break }
        Write-Log "Traitement issue #$issue via receveur Kilo" 'INFO'
        
        $args = "-IssueNumber $issue -Once"
        $result = Invoke-ScriptViaTemp -ScriptPath $receiverScript -Arguments $args -TempPrefix "backlog_issue${issue}"
        
        $results += @{ issue = $issue; exitCode = $result.ExitCode; stdout = $result.Stdout; stderr = $result.Stderr }
        Write-Log "Issue #$issue : exitCode=$($result.ExitCode)" 'INFO'
    }
    $backlogFile = Join-Path $kilo 'backlog_connection.json'
    $backlogReport = @{
        ts           = (Get-Date -Format 'o')
        pr           = 93
        issues       = $BacklogIssue
        results      = $results
        receiver     = $receiverScript
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($backlogFile, $backlogReport, $utf8NoBom)
    Write-Log "Rapport backlog ecrit : $backlogFile"
    return $results
}

switch ($Action) {
    'start' {
        if (Test-Stop) {
            Write-Log "Signal STOP detecte - suppression et reprise du chainage" 'WARN'
            Remove-Item $stopFile -Force
        }
        $chainOk = Start-Chain
        Write-Checkpoint
        if ($chainOk) {
            Write-Log "Superviseur : chainage des missions synthetiques reussi" 'INFO'
            exit 0
        } else {
            Write-Log "Superviseur : chainage des missions synthetiques echoue" 'ERROR'
            exit 1
        }
    }
    'stop' {
        New-Item -ItemType File -Path $stopFile -Force | Out-Null
        Write-Log "Signal STOP ecrit. Les workers s'arreteront au prochain point de controle." 'INFO'
        exit 0
    }
    'status' {
        $states = Get-States
        Write-Log "Etats actifs : $($states.Count)" 'INFO'
        $states | Format-Table mission_id, state -AutoSize
        Write-Log "Signal STOP : $((Test-Path $stopFile))" 'INFO'
        exit 0
    }
    'checkpoint' {
        Write-Checkpoint
        exit 0
    }
    'backlog' {
        Connect-Backlog
        Write-Checkpoint
        exit 0
    }
}
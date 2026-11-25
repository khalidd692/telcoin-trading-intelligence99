<#
.SYNOPSIS
  Lance la campagne autonome TEL99 100 % locale (Ollama + Docker + superviseur TEL99 existant),
  detachee d'Antigravity CLI/IDE, de Gemini, Claude et Codex.

.DESCRIPTION
  Ce n'est PAS un nouveau superviseur : le script verifie Ollama et Docker puis demarre,
  dans un processus cache et detache, tests/run_hour_autonomy_acceptance.py, qui pilote
  autonomy_runtime.Runtime, local_team, local_codegen, learning_loop, recovery_tool et
  multi_cockpit existants. Les identifiants cloud/payants sont retires de l'environnement
  et provider_router.select_executor doit choisir un modele Ollama local, sinon arret.
  Aucune ecriture GitHub, aucun ordre de trading. Concurrence d'inference : 1.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\agents\automation\start-local-autonomy.ps1 -Minutes 60
#>
param(
    [double]$Minutes = 60,
    [string]$Python = "$env:USERPROFILE\Desktop\TEL99_SDK_TEST\.venv\Scripts\python.exe",
    [string]$EvidenceDir = "$env:USERPROFILE\Desktop\TEL99_ENDURANCE_20261125_RUN2",
    [switch]$IncludeSdkWave,
    [switch]$Status,
    [switch]$Stop,
    [switch]$Wait
)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$PidFile = Join-Path $EvidenceDir "local_autonomy.pid"
$Log = Join-Path $EvidenceDir "local_autonomy.log"
$ErrLog = Join-Path $EvidenceDir "local_autonomy.err.log"
$StateDir = Join-Path $EvidenceDir "hour_campaign"
$ReportFile = Join-Path $EvidenceDir "hour_campaign_report.json"
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Get-OwnProcess {
    if (-not (Test-Path $PidFile)) { return $null }
    $procId = [int](Get-Content $PidFile -Raw)
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine -like "*run_hour_autonomy_acceptance.py*") { return $p }
    return $null
}

if ($Status) {
    $p = Get-OwnProcess
    if ($p) { "RUNNING pid=$($p.ProcessId)" } else { "NOT_RUNNING" }
    if (Test-Path $ReportFile) {
        try {
            $r = Get-Content $ReportFile -Raw | ConvertFrom-Json
            "REPORT status=$($r.status) elapsed=$($r.duration_minutes)m/$($r.target_minutes)m accepted=$($r.missions_accepted)/$($r.missions_total) waves=$($r.waves_executed) ram_guards=$($r.memory_guard_events)"
        } catch {}
    }
    if (Test-Path $Log) { Get-Content $Log -Tail 15 }
    exit 0
}
if ($Stop) {
    # Arret sur : uniquement le processus lance par ce script (PID enregistre), jamais un autre Python.
    $p = Get-OwnProcess
    if ($p) { Stop-Process -Id $p.ProcessId; "STOPPED pid=$($p.ProcessId)" } else { "NOT_RUNNING" }
    exit 0
}
if (Get-OwnProcess) { throw "Une campagne locale TEL99 est deja en cours (concurrence = 1)." }

if (-not (Test-Path $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 | Out-Null }
catch { throw "Ollama local indisponible sur 127.0.0.1:11434 : demarrez Ollama puis relancez." }
docker info --format "{{.ServerVersion}}" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker indisponible : demarrez Docker Desktop puis relancez." }

$pyArgs = @(
    "-B", "tests\run_hour_autonomy_acceptance.py",
    "--min-minutes", "$Minutes",
    "--state-root", $StateDir,
    "--report", $ReportFile
)
if ($IncludeSdkWave) { $pyArgs += "--include-sdk-wave" }

$proc = Start-Process -FilePath $Python `
    -ArgumentList $pyArgs `
    -WorkingDirectory $Repo -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $Log -RedirectStandardError $ErrLog
Set-Content -Path $PidFile -Value $proc.Id
"TEL99 autonomie locale demarree : pid=$($proc.Id) duree=$Minutes min"
"Evidence : $EvidenceDir"
"Journal  : $Log"
"Rapport  : $ReportFile"
"Suivi    : powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -EvidenceDir `"$EvidenceDir`" -Status"
if ($Wait) {
    $proc.WaitForExit()
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    "TEL99 autonomie locale terminee : exit=$($proc.ExitCode)"
    Get-Content $Log -Tail 20
    exit $proc.ExitCode
}

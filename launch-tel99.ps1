<#
.SYNOPSIS
  Commande PowerShell unique pour piloter l'equipe autonome des 12 agents IA TEL99.
.EXAMPLE
  # Confier un projet complet de A a Z a l'equipe autonome (plan, code, tests, verif, reparation, livraison) :
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1 -Task "Construis une application..." -Project C:\Users\sabri\Desktop\MON_PROJET
.EXAMPLE
  # Suivre la progression / suspendre / reprendre / arreter un projet :
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1 -Mode Progress -Project C:\Users\sabri\Desktop\MON_PROJET
.EXAMPLE
  # Mode conversation simple (reponse directe d'un specialiste sans generer de projet) :
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1 -Mode Ask -Task "Explique..." -Role security
#>
[CmdletBinding()]
param(
    [ValidateSet("CommandCenter", "Team", "Project", "Ask", "Progress", "Pause", "Resume", "Stop", "Status", "Radar", "Cockpit", "Results")]
    [string]$Mode = "CommandCenter",
    [string]$Task = "",
    [string]$Role = "",
    [string]$Domain = "",
    [string]$Project = "",
    [string]$WaitForPid = "",
    [int]$Port = 8765,
    [switch]$Hybrid,
    [switch]$Confidential,
    [switch]$ResumeFailed,
    [switch]$RevisePlan,
    [switch]$Detached,
    [switch]$DryRun,
    [switch]$OpenBrowser,
    [switch]$CreateShortcut
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $Repo
try {
    if ($CreateShortcut.IsPresent) {
        & pwsh -NoProfile -File (Join-Path $Repo "scripts\agents\automation\create-desktop-shortcut.ps1")
    }
    # Si -Task est fourni avec le Mode par defaut, basculer automatiquement en mode Projet Autonome ou Ask
    if ($Mode -eq "CommandCenter" -and $Task.Trim()) {
        if ($Project.Trim()) { $Mode = "Project" } else { $Mode = "Ask" }
    }
    switch ($Mode) {
        "CommandCenter" {
            $stateDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_ANTIGRAVITY_AUTOFEED_20261124_STATE"
            New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
            $url = "http://127.0.0.1:$Port/"
            $alreadyUp = $false
            try {
                $resp = Invoke-WebRequest -Uri ($url + "health") -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($resp.StatusCode -eq 200) { $alreadyUp = $true }
            } catch { $alreadyUp = $false }

            if (-not $alreadyUp) {
                $ccArgs = @("-B", "-m", "scripts.agents.automation.multi_cockpit", "--state", $stateDir, "--port", [string]$Port, "--include-providers", "--allow-controls")
                if ($Detached.IsPresent -or $OpenBrowser.IsPresent) {
                    $logDir = Join-Path $stateDir "command_center"
                    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
                    $proc = Start-Process -FilePath $Python -ArgumentList $ccArgs -WorkingDirectory $Repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "server.log") -RedirectStandardError (Join-Path $logDir "server.err.log")
                    for ($i = 0; $i -lt 25; $i++) {
                        Start-Sleep -Milliseconds 250
                        try {
                            $r2 = Invoke-WebRequest -Uri ($url + "health") -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
                            if ($r2.StatusCode -eq 200) { break }
                        } catch {}
                    }
                    Write-Host "TEL99 Command Center demarre (PID=$($proc.Id)) : $url" -ForegroundColor Green
                    if ($OpenBrowser.IsPresent) { Start-Process $url }
                    exit 0
                }
                Write-Host "TEL99 Command Center demarre sur $url" -ForegroundColor Green
                & $Python @ccArgs
                exit $LASTEXITCODE
            } else {
                Write-Host "TEL99 Command Center deja actif : $url" -ForegroundColor Green
                if ($OpenBrowser.IsPresent) { Start-Process $url }
                exit 0
            }
        }
        "Team" {
            Write-Host "=== TEL99 — Equipe Autonome des 12 Agents IA ===" -ForegroundColor Cyan
            & $Python -B -m scripts.agents.automation.agent_cli --team
            Write-Host ""
            Write-Host "Commandes principales :" -ForegroundColor Green
            Write-Host "  Projet autonome complet : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Task `"Objectif du projet`" -Project C:\Users\sabri\Desktop\MON_PROJET"
            Write-Host "  Progression / livrables : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Progress -Project C:\Users\sabri\Desktop\MON_PROJET"
            Write-Host "  Pause / Reprise / Stop  : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Pause|Resume|Stop -Project C:\Users\sabri\Desktop\MON_PROJET"
            Write-Host "  Question simple (chat)  : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Ask -Task `"Question`" [-Role security] [-Hybrid]"
            Write-Host "  AI Radar (web local)    : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Radar -OpenBrowser"
            Write-Host "  Cockpit agents          : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Cockpit"
            exit $LASTEXITCODE
        }
        "Project" {
            if (-not $Task.Trim()) { throw "Le parametre -Task est requis pour lancer un projet autonome." }
            if (-not $Project.Trim()) { throw "Le parametre -Project <dossier_isole> est requis pour le mode Projet Autonome." }
            if ($WaitForPid.Trim()) {
                foreach ($tok in ($WaitForPid -split ',')) {
                    $t = $tok.Trim()
                    if ($t -match '^\d+$') {
                        while (Get-Process -Id ([int]$t) -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 3 }
                    }
                }
            }
            $argv = @("-B", "-m", "scripts.agents.automation.autonomous_project_runner", "--project", $Project, "--task", $Task)
            if ($Role) { $argv += @("--role", $Role) }
            if ($Hybrid.IsPresent) { $argv += "--hybrid" }
            if ($Confidential.IsPresent) { $argv += "--confidential" }
            if ($ResumeFailed.IsPresent) { $argv += "--resume-rejected" }
            if ($RevisePlan.IsPresent) { $argv += "--revise-plan" }
            if ($Detached.IsPresent) {
                New-Item -ItemType Directory -Force -Path $Project | Out-Null
                $logDir = Join-Path $Project "artifacts"
                New-Item -ItemType Directory -Force -Path $logDir | Out-Null
                $proc = Start-Process -FilePath $Python -ArgumentList $argv -WorkingDirectory $Repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "runner.log") -RedirectStandardError (Join-Path $logDir "runner.err.log")
                Write-Host "TEL99 Projet autonome lance en arriere-plan : pid=$($proc.Id) project=$Project"
                exit 0
            }
            & $Python @argv
            exit $LASTEXITCODE
        }
        "Progress" {
            if (-not $Project.Trim()) { throw "-Mode Progress requiert -Project <dossier>." }
            & $Python -B -m scripts.agents.automation.autonomous_project_runner --project $Project --progress
            exit $LASTEXITCODE
        }
        "Pause" {
            if (-not $Project.Trim()) { throw "-Mode Pause requiert -Project <dossier>." }
            & $Python -B -m scripts.agents.automation.autonomous_project_runner --project $Project --control pause
            exit $LASTEXITCODE
        }
        "Resume" {
            if (-not $Project.Trim()) { throw "-Mode Resume requiert -Project <dossier>." }
            $argv = @("-B", "-m", "scripts.agents.automation.autonomous_project_runner", "--project", $Project, "--resume-process")
            if ($Task.Trim()) { $argv += @("--task", $Task) }
            if ($Role) { $argv += @("--role", $Role) }
            if ($Hybrid.IsPresent) { $argv += "--hybrid" }
            if ($Confidential.IsPresent) { $argv += "--confidential" }
            if ($ResumeFailed.IsPresent) { $argv += "--resume-rejected" }
            if ($RevisePlan.IsPresent) { $argv += "--revise-plan" }
            if ($Detached.IsPresent) {
                $logDir = Join-Path $Project "artifacts"
                New-Item -ItemType Directory -Force -Path $logDir | Out-Null
                $proc = Start-Process -FilePath $Python -ArgumentList $argv -WorkingDirectory $Repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "runner.log") -RedirectStandardError (Join-Path $logDir "runner.err.log")
                Write-Host "TEL99 Reprise autonome lancee en arriere-plan : pid=$($proc.Id) project=$Project"
                exit 0
            }
            & $Python @argv
            exit $LASTEXITCODE
        }
        "Stop" {
            if (-not $Project.Trim()) { throw "-Mode Stop requiert -Project <dossier>." }
            & $Python -B -m scripts.agents.automation.autonomous_project_runner --project $Project --control stop
            exit $LASTEXITCODE
        }
        "Ask" {
            if (-not $Task.Trim()) { throw "Le parametre -Task est requis pour -Mode Ask." }
            $argv = @("-B", "-m", "scripts.agents.automation.agent_cli", "--task", $Task)
            if ($Role) { $argv += @("--role", $Role) }
            if ($Domain) { $argv += @("--domain", $Domain) }
            if ($Project) { $argv += @("--project", $Project) }
            if ($Hybrid.IsPresent) { $argv += "--hybrid" }
            if ($Confidential.IsPresent) { $argv += "--confidential" }
            if ($ResumeFailed.IsPresent) { $argv += "--resume-rejected" }
            if ($DryRun.IsPresent) { $argv += "--dry-run" }
            & $Python @argv
            exit $LASTEXITCODE
        }
        "Status" {
            & $Python -B -m scripts.agents.automation.agent_cli --status
            exit $LASTEXITCODE
        }
        "Results" {
            & $Python -B -m scripts.agents.automation.run_full_local_chain --results
            exit $LASTEXITCODE
        }
        "Radar" {
            $radarScript = Join-Path ([Environment]::GetFolderPath("Desktop")) "AI_RADAR\start-ai-radar.ps1"
            if (-not (Test-Path -LiteralPath $radarScript)) { throw "AI Radar introuvable: $radarScript" }
            $rArgs = @("-NoProfile", "-File", $radarScript)
            if ($OpenBrowser.IsPresent) { $rArgs += "-OpenBrowser" }
            & pwsh @rArgs
            exit $LASTEXITCODE
        }
        "Cockpit" {
            $agentPs1 = Join-Path $Repo "scripts\agents\automation\tel99-agent.ps1"
            & pwsh -NoProfile -File $agentPs1 -Mode Cockpit -AllowControls
            exit $LASTEXITCODE
        }
    }
} finally {
    Pop-Location
}

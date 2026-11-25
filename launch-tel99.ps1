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
    [ValidateSet("Team", "Project", "Ask", "Progress", "Pause", "Resume", "Stop", "Status", "Radar", "Cockpit", "Results")]
    [string]$Mode = "Team",
    [string]$Task = "",
    [string]$Role = "",
    [string]$Domain = "",
    [string]$Project = "",
    [string]$WaitForPid = "",
    [switch]$Hybrid,
    [switch]$Confidential,
    [switch]$Detached,
    [switch]$DryRun,
    [switch]$OpenBrowser
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $Repo
try {
    # Si -Task et -Project sont fournis avec le Mode par defaut, basculer automatiquement en mode Projet Autonome
    if ($Mode -eq "Team" -and $Task.Trim()) {
        if ($Project.Trim()) { $Mode = "Project" } else { $Mode = "Ask" }
    }
    switch ($Mode) {
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
            & $Python -B -m scripts.agents.automation.autonomous_project_runner --project $Project --control resume
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

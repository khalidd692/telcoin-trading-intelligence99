<#
.SYNOPSIS
  Commande PowerShell unique pour lancer et exploiter les 12 agents IA TEL99, le Cockpit et AI Radar.
.EXAMPLE
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1
.EXAMPLE
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1 -Task "Écris un validateur CSV Python stdlib"
.EXAMPLE
  pwsh -NoProfile -File C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125\launch-tel99.ps1 -Task "Audite ce module" -Role security -Hybrid
#>
[CmdletBinding()]
param(
    [ValidateSet("Team", "Status", "Task", "Radar", "Cockpit", "Results")]
    [string]$Mode = "Team",
    [string]$Task = "",
    [string]$Role = "",
    [string]$Domain = "",
    [string]$Project = "",
    [switch]$Hybrid,
    [switch]$Confidential,
    [switch]$DryRun,
    [switch]$OpenBrowser
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $Repo
try {
    if ($Task.Trim()) {
        $Mode = "Task"
    }
    switch ($Mode) {
        "Team" {
            Write-Host "=== TEL99 — Equipe des 12 Agents IA ===" -ForegroundColor Cyan
            & $Python -B -m scripts.agents.automation.agent_cli --team
            Write-Host ""
            Write-Host "Exemples d'utilisation :" -ForegroundColor Green
            Write-Host "  Mission locale (0 cloud) : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Task `"Ta demande`""
            Write-Host "  Mission hybride (0 $)    : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Task `"Ta demande`" -Hybrid"
            Write-Host "  Agent cible + domaine    : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Task `"Ta demande`" -Role security -Domain quant"
            Write-Host "  AI Radar (web local)     : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Radar -OpenBrowser"
            Write-Host "  Statut complet           : pwsh -NoProfile -File $Repo\launch-tel99.ps1 -Mode Status"
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
        "Task" {
            if (-not $Task.Trim()) { throw "Le parametre -Task est requis pour -Mode Task." }
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

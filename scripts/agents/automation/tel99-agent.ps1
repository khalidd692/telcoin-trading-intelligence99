# TEL99 Antigravity V2 unified PowerShell operator CLI.
[CmdletBinding()]
param(
    [ValidateSet("Doctor", "Preflight", "Run", "Status", "Learn", "Cockpit", "Stop", "DraftProposal")]
    [string]$Mode = "Doctor",
    [string]$Manifest,
    [switch]$AutoFeed,
    [switch]$Once,
    [switch]$VerifyBaseline,
    [string]$SpecPath,
    [string]$OutputPath,
    [string]$StateDir = (Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_ANTIGRAVITY_STATE"),
    [ValidateRange(1, 60)]
    [int]$Minutes = 60,
    [ValidateRange(1, 3600)]
    [int]$PollInterval = 30,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $repo
try {
    switch ($Mode) {
        "Doctor" {
            $argv = @("-B", "-m", "scripts.agents.automation.env_doctor", "--state", $StateDir)
            if ($AutoFeed.IsPresent) { $argv += "--auto-feed" }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Learn" {
            $argv = @("-B", "-m", "scripts.agents.automation.learning_loop", "--state", $StateDir)
            if ($OutputPath) { $argv += @("--export", $OutputPath) }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Cockpit" {
            $argv = @("-B", "-m", "scripts.agents.automation.multi_cockpit", "--state", $StateDir, "--port", [string]$Port)
            & $python @argv
            exit $LASTEXITCODE
        }
        "DraftProposal" {
            if (-not $SpecPath) { throw "DraftProposal requires -SpecPath." }
            $argv = @("-B", "-m", "scripts.agents.automation.proposal_builder", "--spec", $SpecPath)
            if ($VerifyBaseline.IsPresent) { $argv += "--verify-baseline" }
            if ($OutputPath) { $argv += @("--output", $OutputPath) }
            & $python @argv
            exit $LASTEXITCODE
        }
        default {
            $module = "scripts.agents.automation.github_multi_mandate_session"
            $argv = @("-B", "-m", $module, $Mode.ToLowerInvariant(), "--state", $StateDir)
            if ($Mode -in @("Preflight", "Run")) {
                if ($AutoFeed.IsPresent -eq [bool]$Manifest) {
                    throw "Choose either -AutoFeed or -Manifest, never both or neither."
                }
                if ($AutoFeed.IsPresent) {
                    $argv += "--auto-feed"
                } else {
                    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
                        throw "Approved controller manifest not found."
                    }
                    $argv += @("--manifest", (Resolve-Path -LiteralPath $Manifest).Path)
                }
            }
            if ($Mode -eq "Run") {
                $argv += @("--seconds", [string]($Minutes * 60), "--poll-interval", [string]$PollInterval)
                if ($Once.IsPresent) { $argv += "--once" }
            }
            & $python @argv
            exit $LASTEXITCODE
        }
    }
} finally {
    Pop-Location
}

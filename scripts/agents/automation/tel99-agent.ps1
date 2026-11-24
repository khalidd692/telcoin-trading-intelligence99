# TEL99 unified PowerShell operator CLI (reads defaults from tel99-config.json).
[CmdletBinding()]
param(
    [ValidateSet("Start", "Doctor", "Providers", "Preflight", "Run", "Status", "Recover", "Learn", "Cockpit", "Stop", "Plan", "DraftProposal")]
    [string]$Mode = "Start",
    [string]$Manifest,
    [switch]$AutoFeed,
    [switch]$Once,
    [switch]$IsolateBlocked,
    [switch]$AllowControls,
    [switch]$ClearStop,
    [switch]$VerifyBaseline,
    [string]$SpecPath,
    [string]$OutputPath,
    [string]$StateDir,
    [ValidateRange(1, 60)]
    [int]$Minutes = 0,
    [ValidateRange(1, 3600)]
    [int]$PollInterval = 0,
    [ValidateRange(1024, 65535)]
    [int]$Port = 0
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
$configPath = Join-Path $PSScriptRoot "tel99-config.json"
$config = $null
if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

if (-not $StateDir) {
    if ($config -and $config.state_dir) {
        $rawDir = [string]$config.state_dir
        if ($rawDir.StartsWith("~/") -or $rawDir.StartsWith("~\")) {
            $StateDir = Join-Path $HOME $rawDir.Substring(2)
        } else {
            $StateDir = $rawDir
        }
    } else {
        $StateDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_ANTIGRAVITY_STATE"
    }
}
if ($Minutes -le 0) { $Minutes = if ($config -and $config.minutes) { [int]$config.minutes } else { 60 } }
if ($PollInterval -le 0) { $PollInterval = if ($config -and $config.poll_interval) { [int]$config.poll_interval } else { 30 } }
if ($Port -le 0) { $Port = if ($config -and $config.cockpit_port) { [int]$config.cockpit_port } else { 8765 } }

$useAutoFeed = $AutoFeed.IsPresent -or (-not $Manifest -and $config -and [bool]$config.auto_feed)
$useIsolate = $IsolateBlocked.IsPresent -or ($config -and [bool]$config.isolate_blocked)

Push-Location -LiteralPath $repo
try {
    switch ($Mode) {
        "Start" {
            Write-Host "TEL99 [1/4] Doctor..."
            & $python -B -m scripts.agents.automation.env_doctor --state $StateDir --auto-feed
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

            Write-Host "TEL99 [2/4] Preflight..."
            $pre = @("-B", "-m", "scripts.agents.automation.github_multi_mandate_session", "preflight", "--state", $StateDir)
            if ($Manifest) { $pre += @("--manifest", (Resolve-Path -LiteralPath $Manifest).Path) }
            else { $pre += "--auto-feed" }
            & $python @pre
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

            Write-Host "TEL99 [3/4] Run..."
            $runArgs = @("-B", "-m", "scripts.agents.automation.github_multi_mandate_session", "run",
                         "--state", $StateDir, "--seconds", [string]($Minutes * 60), "--poll-interval", [string]$PollInterval)
            if ($Manifest) { $runArgs += @("--manifest", (Resolve-Path -LiteralPath $Manifest).Path) }
            else { $runArgs += "--auto-feed" }
            if ($useIsolate) { $runArgs += "--isolate-blocked" }
            if ($Once.IsPresent) { $runArgs += "--once" }
            & $python @runArgs
            $runCode = $LASTEXITCODE

            Write-Host "TEL99 [4/4] Learning sync..."
            & $python -B -m scripts.agents.automation.learning_loop --state $StateDir | Out-Null
            exit $runCode
        }
        "Doctor" {
            $argv = @("-B", "-m", "scripts.agents.automation.env_doctor", "--state", $StateDir, "--include-providers")
            if ($useAutoFeed) { $argv += "--auto-feed" }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Providers" {
            & $python -B -m scripts.agents.automation.provider_router --probe
            exit $LASTEXITCODE
        }
        "Recover" {
            $action = if ($ClearStop.IsPresent) { "clear-stop" } else { "inspect" }
            & $python -B -m scripts.agents.automation.recovery_tool $action --state $StateDir
            exit $LASTEXITCODE
        }
        "Learn" {
            $argv = @("-B", "-m", "scripts.agents.automation.learning_loop", "--state", $StateDir)
            if ($OutputPath) { $argv += @("--export", $OutputPath) }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Cockpit" {
            $argv = @("-B", "-m", "scripts.agents.automation.multi_cockpit", "--state", $StateDir,
                      "--port", [string]$Port, "--include-providers")
            if ($AllowControls.IsPresent) { $argv += "--allow-controls" }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Plan" {
            if (-not $SpecPath) { throw "Plan requires -SpecPath." }
            $argv = @("-B", "-m", "scripts.agents.automation.mission_planner", "--spec", $SpecPath, "--state", $StateDir)
            if ($VerifyBaseline.IsPresent) { $argv += "--verify-baseline" }
            if ($OutputPath) { $argv += @("--output", $OutputPath) }
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
                if ($AutoFeed.IsPresent -and [bool]$Manifest) {
                    throw "Choose either -AutoFeed or -Manifest, never both."
                }
                if ($Manifest) {
                    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) {
                        throw "Approved controller manifest not found."
                    }
                    $argv += @("--manifest", (Resolve-Path -LiteralPath $Manifest).Path)
                } elseif ($useAutoFeed) {
                    $argv += "--auto-feed"
                } else {
                    throw "Specify -AutoFeed or -Manifest."
                }
            }
            if ($Mode -eq "Run") {
                $argv += @("--seconds", [string]($Minutes * 60), "--poll-interval", [string]$PollInterval)
                if ($useIsolate) { $argv += "--isolate-blocked" }
                if ($Once.IsPresent) { $argv += "--once" }
            }
            & $python @argv
            exit $LASTEXITCODE
        }
    }
} finally {
    Pop-Location
}

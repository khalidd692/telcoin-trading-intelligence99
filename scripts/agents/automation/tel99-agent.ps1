# TEL99 unified PowerShell operator CLI (reads defaults from tel99-config.json).
[CmdletBinding()]
param(
    [ValidateSet("Start", "LocalChain", "Engines", "Academy", "Pause", "Resume", "Results", "Doctor", "Providers", "Preflight", "Run", "Status", "Recover", "Learn", "Cockpit", "Stop", "Plan", "DraftProposal", "Specialists", "AuditAgents", "Leases")]
    [string]$Mode = "Start",
    [string]$Manifest,
    [string]$Steps = "preflight,transfer,ai_radar,generalization,academy,lora_corpus,endurance",
    [string]$WaitForPid = "",
    [switch]$Detached,
    [switch]$AutoFeed,
    [switch]$Once,
    [switch]$IsolateBlocked,
    [switch]$ExitWhenDone,
    [switch]$AllowControls,
    [switch]$ClearStop,
    [switch]$VerifyBaseline,
    [switch]$UseSdkBackend,
    [string]$SpecPath,
    [string]$OutputPath,
    [string]$StateDir,
    [string]$Python,
    [ValidateRange(0, 180)]
    [int]$Minutes = 0,
    [ValidateRange(0, 3600)]
    [int]$PollInterval = 0,
    [ValidateRange(0, 65535)]
    [int]$Port = 0
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
if (-not $Python -and $env:TEL99_PYTHON) {
    $Python = $env:TEL99_PYTHON
}
if ($Python) {
    $pythonCmd = Get-Command $Python -ErrorAction SilentlyContinue
    $python = if ($pythonCmd) { $pythonCmd.Source } else { $Python }
} else {
    $python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
}
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
$cfgSdkEnabled = ($config -and $config.PSObject.Properties["sdk_backend"] -and $config.sdk_backend -and [bool]$config.sdk_backend.enabled)
$useSdk = $UseSdkBackend.IsPresent -or $cfgSdkEnabled
$prevBackendEnv = $env:TEL99_EXECUTION_BACKEND
if ($useSdk) {
    $env:TEL99_EXECUTION_BACKEND = "antigravity_sdk"
}

Push-Location -LiteralPath $repo
try {
    switch ($Mode) {
        "Start" {
            if ($AutoFeed.IsPresent -and $Manifest) {
                throw "Choose either -AutoFeed or -Manifest, never both."
            }
            Write-Host "TEL99 [1/4] Doctor..."
            $doctorArgs = @("-B", "-m", "scripts.agents.automation.env_doctor", "--state", $StateDir)
            if (-not $Manifest) { $doctorArgs += "--auto-feed" }
            & $python @doctorArgs
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
            if ($ExitWhenDone.IsPresent) { $runArgs += "--exit-when-done" }
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
        "Specialists" {
            & $python -B -m scripts.agents.specialist_dispatch list
            exit $LASTEXITCODE
        }
        "AuditAgents" {
            & $python -B -m scripts.agents.specialist_dispatch audit
            exit $LASTEXITCODE
        }
        "Leases" {
            & $python -B -m scripts.agents.automation.ide_coordination status --state $StateDir
            exit $LASTEXITCODE
        }
        "Engines" {
            & $python -B -m scripts.agents.automation.ide_coordination engines --state $StateDir
            exit $LASTEXITCODE
        }
        "LocalChain" {
            $chainDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_LOCAL_CHAIN_STATE"
            New-Item -ItemType Directory -Force -Path $chainDir | Out-Null
            Remove-Item -LiteralPath (Join-Path $chainDir "stop.request") -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath (Join-Path $chainDir "pause.request") -ErrorAction SilentlyContinue
            $argv = @("-B", "-m", "scripts.agents.automation.run_full_local_chain", "--steps", $Steps, "--report-dir", $chainDir, "--endurance-minutes", [string]$Minutes)
            if ($WaitForPid) {
                foreach ($tok in ($WaitForPid -split ',')) {
                    $t = $tok.Trim()
                    if ($t -match '^\d+$' -and [int]$t -gt 0) { $argv += @("--wait-for-pid", $t) }
                }
            }
            if ($Detached.IsPresent) {
                $log = Join-Path $chainDir "local_chain.log"
                $err = Join-Path $chainDir "local_chain.err.log"
                $proc = Start-Process -FilePath $python -ArgumentList $argv -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $err
                Set-Content -Path (Join-Path $chainDir "local_chain.pid") -Value $proc.Id
                Write-Host "TEL99 LocalChain started detached: pid=$($proc.Id) steps=$Steps"
                Write-Host "Log: $log"
                exit 0
            }
            & $python @argv
            exit $LASTEXITCODE
        }
        "Academy" {
            $acadScript = Join-Path ([Environment]::GetFolderPath("Desktop")) "AI_RADAR\run_academy_eval.py"
            & $python -B $acadScript
            exit $LASTEXITCODE
        }
        "Pause" {
            $chainDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_LOCAL_CHAIN_STATE"
            New-Item -ItemType Directory -Force -Path $chainDir | Out-Null
            Set-Content -Path (Join-Path $chainDir "pause.request") -Value (Get-Date -Format o)
            Write-Host "TEL99 LocalChain pause requested at $chainDir\pause.request"
            exit 0
        }
        "Resume" {
            $chainDir = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_LOCAL_CHAIN_STATE"
            Remove-Item -LiteralPath (Join-Path $chainDir "pause.request") -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath (Join-Path $chainDir "stop.request") -ErrorAction SilentlyContinue
            & $python -B -m scripts.agents.automation.recovery_tool clear-stop --state $StateDir
            Write-Host "TEL99 pause/stop cleared safely."
            exit $LASTEXITCODE
        }
        "Results" {
            & $python -B -m scripts.agents.automation.run_full_local_chain --results
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
                if ($ExitWhenDone.IsPresent) { $argv += "--exit-when-done" }
                if ($Once.IsPresent) { $argv += "--once" }
            }
            & $python @argv
            exit $LASTEXITCODE
        }
    }
} finally {
    if ($null -eq $prevBackendEnv) {
        Remove-Item Env:TEL99_EXECUTION_BACKEND -ErrorAction SilentlyContinue
    } else {
        $env:TEL99_EXECUTION_BACKEND = $prevBackendEnv
    }
    Pop-Location
}

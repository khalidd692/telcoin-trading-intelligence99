# TEL99 native Ollama recipe. No Kilo, Codex or paid provider dependency.
# Run with pwsh -NoProfile -File <path> -Mode Test|Gemma|Coder|Qwen35|Route|Evidence|Team.
[CmdletBinding()]
param(
    [ValidateSet("Test", "Gemma", "Coder", "Qwen35", "Route", "Evidence", "Team")]
    [string]$Mode = "Test"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $repo
try {
    Write-Host "TEL99 | Python tests for native Ollama and legacy llama.cpp"
    & $python -B -m unittest tests.test_ollama_native_code tests.test_local_model_routing tests.test_prepare_local_code tests.test_evidence_route tests.test_multiagent_pilot
    if ($LASTEXITCODE -ne 0) {
        throw "Regression tests failed; no real model campaign launched"
    }
    if ($Mode -eq "Test") {
        Write-Host "TESTS_OK | No generation launched"
        return
    }

    $stamp = (Get-Date -Format "yyyyMMddHHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 6)
    $prefix = "native-$stamp"
    $registry = Join-Path $env:TEMP ("tel99-$prefix.json")
    $source = "docs/agents/TEL99_QWEN_REPAIR_QUEUE_20261123.json"
    $pin = "dfc7ae6328f82894b97b2a5a6d7676096fb643d289bc50cba704b30a7ca01bf9"

    if ($Mode -in @("Evidence", "Team")) {
        # The two Windows runs are independently SHA-pinned. The Python
        # evidence verifier fails closed if even one proof cannot be validated.
        $desktop = [Environment]::GetFolderPath("Desktop")
        $gemmaSession = Join-Path $desktop "TEL99_AUTONOMIE_NUIT_20261123-173627-368634"
        $coderSession = Join-Path $desktop "TEL99_AUTONOMIE_NUIT_20261123-175102-481080"
        $cliArgs = @(
            "-B", "-m", "scripts.agents.automation.evidence_route",
            $source, "--source-sha256", $pin,
            "--gemma", $gemmaSession,
            "--gemma-sha256", "463badf6cbde82728da958ce2aed3c834ca749eca5ff4dc8c93804fff9f4c062",
            "--coder", $coderSession,
            "--coder-sha256", "c20e346be8f2368ddd055d4af99361c926230ad4fb66131d1e68bfab59622617"
        )
    } else {
        $cliArgs = @(
            "-B", "-m", "scripts.agents.automation.prepare_local_code",
            $source, "--source-sha256", $pin
        )

        if ($Mode -eq "Gemma") {
            $cliArgs += @("--mode", "fixed", "--binding", "local/ollama-gemma4-e4b", "11434")
        } elseif ($Mode -eq "Coder") {
            $cliArgs += @("--mode", "fixed", "--binding", "local/ollama-qwen2.5-coder-7b", "11434")
        } elseif ($Mode -eq "Qwen35") {
            $cliArgs += @("--mode", "fixed", "--binding", "local/ollama-qwen3.5-9b", "11434")
        } else {
            $cliArgs += @(
                "--mode", "routed",
                "--binding", "local/ollama-gemma4-e4b", "11434",
                "--binding", "local/ollama-qwen2.5-coder-7b", "11434",
                "--binding", "local/ollama-qwen3.5-9b", "11434",
                "--escalate", "qwen-repair-metadata-shape-20261123"
            )
        }
    }
    if ($Mode -eq "Team") {
        $cliArgs += "--team"
    }
    $cliArgs += @("--prefix", $prefix, "--output", $registry)
    $out = & $python @cliArgs
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare a new approved mission registry" }
    $newPin = ($out | Select-Object -Last 1).Trim()
    if ($newPin -cnotmatch "^[0-9a-f]{64}$") { throw "Unexpected approved registry digest" }

    Write-Host "TEL99 | Fresh approved registry: $registry"
    Write-Host "TEL99 | Registry pin: $newPin"
    if ($Mode -in @("Evidence", "Team")) {
        $plan = [System.IO.Path]::ChangeExtension($registry, ".selection.json")
        if (!(Test-Path -LiteralPath $plan)) { throw "Evidence selection plan missing" }
        Write-Host "TEL99 | Verified per-task model selection"
        $selection = Get-Content -LiteralPath $plan -Raw | ConvertFrom-Json
        foreach ($d in $selection.decisions) {
            Write-Host "  $($d.function) => $($d.selected_model)"
        }
    }

    Write-Host "TEL99 | Mode: $Mode | Five original tasks plus optional approved successor"
    Write-Host "TEL99 | Running foreground Night Lab, max one hour, no auto merge"
    & $python -B "scripts/agents/night_lab_20261123.py" run --registry $registry --registry-sha256 $newPin --hours 1
    $runCode = $LASTEXITCODE

    $latest = Get-ChildItem (Join-Path $HOME "Desktop") -Directory -Filter "TEL99_AUTONOMIE_NUIT_*" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) {
        Write-Host "TEL99 | Latest campaign evidence: $($latest.FullName)"
        $status = Join-Path $latest.FullName "status.json"
        if (Test-Path $status) {
            $state = Get-Content $status -Raw | ConvertFrom-Json
            Write-Host "TEL99 | Campaign phase: $($state.phase)"
            $state.missions | Format-List
        }
    }
    if ($Mode -eq "Team" -and $latest) {
        $stateDir = Join-Path $latest.FullName "code-state"
        $count = 0
        if (Test-Path -LiteralPath $stateDir) {
            foreach ($receiptFile in (Get-ChildItem -LiteralPath $stateDir -File -Filter "*.worker.json")) {
                $receipt = Get-Content -LiteralPath $receiptFile.FullName -Raw | ConvertFrom-Json
                $trace = $receipt.agent_trace
                if ($null -ne $trace -and $null -ne $trace.analyst -and $null -ne $trace.developer) {
                    $count++
                    Write-Host "TEL99 | Handoff $($receiptFile.Name): $($trace.analyst.role) => $($trace.developer.role)"
                    Write-Host "       Analyst SHA256: $($trace.analyst.sha256)"
                }
            }
        }
        Write-Host "TEL99 | Agent analyst/developer handoff receipts observed: $count"
    }
    if ($runCode -ne 0) { throw "Night Lab incomplete or blocked (exit $runCode); inspect evidence" }
    Write-Host "TEL99 | Complete: all mandatory missions accepted"
}
finally {
    Pop-Location
}

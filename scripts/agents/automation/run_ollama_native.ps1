# TEL99 native Ollama recipe. No Kilo, Codex or paid provider dependency.
# Run with pwsh -NoProfile -File <path> -Mode Test|Gemma|Route.
[CmdletBinding()]
param(
    [ValidateSet("Test", "Gemma", "Route")]
    [string]$Mode = "Test"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source

Push-Location -LiteralPath $repo
try {
    Write-Host "TEL99 | Python tests for native Ollama and legacy llama.cpp"
    & $python -B -m unittest tests.test_ollama_native_code tests.test_local_model_routing tests.test_prepare_local_code
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

    $cliArgs = @(
        "-B", "-m", "scripts.agents.automation.prepare_local_code",
        $source, "--source-sha256", $pin
    )

    if ($Mode -eq "Gemma") {
        $cliArgs += @("--mode", "fixed", "--binding", "local/ollama-gemma4-e4b", "11434")
    } else {
        $cliArgs += @(
            "--mode", "routed",
            "--binding", "local/ollama-gemma4-e4b", "11434",
            "--binding", "local/ollama-qwen2.5-coder-7b", "11434",
            "--binding", "local/ollama-qwen3.5-9b", "11434",
            "--escalate", "qwen-repair-metadata-shape-20261123"
        )
    }
    $cliArgs += @("--prefix", $prefix, "--output", $registry)
    $out = & $python @args
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare a new approved mission registry" }
    $newPin = ($out | Select-Object -Last 1).Trim()
    if ($newPin -cnotmatch "^[0-9a-f]{64}$") { throw "Unexpected approved registry digest" }

    Write-Host "TEL99 | Fresh approved registry: $registry"
    Write-Host "TEL99 | Registry pin: $newPin"
    Write-Host "TEL99 | Mode: $Mode | Five original independent tasks"
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
    if ($runCode -ne 0) { throw "Night Lab incomplete or blocked (exit $runCode); inspect evidence" }
    Write-Host "TEL99 | Complete: all mandatory missions accepted"
}
finally {
    Pop-Location
}

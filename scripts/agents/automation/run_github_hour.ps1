# HISTORICAL ONLY: controller #178 was fully completed. Do not use for new missions.
# TEL99 — one-hour bounded local-code GitHub campaign; no new supervisor.
[CmdletBinding()]
param(
    [ValidateSet("Preflight", "Run", "Status", "Stop")]
    [string]$Mode = "Preflight",
    [ValidateRange(1, 60)]
    [int]$Minutes = 60
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
$state = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_GITHUB_HOUR_STATE_20261123"
$controller = 178
$mandate = 7114796910
$pin = "85097fb5baaf114b71c2f3e9bed29a43457c6824604baf43d549ce6b9a44c1bf"
$module = "scripts.agents.automation.github_local_code_campaign"

Push-Location -LiteralPath $repo
try {
    if ($Mode -in @("Run", "Preflight")) {
        Write-Host "TEL99 | Checking Python safety and hour queue regressions"
        & $python -B -m unittest tests.test_github_local_code_campaign tests.test_github_hour_queue tests.test_local_code_pr_publisher tests.test_multiagent_pilot tests.test_evidence_route tests.test_ollama_native_code tests.test_local_codegen tests.test_kilo_github_campaign
        if ($LASTEXITCODE -ne 0) { throw "Local tests failed - workers not launched" }

        Write-Host "TEL99 | Verifying signed GitHub mandate for three new issues"
        & $python -B -m $module preflight --issue $controller --mandate-comment $mandate --mandate-sha256 $pin
        if ($LASTEXITCODE -ne 0) { throw "Signed GitHub preflight not READY - workers not launched" }

        if ($Mode -eq "Preflight") {
            Write-Host "TEL99 | READY (no model generation)"
            return
        }
    }

    $cmd = @("-B", "-m", $module, $Mode.ToLowerInvariant(), "--state", $state)
    if ($Mode -eq "Run") {
        $cmd += @("--issue", [string]$controller,
                  "--mandate-comment", [string]$mandate,
                  "--mandate-sha256", $pin,
                  "--seconds", [string]($Minutes * 60))
        Write-Host "TEL99 | Supervisor running for up to $Minutes minutes (only approved work)"
        Write-Host "TEL99 | STOP: run same script with -Mode Stop from a second PowerShell"
    }
    & $python @cmd
    if ($LASTEXITCODE -ne 0) {
        throw "TEL99 campaign incomplete/blocked. Original state preserved at $state"
    }
    Write-Host "TEL99 | $Mode complete - state: $state"
}
finally {
    Pop-Location
}

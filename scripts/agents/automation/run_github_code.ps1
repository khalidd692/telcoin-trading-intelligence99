# TEL99: run the existing supervisor on two owner-approved GitHub code issues.
# No long-running Windows service or task-scheduler installation.
[CmdletBinding()]
    param(
        [ValidateSet("Preflight", "Run", "Status", "Stop")]
        [string]$Mode = "Preflight",
        [int]$PollInterval = 30,
        [ValidateRange(1,3600)][int]$Seconds = 3600
    )
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
$state = Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_GITHUB_CODE_STATE_20261123"
$controller = 169
$mandate = 7113655599
$pin = "d22c14d046c53deed84894fdfbdeb1c015043e91a8406c37a6540beeefaf1e7d"
$module = "scripts.agents.automation.github_local_code_campaign"

Push-Location -LiteralPath $repo
try {
    if ($Mode -in @("Run", "Preflight")) {
        Write-Host "TEL99 | Python offline safety regression tests"
        & $python -B -m unittest tests.test_github_local_code_campaign tests.test_local_code_pr_publisher tests.test_multiagent_pilot tests.test_evidence_route tests.test_ollama_native_code tests.test_local_codegen tests.test_kilo_github_campaign
        if ($LASTEXITCODE -ne 0) { throw "Python safety tests failed; execution refused" }
        Write-Host "TEL99 | GitHub owner mandate preflight"
        & $python -B -m $module preflight --issue $controller --mandate-comment $mandate --mandate-sha256 $pin
        if ($LASTEXITCODE -ne 0) { throw "GitHub preflight not ready; no local worker launched" }
        if ($Mode -eq "Preflight") {
            Write-Host "TEL99 | READY - no model generation"
            return
        }
    }
    $baseArgs = @("-B", "-m", $module, $Mode.ToLowerInvariant(), "--state", $state)
    if ($Mode -eq "Run") {
        $baseArgs += @("--issue", [string]$controller,
                       "--mandate-comment", [string]$mandate,
                       "--mandate-sha256", $pin,
                       "--seconds", "$Seconds",
                       "--poll-interval", "$PollInterval")
        Write-Host "TEL99 | Running existing GitHub local-code supervisor, stop by Mode Stop"
    }
    & $python @baseArgs
    if ($LASTEXITCODE -ne 0) {
        throw "TEL99 GitHub campaign not complete (exit $LASTEXITCODE); state preserved: $state"
    }
    Write-Host "TEL99 | $Mode finished. Durable state: $state"
}
finally {
    Pop-Location
}

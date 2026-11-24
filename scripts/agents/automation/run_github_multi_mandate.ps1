# TEL99 bounded dispatcher over existing verified GitHub/Ollama supervisor.
[CmdletBinding()]
param(
    [ValidateSet("Preflight", "Run", "Status", "Stop")]
    [string]$Mode = "Preflight",
    [string]$Manifest,
    [switch]$AutoFeed,
    [string]$StateDir = (Join-Path ([Environment]::GetFolderPath("Desktop")) "TEL99_MULTI_MANDATE_STATE"),
    [ValidateRange(1, 60)]
    [int]$Minutes = 60,
    [ValidateRange(1, 3600)]
    [int]$PollInterval = 30
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$python = (Get-Command python -CommandType Application -ErrorAction Stop).Source
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
        $manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
        $argv += @("--manifest", $manifestPath)
    }
}
if ($Mode -eq "Run") {
    $argv += @("--seconds", [string]($Minutes * 60),
               "--poll-interval", [string]$PollInterval)
}
Push-Location -LiteralPath $repo
try {
    if ($Mode -eq "Run") {
        Write-Host "TEL99 | verifying owner mandates before workers"
        $preflight = @("-B", "-m", $module, "preflight", "--state", $StateDir)
        if ($AutoFeed.IsPresent) {
            $preflight += "--auto-feed"
        } else {
            $preflight += @("--manifest", $manifestPath)
        }
        & $python @preflight
        if ($LASTEXITCODE -ne 0) { throw "Preflight not READY; no workers launched" }
    }
    & $python @argv
    if ($LASTEXITCODE -ne 0) { throw "TEL99 incomplete/blocked, ledger preserved: $StateDir" }
} finally {
    Pop-Location
}

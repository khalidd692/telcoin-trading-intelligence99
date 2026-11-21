$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$launcher = Join-Path (Split-Path $PSScriptRoot) 'start-agents.ps1'
$pwsh = (Get-Process -Id $PID).Path
$directory = Join-Path ([IO.Path]::GetTempPath()) ("kilo-launcher-" + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $directory

function Assert-LauncherExit([int]$Expected, [string]$Pattern, [string[]]$Arguments) {
    $output = & $pwsh -NoLogo -NoProfile -File $launcher @Arguments 2>&1
    if ($LASTEXITCODE -ne $Expected -or "$output" -notmatch $Pattern) {
        throw "Expected exit $Expected and /$Pattern/, got ${LASTEXITCODE}: $output"
    }
}

try {
    $state = Join-Path $directory 'GitHub state with spaces'
    $registry = Join-Path $directory 'registry.json'
    '{"missions":[],"approvals":{}}' | Set-Content -LiteralPath $registry -Encoding utf8NoBOM
    $sha = (Get-FileHash -LiteralPath $registry -Algorithm SHA256).Hash.ToLowerInvariant()
    $pin = 'a' * 64

    Assert-LauncherExit 0 '"github_queue": null' @('-Action', 'STATUS', '-GitHubIssue', '987', '-State', $state)
    Assert-LauncherExit 1 'requires.*Mandate' @('-Action', 'START', '-GitHubIssue', '987', '-State', $state)
    Assert-LauncherExit 2 'dedicated issue' @('-Action', 'START', '-GitHubIssue', '114', '-State', $state,
        '-MandateComment', '7100000001', '-MandateSha256', $pin)
    Assert-LauncherExit 0 'STOP requested' @('-Action', 'STOP', '-GitHubIssue', '987', '-State', $state)
    Assert-LauncherExit 0 '"state": "STOP_REQUESTED"' @('-Action', 'STATUS', '-GitHubIssue', '987', '-State', $state)
    Assert-LauncherExit 2 'STOP remains set' @('-Action', 'START', '-GitHubIssue', '987', '-State', $state,
        '-MandateComment', '7100000001', '-MandateSha256', $pin)
    Assert-LauncherExit 0 '"state": "STOPPED"' @('-Action', 'RUN', '-Registry', $registry, '-RegistrySha256', $sha,
        '-State', (Join-Path $directory 'local'), '-Once')
    Assert-LauncherExit 1 'Campaign requires' @('-Action', 'START', '-Campaign', '-State', $state)
    Assert-LauncherExit 0 'STOP requested' @('-Action', 'STOP', '-GitHubIssue', '123', '-Campaign',
        '-State', (Join-Path $directory 'campaign'))
    Assert-LauncherExit 2 'STOP remains set' @('-Action', 'START', '-GitHubIssue', '123', '-Campaign',
        '-State', (Join-Path $directory 'campaign'), '-MandateComment', '7100000001', '-MandateSha256', $pin)
    Write-Output '10/10 PowerShell launcher checks passed without GitHub or Kilo network access.'
}
finally {
    Remove-Item -LiteralPath $directory -Recurse -Force
}

# The last launcher check expects a nonzero native exit code. Report the suite result.
exit 0

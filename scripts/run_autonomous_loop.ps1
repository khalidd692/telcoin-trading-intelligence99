[CmdletBinding()]
param(
    [switch]$Demo,
    [ValidateRange(1, 9)]
    [int]$DemoAttempt = 1,
    [switch]$Once,
    [string]$Approvals,
    [string]$Codex,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $installed = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($installed -and $installed.Source -notlike '*\WindowsApps\*') {
        $Python = $installed.Source
    } else {
        $Python = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Python 3 est requis. Indiquez son executable avec -Python.'
}
if (-not $Codex) {
    $installed = Get-Command codex.exe -ErrorAction SilentlyContinue
    if ($installed) {
        $Codex = $installed.Source
    } else {
        $local = Join-Path $root '.tel99-automation-state\codex-cli\node_modules\@openai'
        if (Test-Path -LiteralPath $local) {
            $runner = Get-ChildItem -LiteralPath $local -Filter codex.exe -File -Recurse |
                Select-Object -First 1
            if ($runner) { $Codex = $runner.FullName }
        }
    }
}
$runnerArgs = @('-B', (Join-Path $PSScriptRoot 'agents\automation\local_codex.py'))
if ($Demo) { $runnerArgs += @('--demo', '--demo-attempt', $DemoAttempt) }
if ($Once) { $runnerArgs += '--once' }
if ($Approvals) { $runnerArgs += @('--approvals', $Approvals) }
if ($Codex) { $runnerArgs += @('--codex', $Codex) }
& $Python @runnerArgs
exit $LASTEXITCODE

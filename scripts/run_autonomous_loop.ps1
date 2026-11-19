[CmdletBinding()]
param(
    [switch]$Demo,
    [switch]$CodeDemo,
    [switch]$Preflight,
    [switch]$DiscoverOnly,
    [int]$AwaitIssue,
    [ValidateRange(1, 180)]
    [int]$SessionMinutes,
    [switch]$Status,
    [switch]$RequestStop,
    [ValidateRange(1, 9)]
    [int]$DemoAttempt = 1,
    [switch]$Once,
    [string]$Approvals,
    [string]$Codex,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$kvProfile = Join-Path $root '.tel99-automation-state/local-codex/upstash-user.json'
if (-not ($Status -or $RequestStop) -and (Test-Path -LiteralPath $kvProfile -PathType Leaf) -and
    -not ($env:TEL99_UPSTASH_REST_URL -or $env:TEL99_UPSTASH_REST_TOKEN -or $env:TEL99_UPSTASH_FREE)) {
    $profileData = Get-Content -LiteralPath $kvProfile -Raw | ConvertFrom-Json
    if ($profileData.free -ne $true) { throw 'Profil Upstash Free invalide.' }
    Import-Module -Name (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
    $protectedToken = ConvertTo-SecureString $profileData.token
    $env:TEL99_UPSTASH_REST_URL = $profileData.url
    $env:TEL99_UPSTASH_REST_TOKEN = [Net.NetworkCredential]::new('', $protectedToken).Password
    $env:TEL99_UPSTASH_FREE = '1'
}
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
        if (-not (Test-Path -LiteralPath $local)) {
            $local = Join-Path (Split-Path -Parent $root) 'codex-cli\node_modules\@openai'
        }
        if (Test-Path -LiteralPath $local) {
            $runner = Get-ChildItem -LiteralPath $local -Filter codex.exe -File -Recurse |
                Select-Object -First 1
            if ($runner) { $Codex = $runner.FullName }
        }
    }
}
$runnerArgs = @('-B', (Join-Path $PSScriptRoot 'agents\automation\local_codex.py'))
if ($Demo) { $runnerArgs += @('--demo', '--demo-attempt', $DemoAttempt) }
if ($CodeDemo) { $runnerArgs += @('--code-demo', '--demo-attempt', $DemoAttempt) }
if ($Once) { $runnerArgs += '--once' }
if ($Preflight) { $runnerArgs += '--preflight' }
if ($DiscoverOnly) { $runnerArgs += '--discover-only' }
if ($AwaitIssue) { $runnerArgs += @('--await-issue', $AwaitIssue) }
if ($SessionMinutes) { $runnerArgs += @('--session-minutes', $SessionMinutes) }
if ($Status) { $runnerArgs += '--status-read' }
if ($RequestStop) { $runnerArgs += '--request-stop' }
if ($Approvals) { $runnerArgs += @('--approvals', $Approvals) }
if ($Codex) { $runnerArgs += @('--codex', $Codex) }
& $Python @runnerArgs
exit $LASTEXITCODE

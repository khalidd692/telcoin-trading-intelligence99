[CmdletBinding()]
param(
 [ValidateSet('RUN','STATUS','STOP')][string]$Action='STATUS',
 [string]$Python,
 [string]$State=(Join-Path $PSScriptRoot '.tel99-automation-state/kilo'),
 [string]$Registry,
 [string]$RegistrySha256,
 [ValidateRange(1,3600)][int]$Seconds=300,
 [switch]$Once
)
$ErrorActionPreference='Stop'
if (-not $Python) {
 $managed=Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
 if (Test-Path -LiteralPath $managed) { $Python=$managed }
 else { $Python=(Get-Command python -ErrorAction Stop).Source }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable missing' }
$entry=Join-Path $PSScriptRoot 'scripts/agents/automation/autonomy_runtime.py'
$argv=@('-B',$entry,$Action.ToLowerInvariant(),'--state',$State)
if ($Action -eq 'RUN') {
 if (-not $Registry -or $RegistrySha256 -cnotmatch '^[0-9a-f]{64}$') {
  throw 'RUN requires an operator-approved registry and its pinned SHA256; no automatic approval'
 }
 $argv+=@('--registry',$Registry,'--registry-sha256',$RegistrySha256,'--seconds',"$Seconds")
 if ($Once) { $argv+='--once' }
}
& $Python @argv
exit $LASTEXITCODE

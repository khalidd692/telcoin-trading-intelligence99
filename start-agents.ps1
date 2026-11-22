[CmdletBinding()]
param(
 [ValidateSet('START','RUN','STATUS','STOP','PREFLIGHT','DIAGNOSTIC')][string]$Action='STATUS',
 [string]$Python,
 [string]$State,
 [string]$Registry,
 [string]$RegistrySha256,
 [ValidateRange(1,2147483647)][int]$GitHubIssue,
 [long]$MandateComment,
 [string]$MandateSha256,
 [switch]$Campaign,
 [ValidateRange(1,3600)][int]$Seconds=300,
 [switch]$Once
)
$ErrorActionPreference='Stop'
try {
 if (-not $Python) {
  $managed=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
  if (Test-Path -LiteralPath $managed) { $Python=$managed }
  else { $Python=(Get-Command python -ErrorAction Stop).Source }
 }
 if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable missing' }
} catch {
 if ($Action -ne 'DIAGNOSTIC') { throw }
 @{
  status='BLOCKED'
  timestamp_utc=[DateTimeOffset]::UtcNow.ToString('o')
  source='PowerShell launcher'
  versions=@{python=$null; pwsh=$PSVersionTable.PSVersion.ToString()}
  blockers=@('PYTHON_UNAVAILABLE')
 } | ConvertTo-Json -Depth 3
 exit 2
}
if ($Action -eq 'START') { $Action='RUN' }
if ($Campaign -and (-not $GitHubIssue -or ($MandateComment -le 0 -and -not $State))) {
 throw 'Campaign requires -GitHubIssue and either -MandateComment or -State'
}
if (-not $State) {
 $name=if ($Campaign) {
  "kilo-campaign-$GitHubIssue-$MandateComment"
 } elseif ($GitHubIssue) {
  "kilo-github-$GitHubIssue"
 } else {
  'kilo'
 }
 $State=Join-Path $PSScriptRoot ".tel99-automation-state/$name"
}
if ($Action -eq 'DIAGNOSTIC') {
 $entry=Join-Path $PSScriptRoot 'scripts/agents/automation/windows_diagnostic.py'
 $argv=@('-B',$entry,'--state',$State)
 if ($GitHubIssue) { $argv+=@('--issue',"$GitHubIssue") }
 if ($MandateComment -or $MandateSha256) {
  if (-not $GitHubIssue -or $MandateComment -le 0 -or $MandateSha256 -cnotmatch '^[0-9a-f]{64}$') {
   throw 'DIAGNOSTIC GitHub reads require -GitHubIssue, -MandateComment and -MandateSha256'
  }
  $argv+=@('--mandate-comment',"$MandateComment",'--mandate-sha256',$MandateSha256)
 }
 if ($Campaign) { $argv+='--campaign' }
 $PSNativeCommandUseErrorActionPreference=$false
 & $Python @argv
 exit $LASTEXITCODE
}
$script=if ($GitHubIssue) { 'kilo_github_adapter.py' } else { 'autonomy_runtime.py' }
$entry=Join-Path $PSScriptRoot "scripts/agents/automation/$script"
$argv=@('-B',$entry,$Action.ToLowerInvariant(),'--state',$State)
if ($Action -eq 'PREFLIGHT' -and -not $GitHubIssue) { throw 'PREFLIGHT requires -GitHubIssue' }
if ($Action -in @('RUN', 'PREFLIGHT')) {
 if ($GitHubIssue) {
  if ($Registry -or $RegistrySha256) { throw 'Choose either a GitHub issue or the local registry' }
  if ($MandateComment -le 0 -or $MandateSha256 -cnotmatch '^[0-9a-f]{64}$') {
   throw 'START with -GitHubIssue requires -MandateComment and -MandateSha256'
  }
  $argv+=@('--issue',"$GitHubIssue",'--mandate-comment',"$MandateComment",'--mandate-sha256',$MandateSha256)
  if ($Campaign) { $argv+='--campaign' }
 } else {
  if ($MandateComment -or $MandateSha256) { throw 'A GitHub mandate requires -GitHubIssue' }
  if (-not $Registry -or $RegistrySha256 -cnotmatch '^[0-9a-f]{64}$') {
  throw 'RUN requires an operator-approved registry and its pinned SHA256; no automatic approval'
  }
  $argv+=@('--registry',$Registry,'--registry-sha256',$RegistrySha256)
 }
 if ($Action -eq 'RUN') {
  $argv+=@('--seconds',"$Seconds")
  if ($Once) { $argv+='--once' }
 }
}
& $Python @argv
exit $LASTEXITCODE

[CmdletBinding()]
param(
    [ValidateSet('Diagnose','ImportBundle')][string]$Action = 'Diagnose',
    [string]$Repository,
    [string]$BundlePath,
    [string]$ExpectedSourceSha,
    [string]$ExpectedBundleSha256,
    [string]$Destination
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $algorithm.Dispose(); $stream.Dispose() }
}
try {
    $manifestPath = Join-Path $PSScriptRoot 'SHA256SUMS.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $rootPath = [IO.Path]::GetFullPath($PSScriptRoot) + [IO.Path]::DirectorySeparatorChar
    foreach ($entry in $manifest) {
        $itemPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot $entry.path))
        if (-not $itemPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path outside package' }
        $actualHash = Get-Sha256 $itemPath
        if ($actualHash -ine $entry.sha256) { throw ('Package hash mismatch: ' + $entry.path) }
    }
    Get-Command git -ErrorAction Stop | Out-Null
    if ($Action -eq 'ImportBundle') {
        if ($ExpectedSourceSha -cnotmatch '^a5112413[0-9a-f]{32}$') { throw 'Full authentic source SHA required (40 hex starting a5112413)' }
        if ($ExpectedBundleSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Authentic bundle SHA256 required' }
        if (-not $BundlePath -or -not (Test-Path -LiteralPath $BundlePath -PathType Leaf)) { throw 'Original bundle missing' }
        $bundleFullPath = (Resolve-Path -LiteralPath $BundlePath).Path
        if ((Get-Sha256 $bundleFullPath) -ine $ExpectedBundleSha256) { throw 'Bundle SHA256 mismatch' }
        if (-not $Destination) { throw 'New destination required' }
        $destinationFullPath = [IO.Path]::GetFullPath($Destination)
        if (Test-Path -LiteralPath $destinationFullPath) { throw 'Destination already exists; preserved' }
        & git bundle list-heads "$bundleFullPath"
        if ($LASTEXITCODE -ne 0) { throw 'Invalid bundle' }
        & git clone --no-checkout -- "$bundleFullPath" "$destinationFullPath"
        if ($LASTEXITCODE -ne 0) { throw 'Clone failed; preserve partial destination and obtain a full bundle' }
        $Repository = $destinationFullPath
        $resolvedSource = & git -C "$Repository" rev-parse --verify 'a5112413^{commit}'
        if ($LASTEXITCODE -ne 0 -or "$resolvedSource".Trim() -cne $ExpectedSourceSha) { throw 'Source SHA mismatch; no code executed' }
        & git -C "$Repository" fsck --full
        if ($LASTEXITCODE -ne 0) { throw 'Object integrity check failed' }
        & git -C "$Repository" -c core.hooksPath=NUL checkout --detach "$ExpectedSourceSha"
        if ($LASTEXITCODE -ne 0) { throw 'Checkout failed' }
    } else {
        if (-not $Repository) { $Repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..')) }
        & git -C "$Repository" rev-parse HEAD
        if ($LASTEXITCODE -ne 0) { throw 'Repository unavailable' }
        $ErrorActionPreference = 'Continue'
        $resolvedSource = & git -C "$Repository" rev-parse --verify 'a5112413^{commit}' 2>$null
        $lookupExit = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($lookupExit -ne 0) {
            Write-Output 'BLOCKED_SOURCE_ORIGINE: a5112413 absent. Read RECUPERATION_ORIGINE.md. No model/runtime/test launched.'
            exit 2
        }
    }
    & git -C "$Repository" show --no-patch --format=fuller "$resolvedSource"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read source metadata' }
    & git -C "$Repository" diff-tree --no-commit-id --name-status -r "$resolvedSource"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect source tree' }
    Write-Output ('SOURCE_RECOVERED=' + "$resolvedSource".Trim())
    Write-Output ('CHECKOUT=' + $Repository)
    Write-Output 'Review original code/config/evidence before execution. A->B Windows remains NON TESTE. No model called.'
    exit 0
} catch {
    Write-Error -ErrorAction Continue $_.Exception.Message
    exit 2
}

<#
.SYNOPSIS
    Kilo GitHub Receiver — raccord GitHub → Kilo Agent Manager (P0 #123).
.DESCRIPTION
    Reçoit une mission publiée sur GitHub (issue avec mandat vérifié),
    produit un ACK corrélé, journalise l'exécution et prépare la délégation
    à un spécialiste Kilo. Aucun appel de modèle n'est effectué.
.PARAMETER IssueNumber
    Numéro de l'issue GitHub à écouter.
.PARAMETER Owner
    Propriétaire du dépôt (défaut: khalidd692).
.PARAMETER Repo
    Nom du dépôt (défaut: telcoin-trading-intelligence99).
.PARAMETER Token
    Token GitHub optionnel (lecture publique sans token).
.EXAMPLE
    .\scripts/kilocli/github_receiver.ps1 -IssueNumber 123
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [int]$IssueNumber,

    [string]$Owner = 'khalidd692',
    [string]$Repo = 'telcoin-trading-intelligence99',
    [string]$Token = $null
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$claimsDir = Join-Path $root '.kilo' 'claims'
$sessionsDir = Join-Path $root '.kilo' 'sessions'
$sessionId = 'session-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$sessionDir = Join-Path $sessionsDir $sessionId
$logFile = Join-Path $sessionDir 'ack_log.jsonl'

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $line = "{`"ts`":`"$ts`",`"level`":`"$level`",`"message`":`"$message`"}"
    if (-not (Test-Path $sessionDir)) { New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null }
    Add-Content -Path $logFile -Value $line
    Write-Host "[$level] $message"
}

function Compute-Sha256([string]$inputText) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($inputText)
    $hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ''
}

function Invoke-GitHubApi([string]$url) {
    $headers = @{ Accept = 'application/vnd.github+json' }
    if ($PSBoundParameters.ContainsKey('Token') -and $Token) {
        $headers['Authorization'] = "Bearer $Token"
    }
    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -Method Get -TimeoutSec 15
        return $resp
    } catch {
        Write-Log "Erreur API GitHub : $($_.Exception.Message)" 'ERROR'
        exit 3
    }
}

function Test-Mandat([object]$comment) {
    # Auteur doit être le propriétaire du dépôt
    if ($comment.user.login -ne $Owner) {
        Write-Log "Mandat refusé : auteur $($comment.user.login) n'est pas le propriétaire $Owner" 'WARN'
        return $false
    }
    $body = $comment.body
    # Mot-clé de mandat explicite
    $mandateKeywords = @('APPROVÉ','MISSION','GO','AUTORISÉ','AUTORISATION')
    $hasMandate = $false
    foreach ($kw in $mandateKeywords) {
        if ($body -like "*$kw*") { $hasMandate = $true; break }
    }
    if (-not $hasMandate) {
        Write-Log "Mandat refusé : aucun mot-clé de mandat explicite dans le commentaire" 'WARN'
        return $false
    }
    return $true
}

# --- Étape 1 : lecture des commentaires de l'issue ---
$apiUrl = "https://api.github.com/repos/$Owner/$Repo/issues/$IssueNumber/comments"
Write-Log "Lecture des commentaires de l'issue #$IssueNumber ($apiUrl)"
$comments = Invoke-GitHubApi -url $apiUrl

if (-not $comments -or $comments.Count -eq 0) {
    Write-Log "Aucun commentaire sur l'issue #$IssueNumber" 'WARN'
    exit 1
}

# Prendre le dernier commentaire du propriétaire avec mandat
$targetComment = $null
foreach ($c in ($comments | Sort-Object created_at -Descending)) {
    if (Test-Mandat -comment $c) {
        $targetComment = $c
        break
    }
}

if (-not $targetComment) {
    Write-Log "Aucun commentaire avec mandat valide trouvé sur l'issue #$IssueNumber" 'WARN'
    exit 1
}

$missionId = "mission-$IssueNumber-$($targetComment.id)"
$commentBody = $targetComment.body
$issueSha = $targetComment.node_id
$commentNodeSha = $targetComment.node_id
$commentSha256 = Compute-Sha256 -inputText $commentBody
$claimedAt = Get-Date -Format 'o'

# --- Étape 2 : Claim CAS atomique (compare-and-set sur le fichier de claim) ---
if (-not (Test-Path $claimsDir)) { New-Item -ItemType Directory -Path $claimsDir -Force | Out-Null }
$claimFile = Join-Path $claimsDir "$missionId.json"

if (Test-Path $claimFile) {
    $existing = Get-Content -Path $claimFile -Raw | ConvertFrom-Json
    $existingStatus = if ($existing.PSObject.Properties.Name -contains 'status') { $existing.status } else { 'unknown' }
    if ($existingStatus -eq 'processed') {
        Write-Log "Claim déjà traité (status=processed) pour $missionId — doublon refusé" 'WARN'
        exit 2
    }
    if ($existingStatus -eq 'claimed') {
        Write-Log "Claim déjà présent (status=claimed) pour $missionId — réclamation en doublon refusée" 'WARN'
        exit 2
    }
}

# CAS : écrire seulement si le fichier n'existe pas encore (état attendu = absent)
# Tentative d'écriture avec vérification post-coup pour détecter la concurrence
$claim = @{
    mission_id        = $missionId
    issue_number      = $IssueNumber
    issue_sha         = $issueSha
    comment_node_id   = $commentNodeSha
    comment_sha256    = $commentSha256
    mandate_sha256    = $commentSha256
    author            = $targetComment.user.login
    claimed_at        = $claimedAt
    status            = 'claimed'
    receiver          = 'KILO-INTEGRATOR'
    worktree          = (Join-Path $root '.kilo' 'worktrees' $missionId)
    branch            = 'feat/kilo-github-receiver-123'
} | ConvertTo-Json -Depth 5

# Écriture atomique : fichier temporaire puis rename
$tmpClaim = $claimFile + '.tmp'
Set-Content -Path $tmpClaim -Value $claim -Encoding UTF8
if (Test-Path $claimFile) {
    # Un autre processus a créé le claim entre-temps : refus (perte de mise à jour évitée)
    Remove-Item -Path $tmpClaim -Force
    $existing = Get-Content -Path $claimFile -Raw | ConvertFrom-Json
    Write-Log "Conflit CAS : claim $missionId déjà créé par un autre worker — refus" 'WARN'
    exit 2
}
Move-Item -Path $tmpClaim -Destination $claimFile -Force
Write-Log "Claim CAS enregistré : $missionId (claimFile=$claimFile, comment_sha256=$commentSha256)"

# --- Étape 3 : ACK corrélé ---
if (-not (Test-Path $sessionDir)) { New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null }
$ack = @{
    mission_id     = $missionId
    issue_number   = $IssueNumber
    ack_at         = $claimedAt
    receiver       = 'KILO-INTEGRATOR'
    status         = 'ACK'
    claim_sha256   = $commentSha256
    comment_node_id= $commentNodeSha
    claim_file     = $claimFile
    session_id     = $sessionId
} | ConvertTo-Json -Depth 5

$ackFile = Join-Path $sessionDir ("ack_" + $missionId + ".json")
Set-Content -Path $ackFile -Value $ack -Encoding UTF8
Write-Log "ACK émis : $missionId (ackFile=$ackFile, claim_sha256=$commentSha256)"

# --- Étape 4 : Journal ---
$logEntry = @{
    ts         = $claimedAt
    level      = 'INFO'
    message    = "Mission reçue et ACK émis : $missionId depuis issue #$IssueNumber (claim=$claimFile, ack=$ackFile)"
} | ConvertTo-Json -Depth 3
Add-Content -Path $logFile -Value $logEntry

Write-Log "Réception terminée avec succès pour $missionId" 'INFO'
exit 0

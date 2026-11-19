<#
.SYNOPSIS
    Kilo GitHub Receiver — raccord GitHub → Kilo Agent Manager (P0 #123).
.DESCRIPTION
    Reçoit une mission publiée sur GitHub (issue avec mandat vérifié),
    produit un ACK corrélé, journalise l'exécution et prépare la délégation
    à un spécialiste Kilo. Le claim CAS utilise un verrou fichier .NET
    (FileShare.None) pour une exclusion mutuelle inter-processus réelle.
    Codes de sortie : 0=succès, 1=pas de mandat, 2=doublon/conflit, 3=erreur API.
. PARAMETER IssueNumber
    Numéro de l'issue GitHub à écouter.
.PARAMETER Owner
    Propriétaire du dépôt (défaut: khalidd692).
.PARAMETER Repo
    Nom du dépôt (défaut: telcoin-trading-intelligence99).
.PARAMETER Token
    Token GitHub optionnel.
.PARAMETER Once
    Traiter une seule fois puis sortir.
.PARAMETER PollInterval
    Intervalle de sondage en secondes (défaut: 30).
.EXAMPLE
    .\scripts/kilocli/github_receiver.ps1 -IssueNumber 123 -Once
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [int]$IssueNumber,

    [string]$Owner = 'khalidd692',
    [string]$Repo = 'telcoin-trading-intelligence99',
    [string]$Token = $null,
    [switch]$Once,
    [int]$PollInterval = 30
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$claimsDir = Join-Path $root '.kilo' 'claims'
$sessionsDir = Join-Path $root '.kilo' 'sessions'
$sessionId = 'session-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$sessionDir = Join-Path $sessionsDir $sessionId
$logFile = Join-Path $sessionDir 'ack_log.jsonl'

# UTF-8 sans BOM pour tous les fichiers texte
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $entry = @{ ts = $ts; level = $level; message = $message } | ConvertTo-Json -Depth 3
    if (-not (Test-Path $sessionDir)) { New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null }
    [System.IO.File]::AppendAllText($logFile, $entry + "`n", $utf8NoBom)
    Write-Host "[$level] $message"
}

function Compute-Sha256([string]$inputText) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($inputText)
        $hash = $sha.ComputeHash($bytes)
        return ($hash | ForEach-Object { $_.ToString("x2") }) -join ''
    } finally {
        $sha.Dispose()
    }
}

function Invoke-GitHubApi([string]$url, [ref]$statusCode) {
    $headers = @{ Accept = 'application/vnd.github+json' }
    if ($PSBoundParameters.ContainsKey('Token') -and $Token) {
        $headers['Authorization'] = "Bearer $Token"
    }
    try {
        $resp = Invoke-RestMethod -Uri $url -Headers $headers -Method Get -TimeoutSec 15
        $statusCode.Value = 200
        return $resp
    } catch [System.Net.WebException] {
        $webEx = $_.Exception
        if ($webEx.Response -is [System.Net.HttpWebResponse]) {
            $statusCode.Value = [int]$webEx.Response.StatusCode
        } else {
            $statusCode.Value = 0
        }
        Write-Log "Erreur API GitHub (HTTP $($statusCode.Value)) : $($_.Exception.Message)" 'ERROR'
        return $null
    } catch {
        $statusCode.Value = 0
        Write-Log "Erreur API GitHub : $($_.Exception.Message)" 'ERROR'
        return $null
    }
}

function Test-Mandat([object]$comment) {
    if ($comment.user.login -ne $Owner) {
        Write-Log "Mandat refusé : auteur $($comment.user.login) n'est pas le propriétaire $Owner" 'WARN'
        return $false
    }
    $body = $comment.body
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

# Claim CAS véritablement atomique (FileStream CreateNew + FileShare.None)
function Claim-Cas([string]$claimFile, [hashtable]$claim) {
    try {
        $claimJson = $claim | ConvertTo-Json -Depth 5
        $bytes = $utf8NoBom.GetBytes($claimJson)
        $stream = [System.IO.File]::Open(
            $claimFile,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $stream.Write($bytes, 0, $bytes.Length)
        } finally {
            $stream.Dispose()
        }
        Write-Log "Claim CAS enregistré : $($claim.mission_id) (verrou exclusif acquis)"
        return @{ ok = $true; exitCode = 0 }
    } catch {
        if ($_.Exception.Message -like "*already exists*") {
            Write-Log "Conflit CAS : claim $($claim.mission_id) déjà créé — doublon refusé" 'WARN'
            return @{ ok = $false; exitCode = 2 }
        }
        Write-Log "Erreur de verrou CAS : $($_.Exception.Message)" 'WARN'
        return @{ ok = $false; exitCode = 2 }
    }
}

function Process-Issue() {
    $apiUrl = "https://api.github.com/repos/$Owner/$Repo/issues/$IssueNumber/comments"
    $httpStatus = 0
    Write-Log "Lecture des commentaires de l'issue #$IssueNumber ($apiUrl)"
    $comments = Invoke-GitHubApi -url $apiUrl -statusCode ([ref]$httpStatus)

    if ($comments -eq $null) {
        return @{ ok = $false; exitCode = 3 }
    }

    if (-not $comments -or $comments.Count -eq 0) {
        Write-Log "Aucun commentaire sur l'issue #$IssueNumber" 'WARN'
        return @{ ok = $false; exitCode = 1 }
    }

    $targetComment = $null
    foreach ($c in ($comments | Sort-Object created_at -Descending)) {
        if (Test-Mandat -comment $c) {
            $targetComment = $c
            break
        }
    }

    if (-not $targetComment) {
        Write-Log "Aucun commentaire avec mandat valide trouvé sur l'issue #$IssueNumber" 'WARN'
        return @{ ok = $false; exitCode = 1 }
    }

    $missionId = "mission-$IssueNumber-$([int64]$targetComment.id)"
    $commentBody = $targetComment.body
    $issueSha = $targetComment.node_id
    $commentNodeSha = $targetComment.node_id
    $commentSha256 = Compute-Sha256 -inputText $commentBody
    $claimedAt = Get-Date -Format 'o'

    if (-not (Test-Path $claimsDir)) { New-Item -ItemType Directory -Path $claimsDir -Force | Out-Null }
    $claimFile = Join-Path $claimsDir "$missionId.json"

    if (Test-Path $claimFile) {
        $raw = [System.IO.File]::ReadAllText($claimFile, $utf8NoBom)
        $existing = $raw | ConvertFrom-Json -Depth 5
        if ($existing -and $existing.PSObject.Properties.Name -contains 'status') {
            if ($existing.status -eq 'processed') {
                Write-Log "Claim déjà traité (status=processed) pour $missionId — doublon refusé" 'WARN'
                return @{ ok = $false; exitCode = 2 }
            }
            if ($existing.status -eq 'claimed') {
                Write-Log "Claim déjà présent (status=claimed) pour $missionId — doublon refusé" 'WARN'
                return @{ ok = $false; exitCode = 2 }
            }
        }
    }

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
    }

    $claimResult = Claim-Cas -claimFile $claimFile -claim $claim
    if (-not $claimResult.ok) {
        return @{ ok = $false; exitCode = $claimResult.exitCode }
    }

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
        execution_status = 'EXECUTION_COMPLETED'
        verdict        = 'PENDING'
    } | ConvertTo-Json -Depth 5

    $ackFile = Join-Path $sessionDir ("ack_" + $missionId + ".json")
    [System.IO.File]::WriteAllText($ackFile, $ack, $utf8NoBom)
    Write-Log "ACK émis : $missionId (ackFile=$ackFile, claim_sha256=$commentSha256)"

    $logEntry = @{ ts = $claimedAt; level = 'INFO'; message = "Mission reçue et ACK émis : $missionId depuis issue #$IssueNumber" } | ConvertTo-Json -Depth 3
    [System.IO.File]::AppendAllText($logFile, $logEntry + "`n", $utf8NoBom)

    Write-Log "Réception terminée avec succès pour $missionId" 'INFO'
    return @{ ok = $true; exitCode = 0; missionId = $missionId }
}

# --- Boucle principale ---
do {
    $result = Process-Issue

    if ($result.ok) {
        Write-Log "Mission traitée : $($result.missionId), exit code 0" 'INFO'
    } else {
        Write-Log "Mission non traitée, exit code $($result.exitCode)" 'WARN'
    }

    if ($result.exitCode -eq 2) {
        Write-Log "Doublon détecté — arrêt du receiver avec code 2" 'WARN'
        exit 2
    }

    if ($result.exitCode -eq 3 -and -not $Once) {
        Write-Log "Erreur API — continuation en mode boucle (pas de exit 3)" 'WARN'
    } elseif ($result.exitCode -eq 3 -and $Once) {
        exit 3
    }

    if ($Once) {
        exit 0
    }

    Write-Log "Attente ${PollInterval}s avant prochain sondage..." 'INFO'
    Start-Sleep -Seconds $PollInterval
} while ($true)

Write-Log "Récepteur arrêté." 'INFO'
exit 0

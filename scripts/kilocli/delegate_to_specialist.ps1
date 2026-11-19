<#
.SYNOPSIS
    Kilo Specialist Delegate — délégation d'une mission claimée à un spécialiste (P0 #123).
.DESCRIPTION
    Prend un mission_id, lit le claim CAS, assigne un spécialiste Kilo et produit
    un RESULT/EVIDENCE corrélé. Aucun appel de modèle n'est effectué.
.PARAMETER MissionId
    Identifiant de la mission (ex: mission-123-7011840642).
.PARAMETER Specialist
    Nom du spécialiste cible (ex: tel99-analyst). Défaut: tel99-analyst.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$MissionId,

    [string]$Specialist = 'tel99-analyst'
)

$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$claimsDir = Join-Path $root '.kilo' 'claims'
$specialistsDir = Join-Path $root '.kilo' 'specialists'
$workDir = Join-Path $specialistsDir $MissionId
$delegationLog = Join-Path $workDir 'delegation_log.jsonl'

function Write-Log([string]$message, [string]$level='INFO') {
    $ts = Get-Date -Format 'o'
    $line = "{`"ts`":`"$ts`",`"level`":`"$level`",`"message`":`"$message`"}"
    if (-not (Test-Path $workDir)) { New-Item -ItemType Directory -Path $workDir -Force | Out-Null }
    Add-Content -Path $delegationLog -Value $line
    Write-Host "[$level] $message"
}

# --- Étape 1 : lecture du claim CAS ---
$claimFile = Join-Path $claimsDir "$MissionId.json"
if (-not (Test-Path $claimFile)) {
    Write-Log "Claim introuvable pour $MissionId" 'ERROR'
    exit 1
}
$claim = Get-Content -Path $claimFile -Raw | ConvertFrom-Json
if ($claim.status -ne 'claimed') {
    Write-Log "Claim déjà traité (status=$($claim.status)) pour $MissionId" 'WARN'
    exit 2
}
Write-Log "Claim lu : $MissionId (auteur=$($claim.author), issu de issue #$($claim.issue_number))"

# --- Étape 2 : assignation du spécialiste ---
$assignedAt = Get-Date -Format 'o'
$missionJson = @{
    mission_id   = $MissionId
    issue_number = $claim.issue_number
    author       = $claim.author
    claimed_at   = $claim.claimed_at
    assigned_to  = $Specialist
    assigned_at  = $assignedAt
    status       = 'assigned'
} | ConvertTo-Json -Depth 5

$missionFile = Join-Path $workDir 'mission.json'
Set-Content -Path $missionFile -Value $missionJson
Write-Log "Spécialiste assigné : $Specialist (missionFile=$missionFile)"

# --- Étape 3 : résultat de l'exécution (simulation déterministe, pas d'appel modèle) ---
$result = @{
    mission_id     = $MissionId
    specialist     = $Specialist
    result         = 'MISSION_RECU_TRAITE'
    evidence_sha   = $claim.comment_sha
    status         = 'completed'
    completed_at   = $assignedAt
    source         = 'claim_cas_' + $MissionId
} | ConvertTo-Json -Depth 5

$resultFile = Join-Path $workDir 'result.json'
Set-Content -Path $resultFile -Value $result
Write-Log "Résultat produit : $MissionId par $Specialist (resultFile=$resultFile, evidence_sha=$($claim.comment_sha))"

# --- Étape 4 : mise à jour du claim (marqué comme traité) ---
$claimUpdated = [ordered]@{
    mission_id     = $claim.mission_id
    issue_number   = $claim.issue_number
    issue_sha      = $claim.issue_sha
    comment_sha    = $claim.comment_sha
    author         = $claim.author
    claimed_at     = $claim.claimed_at
    status         = 'processed'
    processed_at   = $assignedAt
    processed_by   = $Specialist
    receiver       = $claim.receiver
    worktree       = $claim.worktree
    branch         = $claim.branch
} | ConvertTo-Json -Depth 5

Set-Content -Path $claimFile -Value $claimUpdated
Write-Log "Claim mis à jour : $MissionId status=processed"

Write-Log "Délégation terminée avec succès pour $MissionId vers $Specialist" 'INFO'
exit 0

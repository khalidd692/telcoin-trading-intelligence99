# Safe sequential finalization, run from isolated Git worktree. No main merge.
$ErrorActionPreference = "Stop"
$desk = "$HOME\Desktop"
$repo = "$desk\TEL99_CAPABILITY_UPGRADE_20261125"
$fix = $PSScriptRoot
$base = "http://127.0.0.1:8765"
$run = "$desk\TEL99_FINALISATION\$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory -Force $run | Out-Null
Start-Transcript -Path "$run\finalisation.log"
function Check-Native([string]$message) {
    if ($LASTEXITCODE -ne 0) { throw $message }
}
function Get-Campaigns {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.Name -match '^(python.*|pwsh|powershell)\.exe$' -and
        $_.CommandLine -match 'run_full_local_chain|competency_matrix|run_unseen_v[34]_eval|run_post_phase2_recettes|autonomous_project_runner|run_hour_autonomy_acceptance|run_groq_hybrid_benchmark|run_dialogue_live_acceptance'
    })
}
function Get-CC { Invoke-RestMethod "$base/api/cc/state" -TimeoutSec 20 }
function Test-Idle($s) {
    return (($s.engines.active_inference_leases_count -eq 0) -and
        (@($s.chat_jobs | Where-Object {$_.status -notin @("DONE","ERROR","CANCELLED")}).Count -eq 0) -and
        (@($s.projects | Where-Object {$_.runner_active}).Count -eq 0) -and
        (@(Get-Campaigns).Count -eq 0))
}
function Wait-Idle {
    $deadline = (Get-Date).AddHours(24)
    do {
        $state = Get-CC
        if (Test-Idle $state) { return $state }
        if ((Get-Date) -ge $deadline) { throw "Idle timeout: no process stopped." }
        Write-Host "Campagnes ou conversations actives : attente propre."
        Start-Sleep -Seconds 60
    } while ($true)
}
function Start-CC {
    pwsh -NoProfile -File "$repo\launch-tel99.ps1" -Mode CommandCenter -Detached
    Check-Native "Command Center launcher failed"
    for ($i=0; $i -lt 30; $i++) {
        try {
            $h = Invoke-RestMethod "$base/health" -TimeoutSec 2
            if ($h.ok) { return }
        } catch {}
        Start-Sleep -Seconds 2
    }
    throw "Command Center health not confirmed"
}
try {
    Set-Location $fix
    if ((git branch --show-current) -ne "fix/groq-model-quotas") { throw "Unexpected candidate branch" }
    if (git status --porcelain) { throw "Candidate worktree dirty" }
    $target = (git rev-parse HEAD).Trim()
    Check-Native "Cannot resolve candidate"
    Write-Host "=== 1. TESTS HORS LIGNE ==="
    foreach ($suite in @("test_groq_model_quotas.py","test_v4_quota_recovery.py","test_provider_router.py","test_command_center.py","test_dialogue_coverage.py")) {
        python -B -m unittest discover -s tests -p $suite -v
        Check-Native "Failed suite: $suite"
    }

    Write-Host "=== 2. ATTENTE DES CAMPAGNES EXISTANTES ==="
    $s = Wait-Idle
    if ((git -C $repo branch --show-current) -ne "agents/tel99-capability-upgrade-20261125") { throw "Unexpected deployment branch" }
    if (git -C $repo status --porcelain) { throw "Deployment worktree dirty" }
    git -C $repo merge-base --is-ancestor HEAD $target
    Check-Native "Not a fast-forward candidate"
    $current = (git -C $repo rev-parse HEAD).Trim()
    if ($current -ne $target) {
        Write-Host "=== 3. INTEGRATION ET REDEMARRAGE ==="
        $owners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique)
        if ($owners.Count -ne 1) { throw "Unexpected server owners" }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
        if ($proc.CommandLine -notmatch 'scripts\.agents\.automation\.multi_cockpit') { throw "Unexpected server" }
        if (-not (Test-Idle (Get-CC))) { throw "Activity resumed before deployment" }
        Stop-Process -Id $proc.ProcessId
        try {
            git -C $repo merge --ff-only $target
            Check-Native "Integration failed"
        } finally {
            Start-CC
        }
    }
    else {
        Write-Host "Candidate already integrated; server must expose new model quotas."
    }
    Set-Location $repo
    $s = Get-CC
    if (-not $s.cloud_budgets.groq.models) { throw "New quota router not visible; restart/diagnose server before proceeding." }
    $s.cloud_budgets.groq | ConvertTo-Json -Depth 10
    $s.projects | Select-Object name,status,missions_accepted,missions_total | Format-Table -AutoSize

    Write-Host "=== 4. RECETTE CONVERSATIONNELLE REELLE ==="
    $s = Wait-Idle
    if ($s.engines.available_memory_mib -ge 2500) {
        python -B tests/run_dialogue_live_acceptance.py --out "$run\dialogue"
        if ($LASTEXITCODE -ne 0) { Write-Warning "Dialogue not validated; inspect report. No false pass." }
    } else { Write-Warning "Dialogue deferred: RAM below 2500 MiB." }

    Write-Host "=== 5. REPRISE V4 CIBLEE ==="
    $s = Wait-Idle
    python -B -m scripts.agents.automation.run_unseen_v4_eval --recover-quota-errors
    Check-Native "V4 dry run failed"
    $g = $s.cloud_budgets.groq
    if (-not $g.legacy_unattributed -and $g.remaining_background_tokens_budget -ge 2000 -and $s.engines.available_memory_mib -ge 2500) {
        python -B -m scripts.agents.automation.run_unseen_v4_eval --recover-quota-errors --execute-recovery |
            Tee-Object -FilePath "$run\v4_recovery.log"
        if ($LASTEXITCODE -ne 0) { Write-Warning "Recovery interrupted; preserve checkpoints." }
    } else { Write-Warning "V4 deferred: RAM, quota or legacy migration." }

    Write-Host "=== 6. ENDURANCE 60 MINUTES ==="
    $s = Wait-Idle
    if ($s.engines.available_memory_mib -ge 2500) {
        $end = "$run\endurance"
        New-Item -ItemType Directory -Force $end | Out-Null
        python -B tests/run_hour_autonomy_acceptance.py --min-minutes 60 --min-free-ram-mb 2500 --state-root "$end\hour_campaign" --report "$end\hour_campaign_report.json"
        if ($LASTEXITCODE -ne 0) { Write-Warning "Endurance runner returned failure." }
        if (Test-Path "$end\hour_campaign_report.json") {
            $e = Get-Content "$end\hour_campaign_report.json" -Raw | ConvertFrom-Json
            $e | Select-Object status,duration_minutes,missions_accepted,missions_blocked,missions_total
            if ($e.duration_minutes -ge 60 -and $e.missions_accepted -gt 0 -and $null -ne $e.missions_blocked -and $e.missions_blocked -eq 0) {
                Write-Host "Endurance business criteria met"
            } else { Write-Warning "Endurance not validated." }
        } else { Write-Warning "Missing endurance report." }
    } else { Write-Warning "Endurance deferred: RAM below 2500 MiB." }

    Write-Host "=== 7. BILAN ==="
    $s = Get-CC
    $s.certification.matrix_global | ConvertTo-Json -Depth 6
    $s.certification.phase2_chain | ConvertTo-Json -Depth 8
    $s.projects | Select-Object name,status,missions_accepted,missions_total | Format-Table -AutoSize
    git -C $repo log -1 --oneline
    Write-Host "Reports: $run"
} finally {
    Stop-Transcript
}

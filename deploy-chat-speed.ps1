# Install the conversation speed update only, after the existing finalizer exits.
# Never rerun V4/endurance or stop agents. Run from the isolated candidate worktree.
$ErrorActionPreference = "Stop"
$repo = "$HOME\Desktop\TEL99_CAPABILITY_UPGRADE_20261125"
$base = "http://127.0.0.1:8765"
$required = "5fe92ef430c5c4e11dc38138d1af240d74b34f64"
$mutex = [System.Threading.Mutex]::new($false, "Local\TEL99_CHAT_SPEED_DEPLOY")
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw "Speed deployment already running." }
    Set-Location $PSScriptRoot
    if ((git branch --show-current) -ne "fix/groq-model-quotas" -or (git status --porcelain)) { throw "Unexpected or dirty candidate worktree." }
    $target = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Cannot resolve candidate." }
    $run = "$HOME\Desktop\TEL99_FINALISATION\CHAT_SPEED_$(Get-Date -Format yyyyMMdd_HHmmss)"
    New-Item -ItemType Directory -Force $run | Out-Null
    Start-Transcript -Path "$run\deployment.log"
    try {
        Write-Host "=== Tests hors ligne ==="
        foreach ($suite in @("test_groq_model_quotas.py","test_v4_quota_recovery.py","test_provider_router.py","test_command_center.py","test_dialogue_coverage.py","test_chat_response_modes.py")) {
            python -B -m unittest discover -s tests -p $suite -v
            if ($LASTEXITCODE -ne 0) { throw "Failed suite: $suite" }
        }
        node --check scripts/agents/automation/command_center_ui/app.js
        if ($LASTEXITCODE -ne 0) { throw "Invalid JavaScript." }

        function Test-Idle {
            $active = @(Get-CimInstance Win32_Process | Where-Object {
                $_.ProcessId -ne $PID -and
                $_.Name -match '^(python.*|pwsh|powershell)\.exe$' -and
                $_.CommandLine -match 'finalize-tel99-safe\.ps1|run_full_local_chain|competency_matrix|run_unseen_v[34]_eval|run_post_phase2_recettes|autonomous_project_runner|run_hour_autonomy_acceptance|run_groq_hybrid_benchmark|run_dialogue_live_acceptance'
            })
            if ($active.Count) { return $false }
            $s = Invoke-RestMethod "$base/api/cc/state" -TimeoutSec 20
            return ($s.engines.active_inference_leases_count -eq 0 -and
                @($s.chat_jobs | Where-Object {$_.status -notin @("DONE","ERROR","CANCELLED")}).Count -eq 0 -and
                @($s.projects | Where-Object {$_.runner_active}).Count -eq 0)
        }
        $deadline = (Get-Date).AddHours(24)
        while (-not (Test-Idle)) {
            if ((Get-Date) -ge $deadline) { throw "Idle timeout; no process stopped." }
            Write-Host "Finalisation ou campagnes actives : attente propre."
            Start-Sleep -Seconds 60
        }
        if ((git -C $repo branch --show-current) -ne "agents/tel99-capability-upgrade-20261125" -or (git -C $repo status --porcelain)) {
            throw "Unexpected or dirty deployment branch."
        }
        git -C $repo merge-base --is-ancestor $required HEAD
        if ($LASTEXITCODE -ne 0) { throw "Previous finalization not integrated. Diagnose its report first." }
        git -C $repo merge-base --is-ancestor HEAD $target
        if ($LASTEXITCODE -ne 0) { throw "Not a fast-forward candidate." }
        if ((git -C $repo rev-parse HEAD).Trim() -ne $target) {
            $owners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object -ExpandProperty OwningProcess -Unique)
            if ($owners.Count -ne 1) { throw "Unexpected server owners." }
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])"
            if ($proc.CommandLine -notmatch 'scripts\.agents\.automation\.multi_cockpit') { throw "Unexpected server." }
            if (-not (Test-Idle)) { throw "Activity resumed before deployment." }
            Stop-Process -Id $proc.ProcessId
            try {
                git -C $repo merge --ff-only $target
                if ($LASTEXITCODE -ne 0) { throw "Integration failed." }
            } finally {
                pwsh -NoProfile -File "$repo\launch-tel99.ps1" -Mode CommandCenter -Detached
            }
        }
        $ready = $false
        for ($i=0; $i -lt 30; $i++) {
            try {
                $html = Invoke-WebRequest "$base/" -TimeoutSec 2
                if ($html.Content -match 'id="chatResponseMode"') { $ready = $true; break }
            } catch {}
            Start-Sleep -Seconds 2
        }
        if (-not $ready) { throw "New response-mode UI not verified." }
        Write-Host "Modes disponibles. Actualisez le navigateur (Ctrl+F5)."
        Write-Host "=== Mesure locale reelle ==="
        $s = Invoke-RestMethod "$base/api/cc/state" -TimeoutSec 20
        if ((Test-Idle) -and $s.engines.available_memory_mib -ge 2500) {
            Set-Location $repo
            python -B tests/run_dialogue_live_acceptance.py --mode auto --out "$run\dialogue"
            if ($LASTEXITCODE -ne 0) { Write-Warning "Dialogue not validated; inspect report." }
        } else { Write-Warning "Live measurement deferred; resources busy or RAM insufficient." }
        Write-Host "Reports: $run"
    } finally { Stop-Transcript }
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

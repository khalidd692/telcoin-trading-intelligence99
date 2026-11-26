# Standalone autonomous runner for TEL99 G8 Proactive Brief.
# Independent of Gemini/IDE sessions. Never wakes PC, never spends money,
# protects active campaigns (never unloads Ollama while another campaign runs),
# respects owner priority, CAS leases, RAM guard, and daily deduplication.
param(
    [string]$Trigger = "windows_task_scheduler",
    [int]$MaxRetries = 8,
    [int]$RetryWaitSeconds = 300,
    [switch]$WaitForSafeCheckpoint
)
$ErrorActionPreference = "Continue"
$Repo = "C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125"
$PyExe = "C:\Users\sabri\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
$Log = "C:\Users\sabri\Desktop\TEL99_LOCAL_CHAIN_STATE\proactive_night_task.log"

function Log-Night([string]$m) {
    "$(Get-Date -Format o) [$Trigger] $m" | Out-File -FilePath $Log -Append -Encoding utf8
}

function Get-ActiveCampaigns {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.Name -match '^(python.*|pwsh|powershell)\.exe$' -and
        $_.CommandLine -match 'run_hour_autonomy_acceptance|run_unseen_v[34]_eval|autonomous_project_runner|run_full_local_chain|competency_matrix'
    })
}

function Get-ActiveLeasesCount {
    try {
        $s = Invoke-RestMethod "http://127.0.0.1:8765/api/cc/state" -TimeoutSec 10
        return [int]($s.engines.active_inference_leases_count)
    } catch {
        return 0
    }
}

New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
Log-Night "Autonomous G8 runner started (PID=$PID, MaxRetries=$MaxRetries, WaitForSafeCheckpoint=$WaitForSafeCheckpoint)."

Push-Location $Repo
try {
    if ($WaitForSafeCheckpoint) {
        $deadline = (Get-Date).AddHours(3)
        while ((Get-Date) -lt $deadline) {
            $camps = Get-ActiveCampaigns
            $leases = Get-ActiveLeasesCount
            if ($camps.Count -eq 0 -and $leases -eq 0) {
                Log-Night "Safe checkpoint reached (active_campaigns=0, active_leases=0). Proceeding with TEL99 G8 cycle."
                break
            }
            $pids = ($camps | Select-Object -ExpandProperty ProcessId) -join ","
            Log-Night "Protecting active campaign(s) (PIDs=[$pids], leases=$leases) — waiting 60s for safe checkpoint without touching Ollama..."
            Start-Sleep -Seconds 60
        }
    }

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        $camps = Get-ActiveCampaigns
        $leases = Get-ActiveLeasesCount
        if ($camps.Count -gt 0 -or $leases -gt 0) {
            Log-Night "Attempt $attempt/$MaxRetries deferred: active_campaigns=$($camps.Count) active_leases=$leases (protecting Ollama)."
            if ($attempt -lt $MaxRetries) { Start-Sleep -Seconds $RetryWaitSeconds; continue }
            break
        }
        Log-Night "Attempt $attempt/${MaxRetries}: executing TEL99 autonomous 3-role G8 cycle (continuous_learning_worker --action run-proactive-live --publish-g7)..."
        $out = & $PyExe -B -m scripts.agents.automation.continuous_learning_worker --action run-proactive-live --trigger $Trigger --publish-g7 2>&1
        $rc = $LASTEXITCODE
        $out | Out-File -FilePath $Log -Append -Encoding utf8
        Log-Night "Attempt $attempt exited with rc=$rc."
        if ($rc -eq 0) {
            Log-Night "Proactive G8 cycle completed cleanly (DONE/PROPOSAL/NO_USEFUL_TASK)."
            break
        }
        if ($attempt -lt $MaxRetries) {
            Log-Night "Cycle deferred; sleeping ${RetryWaitSeconds}s before bounded retry..."
            Start-Sleep -Seconds $RetryWaitSeconds
        } else {
            Log-Night "Max retries reached; DEFERRED state recorded and published to G7."
        }
    }

    # Protect active campaigns: ONLY unload Ollama if 0 campaigns & 0 CAS leases are active!
    $campsAfter = Get-ActiveCampaigns
    $leasesAfter = Get-ActiveLeasesCount
    if ($campsAfter.Count -eq 0 -and $leasesAfter -eq 0) {
        Log-Night "No active campaigns or CAS leases — safely unloading Ollama to preserve host RAM..."
        & $PyExe -B -c "from scripts.agents.automation import ide_coordination; print('UNLOADED:', ide_coordination.unload_ollama_models())" *>> $Log
    } else {
        Log-Night "Skipping Ollama unload to protect active campaign(s) (campaigns=$($campsAfter.Count), leases=$leasesAfter)."
    }
} finally {
    Pop-Location
}
Log-Night "Autonomous G8 runner finished."

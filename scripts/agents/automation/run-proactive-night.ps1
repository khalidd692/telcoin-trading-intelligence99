# Standalone Windows Task Scheduler runner for TEL99 G8 Overnight Proactive Brief.
# Independent of Gemini/IDE sessions. Never wakes PC, never spends money, respects owner priority & RAM guard.
param(
    [string]$Trigger = "windows_task_scheduler",
    [int]$MaxRetries = 3,
    [int]$RetryWaitSeconds = 900
)
$ErrorActionPreference = "Continue"
$Repo = "C:\Users\sabri\Desktop\TEL99_CAPABILITY_UPGRADE_20261125"
$PyExe = "C:\Users\sabri\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe"
$Log = "C:\Users\sabri\Desktop\TEL99_LOCAL_CHAIN_STATE\proactive_night_task.log"

function Log-Night([string]$m) {
    "$(Get-Date -Format o) [$Trigger] $m" | Out-File -FilePath $Log -Append -Encoding utf8
}

New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
Log-Night "Night proactive runner started (PID=$PID, MaxRetries=$MaxRetries)."

Push-Location $Repo
try {
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        Log-Night "Attempt $attempt/$MaxRetries: running continuous_learning_worker --action run-proactive-live..."
        $out = & $PyExe -B -m scripts.agents.automation.continuous_learning_worker --action run-proactive-live --trigger $Trigger --publish-g7 2>&1
        $rc = $LASTEXITCODE
        $out | Out-File -FilePath $Log -Append -Encoding utf8
        Log-Night "Attempt $attempt exited with rc=$rc."
        if ($rc -eq 0) {
            Log-Night "Proactive cycle completed cleanly (DONE/PROPOSAL/NO_USEFUL_TASK)."
            break
        }
        if ($attempt -lt $MaxRetries) {
            Log-Night "Resources busy or deferred; sleeping ${RetryWaitSeconds}s inside night window before retry..."
            Start-Sleep -Seconds $RetryWaitSeconds
        } else {
            Log-Night "Max retries reached; DEFERRED state recorded and published to G7."
        }
    }
    Log-Night "Unloading Ollama to preserve host RAM..."
    & $PyExe -B -c "from scripts.agents.automation import ide_coordination; print('UNLOADED:', ide_coordination.unload_ollama_models())" *>> $Log
} finally {
    Pop-Location
}
Log-Night "Night proactive runner finished."

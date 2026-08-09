param(
    [switch]$SkipUtic = $false
)

$ErrorActionPreference = "Stop"

function Log-Step {
    param([string]$Message)
    $time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$time] $Message" -ForegroundColor Cyan
}

function Run-PythonScript {
    param([string]$ScriptPath)
    Log-Step "Running: python $ScriptPath"
    try {
        python $ScriptPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Failed: python $ScriptPath (Exit Code: $LASTEXITCODE)" -ForegroundColor Red
            # We don't stop the orchestrator completely on some steps, but usually it's best to continue if possible or stop.
            # Depending on robustness, maybe we should stop? Let's just log it.
        } else {
            Write-Host "Success: $ScriptPath" -ForegroundColor Green
        }
    } catch {
        Write-Host "Error executing $ScriptPath : $_" -ForegroundColor Red
    }
}

Log-Step "=== EV SafeCharge Daily Data Pipeline Update Started ==="

# 1. Lightsail pull
Log-Step "Step 1: Pulling Lightsail loops"
powershell -ExecutionPolicy Bypass -File scripts\pull_lightsail_loops.ps1

# 1b. Fixed daily charger info dump (zcode=27, numOfRows=999; skip if today exists)
# ~25–30 EvCharger API calls — shares daily quota with status loop
Log-Step "Step 1b: Daily charger info dump (fixed conditions)"
Run-PythonScript "apps\data-pipeline\processing\extract\dump_daily_charger_info.py"

# 2. Export Team5 Parking Incremental
Run-PythonScript "apps\data-pipeline\processing\db\export_team5_parking_incremental.py"

# 3. Export Team5 Parking CSV
Run-PythonScript "apps\data-pipeline\processing\db\export_team5_parking_csv.py"

# 4. Join Parking Team5
Run-PythonScript "apps\data-pipeline\processing\extract\join_parking_team5.py"

# 5. Run UTIC Loop (Once)
if (-not $SkipUtic) {
    Log-Step "Step 5: Running UTIC loop (education profile)"
    $env:UTIC_KEY_PROFILE = "education"
    try {
        python apps\data-pipeline\processing\loops\run_utic_loop.py --once
        Write-Host "Success: UTIC loop" -ForegroundColor Green
    } catch {
        Write-Host "Error executing UTIC loop : $_" -ForegroundColor Red
    }
    Remove-Item Env:\UTIC_KEY_PROFILE -ErrorAction SilentlyContinue
} else {
    Log-Step "Step 5: Skipping UTIC loop as requested."
}

# 6. Build D1 Snapshot
Run-PythonScript "apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260716_preprocess_pipeline\src\preprocessing\build_d1_snapshot.py"

# 7. Check Collection Health
Run-PythonScript "apps\data-pipeline\processing\analysis\check_collection_health.py"

# 8. Analyze All Snapshots
Run-PythonScript "apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\analyze_all_snapshots.py"

# 9. Plot and Reliability All Snapshots
Run-PythonScript "apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\plot_and_reliability_all_snapshots.py"

# 10. Copy figures+data (dedicated .py — PS here-string mangled 팀공유 paths)
Log-Step "Step 10: Copying figures to Team Shared folder"
Run-PythonScript "apps\data-pipeline\processing\tools\share\copy_availability_share.py"

# 11. Report KPI
Run-PythonScript "apps\data-pipeline\processing\analysis\report_kpi.py"

# 12. Validate Data Validity
Run-PythonScript "apps\data-pipeline\processing\analysis\validate_data_validity.py"

# 13. Report Integration Readiness
Run-PythonScript "apps\data-pipeline\processing\analysis\report_integration_readiness.py"

Log-Step "=== EV SafeCharge Daily Data Pipeline Update Completed ==="

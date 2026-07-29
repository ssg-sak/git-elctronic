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

# 10. Copy Figures
Log-Step "Step 10: Copying figures to Team Shared folder"
$today = Get-Date -Format "yyyyMMdd"
$targetDir = "docs\팀공유\시간대_가용률_$today\figures"
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Path $targetDir | Out-Null
}
try {
    # It might be in 20260723 hardcoded, or the script might use a dynamic one. Let's just copy from the latest modified snapshot_all_* dir
    $srcBase = Get-ChildItem -Path "docs\data\analysis" -Filter "snapshot_all_*" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($srcBase) {
        $srcPath = Join-Path $srcBase.FullName "figures\*.png"
        Copy-Item -Path $srcPath -Destination $targetDir -Force
        Write-Host "Success: Copied figures from $($srcBase.Name) to $targetDir" -ForegroundColor Green
    } else {
        Write-Host "Warning: Could not find source figures directory." -ForegroundColor Yellow
    }
} catch {
    Write-Host "Error copying figures: $_" -ForegroundColor Red
}

# 11. Report KPI
Run-PythonScript "apps\data-pipeline\processing\analysis\report_kpi.py"

# 12. Validate Data Validity
Run-PythonScript "apps\data-pipeline\processing\analysis\validate_data_validity.py"

# 13. Report Integration Readiness
Run-PythonScript "apps\data-pipeline\processing\analysis\report_integration_readiness.py"

Log-Step "=== EV SafeCharge Daily Data Pipeline Update Completed ==="

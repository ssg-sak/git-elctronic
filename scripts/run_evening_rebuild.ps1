# Evening rebuild after Lightsail already pulled. Regenerates D1/KPI/viz + official status charts.
# D2 full panel rebuild is optional — it can take 1h+; default skip for daily cadence.
param(
    [switch]$SkipUtic = $false,
    [switch]$IncludeD2Panel = $false
)
$ErrorActionPreference = "Continue"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$env:MPLBACKEND = "Agg"

function Step([string]$Name, [scriptblock]$Action) {
    $t = Get-Date -Format "HH:mm:ss"
    Write-Host "[$t] ==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[$t] FAIL $Name exit=$LASTEXITCODE" -ForegroundColor Red
    } else {
        Write-Host "[$t] OK $Name" -ForegroundColor Green
    }
}

Write-Host "=== Evening rebuild (skip Lightsail pull) ===" -ForegroundColor Yellow

Step "1b charger info dump" { python apps\data-pipeline\processing\extract\dump_daily_charger_info.py }
Step "2 team5 parking incremental" { python apps\data-pipeline\processing\db\export_team5_parking_incremental.py }
Step "3 team5 parking csv" { python apps\data-pipeline\processing\db\export_team5_parking_csv.py }
Step "4 join parking" { python apps\data-pipeline\processing\extract\join_parking_team5.py }

if (-not $SkipUtic) {
    Step "5 UTIC once (education)" {
        $env:UTIC_KEY_PROFILE = "education"
        python apps\data-pipeline\processing\loops\run_utic_loop.py --once
        Remove-Item Env:\UTIC_KEY_PROFILE -ErrorAction SilentlyContinue
    }
}

Step "6 D1 snapshot" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260716_preprocess_pipeline\src\preprocessing\build_d1_snapshot.py }
Step "7 collection health" { python apps\data-pipeline\processing\analysis\check_collection_health.py }
Step "8 analyze snapshots" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\analyze_all_snapshots.py }
Step "9 plot reliability" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\plot_and_reliability_all_snapshots.py }

$sb = "apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src"
Step "9b plot extra" { python "$sb\plot_extra_charts.py" }
Step "9c plot advanced" { python "$sb\plot_advanced_charts.py" }
Step "9d plot corrected" { python "$sb\plot_corrected_charts.py" }
Step "9e plot data value" { python "$sb\plot_data_value.py" }
if ($IncludeD2Panel) {
    Step "9f D2 panel" { python "$sb\build_d2_panel.py" }
    Step "9g panel charts" { python apps\data-pipeline\evaluation\viability_tests\analyze_status_panel.py }
} else {
    Write-Host "==> skip D2 panel (pass -IncludeD2Panel to run)" -ForegroundColor DarkYellow
}

Step "10 availability share" { python apps\data-pipeline\processing\tools\share\copy_availability_share.py }
Step "10b status panel share" { python apps\data-pipeline\processing\tools\share\copy_status_panel_share.py }

Step "11 city congestion" { python apps\data-pipeline\processing\analysis\analyze_city_congestion.py }
Step "12 D1 explain" { python apps\data-pipeline\processing\analysis\explain_d1_latest.py }
Step "13 UTIC analysis" { python apps\data-pipeline\processing\analysis\analyze_utic_incidents.py }

Step "14 KPI" { python apps\data-pipeline\processing\analysis\report_kpi.py }
Step "15 validity" { python apps\data-pipeline\processing\analysis\validate_data_validity.py }
Step "16 integration readiness" { python apps\data-pipeline\processing\analysis\report_integration_readiness.py }

Step "17 archive team share" { python apps\data-pipeline\processing\tools\share\archive_team_share.py }
Step "18 pack viz bundle" { python apps\data-pipeline\processing\tools\share\pack_viz_bundle.py }

Write-Host "=== Evening rebuild done ===" -ForegroundColor Yellow

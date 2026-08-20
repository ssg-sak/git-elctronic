param(
    [switch]$SkipPull,
    [string]$AwsHost = "3.36.50.99",
    [string]$AwsUser = "ubuntu",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\LightsailDefaultKey-ap-northeast-2.pem"
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$env:MPLBACKEND = "Agg"

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "==> $Name"
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $Name (exit $LASTEXITCODE)" }
}

if (-not $SkipPull) {
    Invoke-Step "pull Lightsail loop1/loop3" {
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\pull_lightsail_loops.ps1 -AwsHost $AwsHost -AwsUser $AwsUser -KeyPath $KeyPath
    }
}

Invoke-Step "collection health" { python apps\data-pipeline\processing\analysis\check_collection_health.py }
Invoke-Step "snapshot summary" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\analyze_all_snapshots.py }
Invoke-Step "snapshot charts and reliability" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\plot_and_reliability_all_snapshots.py }
Invoke-Step "D2 panel" { python apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\src\build_d2_panel.py }
Invoke-Step "D2 panel charts" { python apps\data-pipeline\evaluation\viability_tests\analyze_status_panel.py }
Invoke-Step "city congestion charts" { python apps\data-pipeline\processing\analysis\analyze_city_congestion.py }

$source = Join-Path $Repo "docs\data\analysis\snapshot_all_20260723"
$summary = Get-Content (Join-Path $source "summary.json") -Raw | ConvertFrom-Json
$stamp = Get-Date -Format "yyyyMMdd"
$teamRoot = Get-ChildItem (Join-Path $Repo "docs") -Directory |
    Where-Object {
        (Test-Path (Join-Path $_.FullName "README.md")) -and
        @((Get-ChildItem $_.FullName -Directory -Filter "*20260728")).Count -ge 2
    } | Select-Object -First 1
if (-not $teamRoot) { throw "Could not locate the team-share root directory." }
$shareAnchor = Get-ChildItem $teamRoot.FullName -Directory -Filter "*20260728" |
    Where-Object {
        $summaryPath = Join-Path $_.FullName "summary.json"
        if (-not (Test-Path $summaryPath)) { return $false }
        $candidate = Get-Content $summaryPath -Raw | ConvertFrom-Json
        return $null -ne $candidate.unique_snapshots
    } |
    Select-Object -First 1
if (-not $shareAnchor) { throw "Could not locate the team-share anchor directory." }
$shareName = $shareAnchor.Name -replace "20260728$", $stamp
$share = Join-Path $teamRoot.FullName $shareName
New-Item -ItemType Directory -Force -Path (Join-Path $share "data"), (Join-Path $share "figures") | Out-Null
Copy-Item (Join-Path $source "availability_by_hour_union.csv"), (Join-Path $source "availability_by_hour_public_vs_residential.csv"), (Join-Path $source "availability_tod.csv"), (Join-Path $source "reliability_checks.json") -Destination (Join-Path $share "data") -Force
Copy-Item (Join-Path $source "figures\*.png") -Destination (Join-Path $share "figures") -Force

$pointer = [ordered]@{
    canonical_artifact = "docs/data/analysis/snapshot_all_20260723"
    artifact_name_legacy = "snapshot_all_20260723"
    as_of_kst = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    latest_snapshot = $summary.last_ts
    first_snapshot = $summary.first_ts
    unique_snapshots = $summary.unique_snapshots
    event_rows = $summary.event_rows
    panel_availability_mean = $summary.panel_avail_mean
    note = "Folder name is retained for backward-compatible references; use this pointer for the current 기준일."
}
$pointer | ConvertTo-Json | Set-Content (Join-Path $Repo "docs\data\analysis\snapshot_all_latest.json") -Encoding UTF8

$readme = @(
    "# 시간대별 충전 가용률 — $stamp 갱신",
    "",
    "AWS Lightsail loop1 기준 최신 팀 공유 자료입니다.",
    "",
    "| 항목 | 값 |",
    "|---|---:|",
    "| 상태 스냅샷 | $($summary.unique_snapshots)개 |",
    "| 관측 기간 | $($summary.first_ts) ~ $($summary.last_ts) |",
    "| 관측 행 | $($summary.event_rows.ToString('N0'))건 |",
    "| 고유 충전소 | $($summary.unique_stations)개 |",
    "| 고유 충전기 | $($summary.unique_chargers)개 |",
    "| 패널 기준 평균 가용률 | $([math]::Round($summary.panel_avail_mean * 100, 1))% |",
    "",
    "그림은 figures/, 원자료는 data/를 참고하세요.",
    "",
    "DA➀ | hourly availability team share | $stamp"
) -join [Environment]::NewLine
$readme | Set-Content (Join-Path $share "README.md") -Encoding UTF8
Write-Host "==> team share: $share"

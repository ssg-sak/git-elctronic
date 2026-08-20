$ErrorActionPreference = "Continue"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$logDir = Join-Path $repo "docs\data\ops_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "team5_parking_daily_$stamp.log"
$python = (Get-Command python -ErrorAction Stop).Source
$env:TEAM5_EXPORT_SCHEDULE = "Windows Task Scheduler: daily 03:20 KST"

Push-Location $repo
try {
    & $python "apps\data-pipeline\processing\db\export_team5_parking_incremental.py" *>&1 |
        Tee-Object -FilePath $log -Append
    $parkingExit = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $parkingExit

# Pull Lightsail loop1 (status) + loop3 (traffic) → archive + merge into live.
# Does NOT start local loops. Records meta for DA① handoff.
#
# Usage (repo root, PowerShell):
#   pwsh -File scripts/pull_lightsail_loops.ps1
#   pwsh -File scripts/pull_lightsail_loops.ps1 -SkipMerge   # archive only

param(
    [string]$AwsHost = "3.36.50.99",
    [string]$AwsUser = "ubuntu",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\LightsailDefaultKey-ap-northeast-2.pem",
    [switch]$SkipMerge
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo

if (-not (Test-Path $KeyPath)) {
    throw "SSH key not found: $KeyPath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archRoot = Join-Path $Repo "docs\data\loops\_archive"
$dest = Join-Path $archRoot "from_lightsail_$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "==> scp loop1 + loop3 from ${AwsUser}@${AwsHost}"
$scpArgs = @("-i", $KeyPath, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20")
& scp @scpArgs -r "${AwsUser}@${AwsHost}:/opt/ev-safecharge/docs/data/loops/loop1" (Join-Path $dest "loop1")
& scp @scpArgs -r "${AwsUser}@${AwsHost}:/opt/ev-safecharge/docs/data/loops/loop3" (Join-Path $dest "loop3")

$live1 = Join-Path $Repo "docs\data\loops\loop1"
$live3 = Join-Path $Repo "docs\data\loops\loop3"
$added1 = 0
$added3 = 0

function Get-YmdFromName([string]$Name) {
    if ($Name -match '_(\d{8})_') { return $Matches[1] }
    return $null
}

function Copy-NewFilesByDate([string]$SrcDir, [string]$DstRoot, [string]$Filter, [switch]$FlatLatest) {
    # Dated CSVs -> DstRoot/YYYYMMDD/; *latest* / meta stay at DstRoot root when FlatLatest
    $n = 0
    if (-not (Test-Path $SrcDir)) { return 0 }
    New-Item -ItemType Directory -Force -Path $DstRoot | Out-Null
    # also search one level of day folders (if server already nested)
    $files = @()
    $files += Get-ChildItem $SrcDir -Filter $Filter -File -ErrorAction SilentlyContinue
    Get-ChildItem $SrcDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $files += Get-ChildItem $_.FullName -Filter $Filter -File -ErrorAction SilentlyContinue
    }
    foreach ($f in $files) {
        $isLatestOrMeta = $f.Name -match "latest|meta|index|quota|call_log|validation"
        if ($FlatLatest -and $isLatestOrMeta) {
            $target = Join-Path $DstRoot $f.Name
            Copy-Item $f.FullName $target -Force
            continue
        }
        if ($isLatestOrMeta -and -not $FlatLatest) {
            $target = Join-Path $DstRoot $f.Name
            if (-not (Test-Path $target)) {
                Copy-Item $f.FullName $target -Force
                $n++
            } else {
                Copy-Item $f.FullName $target -Force
            }
            continue
        }
        $ymd = Get-YmdFromName $f.Name
        if (-not $ymd) {
            $targetDir = $DstRoot
        } else {
            $targetDir = Join-Path $DstRoot $ymd
        }
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        $target = Join-Path $targetDir $f.Name
        if (-not (Test-Path $target)) {
            Copy-Item $f.FullName $target -Force
            $n++
        }
    }
    return $n
}

if (-not $SkipMerge) {
    Write-Host "==> merge new files into live loop1/loop3 (by date)"
    $snapSrc = Join-Path $dest "loop1\snapshots"
    $snapDst = Join-Path $live1 "snapshots"
    $added1 = Copy-NewFilesByDate $snapSrc $snapDst "*.csv"
    # loop1 root helpers
    foreach ($name in @("index.csv", "logs")) {
        $s = Join-Path $dest "loop1\$name"
        $d = Join-Path $live1 $name
        if (Test-Path $s) {
            if ((Get-Item $s).PSIsContainer) {
                New-Item -ItemType Directory -Force -Path $d | Out-Null
                Copy-Item (Join-Path $s "*") $d -Force -ErrorAction SilentlyContinue
            } else {
                Copy-Item $s $d -Force
            }
        }
    }
    $added3 = Copy-NewFilesByDate (Join-Path $dest "loop3") $live3 "*.csv" -FlatLatest
    Copy-NewFilesByDate (Join-Path $dest "loop3") $live3 "*.json" -FlatLatest | Out-Null
}

$snapServer = @(Get-ChildItem (Join-Path $dest "loop1\snapshots") -Filter "*.csv" -ErrorAction SilentlyContinue).Count
$lsServer = @(Get-ChildItem (Join-Path $dest "loop3") -Filter "daegu_traffic_linkspeed_*.csv" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch "latest" }).Count
$incServer = @(Get-ChildItem (Join-Path $dest "loop3") -Filter "daegu_traffic_incident_*.csv" -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch "latest" }).Count

# incident row peek (header-only => 0)
$incLatest = Join-Path $dest "loop3\daegu_traffic_incident_latest.csv"
$incRows = $null
if (Test-Path $incLatest) {
    $lines = Get-Content $incLatest -Encoding UTF8
    $incRows = [Math]::Max(0, $lines.Count - 1)
}

$meta = [ordered]@{
    source               = "Lightsail $AwsHost"
    note                 = "DA① pull — archive + merge live (PC loops stay OFF)"
    as_of_kst            = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    archive              = "docs/data/loops/_archive/from_lightsail_$stamp"
    services             = @("ev-status-loop", "ev-traffic-loop")
    loop1_snaps_on_server = $snapServer
    loop1_snaps_added_to_live = $added1
    loop3_linkspeed_ticks_on_server = $lsServer
    loop3_files_added_to_live = $added3
    loop3_incident_dated_files = $incServer
    loop3_incident_latest_rows = $incRows
    utic_loop2_on_server = $false
    utic_note            = "Lightsail has no loop2/UTIC service — UTIC only if PC/other host runs it"
}
$metaPath = Join-Path $dest "PULL_META.json"
($meta | ConvertTo-Json -Depth 5) | Set-Content -Path $metaPath -Encoding UTF8
Copy-Item $metaPath (Join-Path $archRoot "from_lightsail_latest_PULL_META.json") -Force
Set-Content -Path (Join-Path $archRoot "from_lightsail_latest.txt") -Value "from_lightsail_$stamp" -Encoding UTF8

# append pull log
$logPath = Join-Path $archRoot "PULL_LOG.md"
$logLine = "| $stamp | snaps+$added1 (server $snapServer) | traffic+$added3 · incident_rows=$incRows | ``from_lightsail_$stamp`` |"
if (-not (Test-Path $logPath)) {
    @"
# Lightsail pull log (DA①)

PC 루프는 켜지 않는다. 서버만 수집 → 가끔 pull.

| 시각(폴더) | status | 소통/돌발 | archive |
|---|---|---|---|
$logLine
"@ | Set-Content $logPath -Encoding UTF8
} else {
    Add-Content $logPath $logLine -Encoding UTF8
}

Write-Host "==> done"
Write-Host ($meta | ConvertTo-Json -Compress)
Write-Host "archive: $dest"
Write-Host "log: $logPath"

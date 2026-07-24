# Odcloud rerun: traffic control + link hourly stats + vilage weather
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$out = Join-Path $root "docs\data\extracted"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") { $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'") }
}
$dataKey = $envMap["DATA_GO_KR_KEY"]
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$summary = @()

function Invoke-WithRetry { param([scriptblock]$Action, [int]$Retries = 4)
    $last = $null
    for ($i = 1; $i -le $Retries; $i++) { try { return & $Action } catch { $last = $_; Start-Sleep -Seconds (2 * $i) } }
    throw $last.Exception
}
function Write-RowsCsv { param([string]$Path, [object[]]$Rows, [bool]$Append)
    if (-not $Rows -or $Rows.Count -eq 0) { return 0 }
    if ($Append -and (Test-Path $Path)) { $Rows | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1 | Add-Content -Path $Path -Encoding UTF8 }
    else { $Rows | Export-Csv -Path $Path -NoTypeInformation -Encoding UTF8 }
    return $Rows.Count
}
function Flatten-Obj($obj, [string]$prefix = "") {
    $map = [ordered]@{}
    if ($null -eq $obj) { return $map }
    if ($obj -is [string] -or $obj -is [ValueType]) { $map[$(if ($prefix) { $prefix } else { "value" })] = $obj; return $map }
    foreach ($pr in $obj.PSObject.Properties) {
        $name = if ($prefix) { "$prefix.$($pr.Name)" } else { $pr.Name }
        $val = $pr.Value
        if ($null -eq $val) { $map[$name] = $null }
        elseif ($val -is [Array] -or ($val -is [System.Collections.IEnumerable] -and -not ($val -is [string]))) {
            $arr = @($val)
            if ($arr.Count -eq 1 -and $arr[0] -isnot [string] -and $arr[0] -isnot [ValueType]) {
                $nested = Flatten-Obj $arr[0] $name; foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
            } else { $map[$name] = ($arr | ForEach-Object { "$_" }) -join "|" }
        }
        elseif ($val.PSObject -and $val.PSObject.Properties.Count -gt 0 -and -not ($val -is [string]) -and -not ($val -is [ValueType])) {
            $nested = Flatten-Obj $val $name; foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
        } else { $map[$name] = $val }
    }
    return $map
}
function Export-OdcloudDataset {
    param([string]$Label, [string]$DatasetId, [string]$Uddi, [string]$OutName, [int]$PerPage = 1000)
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    $path = Join-Path $out "${OutName}_$ts.csv"
    try {
        $page = 1; $acc = 0; $total = $null
        while ($true) {
            $url = "https://api.odcloud.kr/api/$DatasetId/v1/uddi:$Uddi"
            $r = Invoke-WithRetry { Invoke-RestMethod -Uri $url -Body @{ serviceKey = $dataKey; page = "$page"; perPage = "$PerPage"; returnType = "JSON" } -TimeoutSec 180 }
            if (-not $total) { if ($r.totalCount) { $total = [int]$r.totalCount } elseif ($r.matchCount) { $total = [int]$r.matchCount } }
            $items = @($r.data); if ($items.Count -eq 0) { break }
            $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $rows = @($items | ForEach-Object { $flat = Flatten-Obj $_; $o = [ordered]@{ fetchedAt = $fa; source = "odcloud"; datasetId = $DatasetId }; foreach ($k in $flat.Keys) { $o[$k] = $flat[$k] }; [PSCustomObject]$o })
            $acc += Write-RowsCsv -Path $path -Rows $rows -Append ($acc -gt 0)
            Write-Host "  page $page : $($items.Count) (acc $acc/$(if ($total) { $total } else { '?' }))"
            if ($total -and $acc -ge $total) { break }
            if ($items.Count -lt $PerPage) { break }
            $page++; if ($page -gt 500) { break }
            Start-Sleep -Milliseconds 200
        }
        if ($acc -eq 0) { throw "empty" }
        $summary += [PSCustomObject]@{ Name = $OutName; Status = "OK"; Detail = "$acc rows" }
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
        $summary += [PSCustomObject]@{ Name = $OutName; Status = "FAIL"; Detail = $_.Exception.Message }
    }
}

Write-Host "=== odcloud rerun ($ts) ===" -ForegroundColor Yellow

Write-Host "`n=== Weather vilage fcst ===" -ForegroundColor Cyan
try {
    $now = (Get-Date).AddHours(-1)
    $hours = @(2, 5, 8, 11, 14, 17, 20, 23)
    $h = [int]$now.ToString("HH")
    $btHour = ($hours | Where-Object { $_ -le $h } | Select-Object -Last 1)
    if ($null -eq $btHour) { $btHour = 23; $now = $now.AddDays(-1) }
    $r = Invoke-WithRetry { Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst" -Body @{ serviceKey = $dataKey; pageNo = "1"; numOfRows = "1000"; dataType = "JSON"; base_date = $now.ToString("yyyyMMdd"); base_time = ("{0:D2}00" -f $btHour); nx = "89"; ny = "90" } -TimeoutSec 90 }
    if ($r.response.header.resultCode -ne "00") { throw $r.response.header.resultMsg }
    $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @(@($r.response.body.items.item) | ForEach-Object { [PSCustomObject]@{ baseDate = $_.baseDate; baseTime = $_.baseTime; fcstDate = $_.fcstDate; fcstTime = $_.fcstTime; category = $_.category; fcstValue = $_.fcstValue; nx = $_.nx; ny = $_.ny; fetchedAt = $fa } })
    Write-RowsCsv -Path (Join-Path $out "daegu_weather_vilage_fcst_$ts.csv") -Rows $rows -Append $false | Out-Null
    $summary += [PSCustomObject]@{ Name = "weather_vilage"; Status = "OK"; Detail = "$($rows.Count) rows" }
} catch { $summary += [PSCustomObject]@{ Name = "weather_vilage"; Status = "FAIL"; Detail = $_.Exception.Message } }

Export-OdcloudDataset -Label "Traffic control" -DatasetId "15117319" -Uddi "1d18ec96-0eb4-4fa7-a9c6-c67100a5b7f0" -OutName "daegu_traffic_control"
Export-OdcloudDataset -Label "Link hourly stats" -DatasetId "15117329" -Uddi "9efa7615-4b08-45dd-b695-89265f4c4586" -OutName "daegu_traffic_link_hourly_stats" -PerPage 5000

Write-Host "`n========== RERUN SUMMARY ==========" -ForegroundColor Yellow
$summary | Format-Table -AutoSize
Get-ChildItem $out -Filter "*$ts*" | Format-Table Name, Length, LastWriteTime -AutoSize

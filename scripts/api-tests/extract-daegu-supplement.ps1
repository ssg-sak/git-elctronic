# Supplement: walk parks fix, vilage weather, parking, odcloud traffic file APIs
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$out = Join-Path $root "docs\data\extracted"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
        $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}

$dataKey = $envMap["DATA_GO_KR_KEY"]
$prkKey = $envMap["DAEGU_PARKING_KEY"]
$prkRtKey = $envMap["DAEGU_PARKING_RT_KEY"]
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$x = 128.6014
$y = 35.8714
$summary = @()

function Add-Result([string]$Name, [string]$Status, [string]$Detail = "") {
    $script:summary += [PSCustomObject]@{ Name = $Name; Status = $Status; Detail = $Detail }
}

function Invoke-WithRetry {
    param([scriptblock]$Action, [int]$Retries = 4)
    $last = $null
    for ($i = 1; $i -le $Retries; $i++) {
        try { return & $Action }
        catch {
            $last = $_
            Start-Sleep -Seconds (2 * $i)
        }
    }
    throw $last.Exception
}

function Write-RowsCsv {
    param([string]$Path, [object[]]$Rows, [bool]$Append)
    if (-not $Rows -or $Rows.Count -eq 0) { return 0 }
    if ($Append -and (Test-Path $Path)) {
        $Rows | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1 | Add-Content -Path $Path -Encoding UTF8
    } else {
        $Rows | Export-Csv -Path $Path -NoTypeInformation -Encoding UTF8
    }
    return $Rows.Count
}

function Flatten-Obj($obj, [string]$prefix = "") {
    $map = [ordered]@{}
    if ($null -eq $obj) { return $map }
    if ($obj -is [string] -or $obj -is [ValueType]) {
        $map[$(if ($prefix) { $prefix } else { "value" })] = $obj
        return $map
    }
    foreach ($pr in $obj.PSObject.Properties) {
        $name = if ($prefix) { "$prefix.$($pr.Name)" } else { $pr.Name }
        $val = $pr.Value
        if ($null -eq $val) { $map[$name] = $null }
        elseif ($val -is [Array] -or ($val -is [System.Collections.IEnumerable] -and -not ($val -is [string]))) {
            $arr = @($val)
            if ($arr.Count -eq 1 -and $arr[0] -isnot [string] -and $arr[0] -isnot [ValueType]) {
                $nested = Flatten-Obj $arr[0] $name
                foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
            } else {
                $map[$name] = ($arr | ForEach-Object { "$_" }) -join "|"
            }
        }
        elseif ($val.PSObject -and $val.PSObject.Properties.Count -gt 0 -and -not ($val -is [string]) -and -not ($val -is [ValueType])) {
            $nested = Flatten-Obj $val $name
            foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
        } else {
            $map[$name] = $val
        }
    }
    return $map
}

function Export-OdcloudDataset {
    param(
        [string]$Label,
        [string]$DatasetId,
        [string]$Uddi,
        [string]$OutName,
        [int]$PerPage = 1000
    )
    Write-Host "`n=== $Label (odcloud $DatasetId) ===" -ForegroundColor Cyan
    $path = Join-Path $out "${OutName}_$ts.csv"
    try {
        $page = 1
        $acc = 0
        $total = $null
        while ($true) {
            $url = "https://api.odcloud.kr/api/$DatasetId/v1/uddi:$Uddi"
            $r = Invoke-WithRetry {
                Invoke-RestMethod -Uri $url -Body @{
                    serviceKey = $dataKey
                    page         = "$page"
                    perPage      = "$PerPage"
                    returnType   = "JSON"
                } -TimeoutSec 120
            }
            if (-not $total) {
                if ($r.totalCount) { $total = [int]$r.totalCount }
                elseif ($r.matchCount) { $total = [int]$r.matchCount }
            }
            $items = @($r.data)
            if ($items.Count -eq 0) { break }
            $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $rows = @($items | ForEach-Object {
                    $flat = Flatten-Obj $_
                    $o = [ordered]@{ fetchedAt = $fa; source = "odcloud"; datasetId = $DatasetId }
                    foreach ($k in $flat.Keys) { $o[$k] = $flat[$k] }
                    [PSCustomObject]$o
                })
            $acc += Write-RowsCsv -Path $path -Rows $rows -Append ($acc -gt 0)
            Write-Host "  page $page : $($items.Count) (acc $acc/$(if ($total) { $total } else { '?' }))"
            if ($total -and $acc -ge $total) { break }
            if ($items.Count -lt $PerPage) { break }
            $page++
            if ($page -gt 500) { break }
            Start-Sleep -Milliseconds 300
        }
        if ($acc -eq 0) { throw "empty dataset (fileData OpenAPI not approved?)" }
        Add-Result $OutName "OK" "$acc rows"
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
        Add-Result $OutName "FAIL" $_.Exception.Message
    }
}

Write-Host "=== extract-daegu-supplement ($ts) ===" -ForegroundColor Yellow

# 1) Walk parks (fixed parser: body.items.item)
Write-Host "`n=== Walk parks (fixed) ===" -ForegroundColor Cyan
try {
    $all = New-Object System.Collections.Generic.List[object]
    $page = 1
    $total = $null
    while ($true) {
        $q = "serviceKey=$([uri]::EscapeDataString($dataKey))&pageNo=$page&numOfRows=100&type=json&lat=$y&lot=$x&radius=10"
        $r = Invoke-WithRetry {
            Invoke-RestMethod -Uri ("https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?" + $q) -TimeoutSec 60
        }
        if ($r.header.resultCode -ne "00") { throw "code=$($r.header.resultCode)" }
        if (-not $total -and $r.body.totalCount) { $total = [int]$r.body.totalCount }
        $items = @()
        if ($r.body.items -and $r.body.items.item) { $items = @($r.body.items.item) }
        if ($items.Count -eq 0) { break }
        foreach ($it in $items) { [void]$all.Add($it) }
        Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if ($total) { $total } else { '?' })"
        if ($total -and $all.Count -ge $total) { break }
        if ($items.Count -lt 100) { break }
        $page++
    }
    $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @($all | ForEach-Object {
            [PSCustomObject]@{
                fetchedAt = $fa; id = $_.id; mngNo = $_.mngNo; parkNm = $_.parkNm
                parkType = $_.parkType; roadNmAddr = $_.roadNmAddr; lotNoAddr = $_.lotNoAddr
                lat = $_.lat; lot = $_.lot; mngInstNm = $_.mngInstNm; mngInstTel = $_.mngInstTel
                dongNm = $_.dongNm; sggNm = $_.sggNm
            }
        })
    $p = Join-Path $out "daegu_walk_parks_$ts.csv"
    Write-RowsCsv -Path $p -Rows $rows -Append $false | Out-Null
    Add-Result "walk_parks" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "walk_parks" "FAIL" $_.Exception.Message
}

# 2) Weather vilage fcst
Write-Host "`n=== Weather vilage fcst ===" -ForegroundColor Cyan
try {
    $now = (Get-Date).AddHours(-1)
    $hours = @(2, 5, 8, 11, 14, 17, 20, 23)
    $h = [int]$now.ToString("HH")
    $btHour = ($hours | Where-Object { $_ -le $h } | Select-Object -Last 1)
    if ($null -eq $btHour) { $btHour = 23; $now = $now.AddDays(-1) }
    $bd = $now.ToString("yyyyMMdd")
    $bt = "{0:D2}00" -f $btHour
    $r = Invoke-WithRetry {
        Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst" `
            -Body @{
                serviceKey = $dataKey; pageNo = "1"; numOfRows = "1000"; dataType = "JSON"
                base_date = $bd; base_time = $bt; nx = "89"; ny = "90"
            } -TimeoutSec 90
    }
    if ($r.response.header.resultCode -ne "00") { throw $r.response.header.resultMsg }
    $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @(@($r.response.body.items.item) | ForEach-Object {
            [PSCustomObject]@{
                baseDate = $_.baseDate; baseTime = $_.baseTime
                fcstDate = $_.fcstDate; fcstTime = $_.fcstTime
                category = $_.category; fcstValue = $_.fcstValue
                nx = $_.nx; ny = $_.ny; fetchedAt = $fa
            }
        })
    $p = Join-Path $out "daegu_weather_vilage_fcst_$ts.csv"
    Write-RowsCsv -Path $p -Rows $rows -Append $false | Out-Null
    Add-Result "weather_vilage" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "weather_vilage" "FAIL" $_.Exception.Message
}

# 3) Parking (pis.daegu) — skip if mock key
function Export-ParkingApi {
    param([string]$Label, [string]$Url, [string]$Key, [string]$OutName)
    Write-Host "`n=== $Label ===" -ForegroundColor Cyan
    if (-not $Key -or $Key -match "MOCK") {
        Add-Result $OutName "SKIP" "mock/empty key in .env"
        Write-Host "  SKIP mock key" -ForegroundColor DarkYellow
        return
    }
    $path = Join-Path $out "${OutName}_$ts.csv"
    try {
        $page = 1
        $acc = 0
        while ($true) {
            $r = Invoke-WithRetry {
                Invoke-RestMethod -Uri "$Url?numOfRows=100&pageNo=$page" `
                    -Headers @{ Authentication = $Key; accept = "application/json;charset=UTF-8" } `
                    -TimeoutSec 90
            }
            $items = @()
            if ($r.items) { $items = @($r.items) }
            elseif ($r.body.items) { $items = @($r.body.items) }
            elseif ($r.data) { $items = @($r.data) }
            if ($items.Count -eq 0) { break }
            $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $rows = @($items | ForEach-Object {
                    $flat = Flatten-Obj $_
                    $o = [ordered]@{ fetchedAt = $fa; isMock = "false"; source = "daegu_pis" }
                    foreach ($k in $flat.Keys) { $o[$k] = $flat[$k] }
                    [PSCustomObject]$o
                })
            $acc += Write-RowsCsv -Path $path -Rows $rows -Append ($acc -gt 0)
            Write-Host "  page $page : $($items.Count) (acc $acc)"
            if ($items.Count -lt 100) { break }
            $page++
            if ($page -gt 50) { break }
        }
        if ($acc -eq 0) { throw "no rows" }
        Add-Result $OutName "OK" "$acc rows"
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
        Add-Result $OutName "FAIL" $_.Exception.Message
    }
}

Export-ParkingApi -Label "Parking info (prkInfo)" `
    -Url "https://pis.daegu.go.kr/api/serviceApply/prkInfo" `
    -Key $prkKey -OutName "daegu_parking_info"
Export-ParkingApi -Label "Parking realtime (rltmPrkInfo)" `
    -Url "https://pis.daegu.go.kr/api/serviceApply/rltmPrkInfo" `
    -Key $prkRtKey -OutName "daegu_parking_realtime"

# 4) Odcloud fileData APIs (need fileData OpenAPI approval on portal)
Export-OdcloudDataset -Label "Traffic incident stats" -DatasetId "15117328" `
    -Uddi "5d72aa50-1a58-488e-bdf6-a6f73befe6a1" -OutName "daegu_traffic_incident_stats"
Export-OdcloudDataset -Label "Traffic control" -DatasetId "15117319" `
    -Uddi "1d18ec96-0eb4-4fa7-a9c6-c67100a5b7f0" -OutName "daegu_traffic_control"
Export-OdcloudDataset -Label "Link hourly stats" -DatasetId "15117329" `
    -Uddi "9efa7615-4b08-45dd-b695-89265f4c4586" -OutName "daegu_traffic_link_hourly_stats" -PerPage 5000

Write-Host "`n========== SUPPLEMENT SUMMARY ==========" -ForegroundColor Yellow
$summary | Format-Table -AutoSize
Get-ChildItem $out -Filter "*$ts*" | Format-Table Name, Length, LastWriteTime -AutoSize

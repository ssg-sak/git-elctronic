# EV SafeCharge - Daegu data extraction (complete download priority)
# - Appends each page to CSV immediately (502-safe)
# - Never overwrites existing files; uses new timestamp folder/files
# - Continues remaining APIs even if one fails

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$outputDir = Join-Path $root "docs\data\extracted"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
        $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$dataKey  = $envMap["DATA_GO_KR_KEY"]
$tmapKey  = $envMap["TMAP_APP_KEY"]
$kakaoKey = $envMap["KAKAO_REST_KEY"]
if (-not $dataKey) { Write-Host "DATA_GO_KR_KEY missing" -ForegroundColor Red; exit 1 }

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$daeguX = 128.6014
$daeguY = 35.8714
$pageSize = 999
$summary = @()

function Add-Result([string]$Name, [string]$Status, [string]$Detail = "") {
    $script:summary += [PSCustomObject]@{ Name = $Name; Status = $Status; Detail = $Detail }
}

function Get-XmlText($node) {
    if ($null -eq $node) { return $null }
    if ($node -is [string]) { return $node }
    if ($null -ne $node.'#text') { return [string]$node.'#text' }
    $s = [string]$node
    if ($s -and $s -notmatch "^System\.") { return $s }
    return $null
}

function Get-TotalCountFromXml([xml]$doc) {
    $t = Get-XmlText $doc.response.body.totalCount
    if ($t -and $t -match "^\d+$") { return [int]$t }
    $raw = $doc.OuterXml
    if ($raw -match "<totalCount>(\d+)</totalCount>") { return [int]$Matches[1] }
    return $null
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Action,
        [int]$Retries = 6,
        [int]$TimeoutHint = 120
    )
    $last = $null
    for ($i = 1; $i -le $Retries; $i++) {
        try { return & $Action }
        catch {
            $last = $_
            $wait = [Math]::Min(30, 3 * $i)
            Write-Host ("  retry {0}/{1} wait {2}s : {3}" -f $i, $Retries, $wait, $_.Exception.Message) -ForegroundColor DarkYellow
            Start-Sleep -Seconds $wait
        }
    }
    throw $last.Exception
}

function Write-RowsCsv {
    param([string]$Path, [object[]]$Rows, [bool]$Append)
    if (-not $Rows -or $Rows.Count -eq 0) { return }
    if ($Append -and (Test-Path $Path)) {
        $Rows | ConvertTo-Csv -NoTypeInformation | Select-Object -Skip 1 | Add-Content -Path $Path -Encoding UTF8
    } else {
        $Rows | Export-Csv -Path $Path -NoTypeInformation -Encoding UTF8
    }
}

function Invoke-JsonUtf8 {
    param([string]$Uri, [int]$TimeoutSec = 60)
    # Invoke-RestMethod on Windows can mojibake UTF-8 JSON; decode bytes explicitly.
    $resp = Invoke-WebRequest -Uri $Uri -TimeoutSec $TimeoutSec -UseBasicParsing
    $bytes = if ($resp.RawContentStream) {
        $ms = New-Object System.IO.MemoryStream
        $resp.RawContentStream.Position = 0
        $resp.RawContentStream.CopyTo($ms)
        $ms.ToArray()
    } else {
        [System.Text.Encoding]::GetEncoding(28591).GetBytes($resp.Content)
    }
    $jsonText = [System.Text.Encoding]::UTF8.GetString($bytes)
    return $jsonText | ConvertFrom-Json
}

function Convert-XmlItems {
    param($Items)
    $list = @($Items)
    if ($list.Count -eq 0) { return @() }
    $skip = @(
        "OuterXml","InnerXml","InnerText","Name","LocalName","NamespaceURI","Prefix",
        "NodeType","ParentNode","OwnerDocument","IsEmpty","Attributes","HasAttributes",
        "HasChildNodes","ChildNodes","FirstChild","LastChild","NextSibling","PreviousSibling",
        "Value","BaseURI","SchemaInfo","#text"
    )
    $props = $list[0] | Get-Member -MemberType Property |
        Where-Object { $skip -notcontains $_.Name } |
        Select-Object -ExpandProperty Name
    $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    return @(
        $list | ForEach-Object {
            $o = [ordered]@{ fetchedAt = $fetchedAt }
            foreach ($p in $props) { $o[$p] = (Get-XmlText $_.$p) }
            [PSCustomObject]$o
        }
    )
}

function Convert-ObjItems {
    param($Items)
    $list = @($Items)
    if ($list.Count -eq 0) { return @() }
    $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    return @(
        $list | ForEach-Object {
            $o = [ordered]@{ fetchedAt = $fetchedAt }
            foreach ($pr in $_.PSObject.Properties) {
                if ($pr.Name -ne "fetchedAt") { $o[$pr.Name] = $pr.Value }
            }
            [PSCustomObject]$o
        }
    )
}

# ===================== 1) Charger Info (all pages) =====================
Write-Host "`n=== 1. Charger Info Daegu zcode=27 (full) ===" -ForegroundColor Cyan
$infoPath = Join-Path $outputDir "daegu_charger_info_$timestamp.csv"
try {
    $page = 1
    $total = $null
    $acc = 0
    while ($true) {
        $r = Invoke-WithRetry -Action {
            $params = @{ serviceKey = $dataKey; numOfRows = "$pageSize"; pageNo = "$page"; zcode = "27" }
            [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo" -Body $params -TimeoutSec 150)
        }
        $code = Get-XmlText $r.response.header.resultCode
        if ($code -ne "00") { throw "resultCode=$code $(Get-XmlText $r.response.header.resultMsg)" }

        $items = @($r.response.body.items.item)
        if ($items.Count -eq 0) { break }

        if (-not $total) { $total = Get-TotalCountFromXml $r }

        $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $rows = @(
            $items | ForEach-Object {
                [PSCustomObject]@{
                    statId = (Get-XmlText $_.statId); statNm = (Get-XmlText $_.statNm); addr = (Get-XmlText $_.addr)
                    lat = (Get-XmlText $_.lat); lng = (Get-XmlText $_.lng)
                    chgerId = (Get-XmlText $_.chgerId); chgerType = (Get-XmlText $_.chgerType)
                    output = (Get-XmlText $_.output); useTime = (Get-XmlText $_.useTime); busiNm = (Get-XmlText $_.busiNm)
                    parkingFree = (Get-XmlText $_.parkingFree); limitYn = (Get-XmlText $_.limitYn); delYn = (Get-XmlText $_.delYn)
                    fetchedAt = $fetchedAt
                }
            }
        )
        Write-RowsCsv -Path $infoPath -Rows $rows -Append ($acc -gt 0)
        $acc += $rows.Count
        $shown = if ($total) { "$total" } else { "?" }
        Write-Host "  page $page : $($rows.Count) saved (acc $acc/$shown) -> $infoPath"

        if ($total -and $acc -ge $total) { break }
        if ($items.Count -lt $pageSize) { break }
        $page++
        if ($page -gt 60) { Write-Host "  page cap 60 reached" -ForegroundColor Yellow; break }
        Start-Sleep -Milliseconds 600
    }
    Add-Result "charger_info" "OK" "$acc rows"
} catch {
    Write-Host "  FAIL (partial kept if any): $($_.Exception.Message)" -ForegroundColor Red
    $partial = if (Test-Path $infoPath) { (Import-Csv $infoPath).Count } else { 0 }
    Add-Result "charger_info" $(if ($partial -gt 0) { "PARTIAL" } else { "FAIL" }) "$partial rows; $($_.Exception.Message)"
}

# ===================== 2) Charger Status (full for period, new file) =====================
Write-Host "`n=== 2. Charger Status Daegu (new file; old CSV untouched) ===" -ForegroundColor Cyan
$statusPath = Join-Path $outputDir "daegu_charger_status_$timestamp.csv"
try {
    $page = 1
    $total = $null
    $acc = 0
    while ($true) {
        $r = Invoke-WithRetry -Action {
            $params = @{ serviceKey = $dataKey; numOfRows = "$pageSize"; pageNo = "$page"; zcode = "27"; period = "10" }
            [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus" -Body $params -TimeoutSec 150)
        }
        $code = Get-XmlText $r.response.header.resultCode
        if ($code -ne "00") { throw "resultCode=$code" }

        $items = @($r.response.body.items.item)
        if ($items.Count -eq 0) { break }
        if (-not $total) { $total = Get-TotalCountFromXml $r }

        $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $rows = @(
            $items | ForEach-Object {
                [PSCustomObject]@{
                    statId = (Get-XmlText $_.statId); statNm = (Get-XmlText $_.statNm)
                    chgerId = (Get-XmlText $_.chgerId); stat = (Get-XmlText $_.stat)
                    statUpdDt = (Get-XmlText $_.statUpdDt); fetchedAt = $fetchedAt
                }
            }
        )
        Write-RowsCsv -Path $statusPath -Rows $rows -Append ($acc -gt 0)
        $acc += $rows.Count
        $shown = if ($total) { "$total" } else { "?" }
        Write-Host "  page $page : $($rows.Count) saved (acc $acc/$shown)"

        if ($total -and $acc -ge $total) { break }
        if ($items.Count -lt $pageSize) { break }
        $page++
        if ($page -gt 30) { break }
        Start-Sleep -Milliseconds 600
    }
    Add-Result "charger_status" "OK" "$acc rows (old file kept)"
} catch {
    Write-Host "  FAIL (partial kept): $($_.Exception.Message)" -ForegroundColor Red
    $partial = if (Test-Path $statusPath) { (Import-Csv $statusPath).Count } else { 0 }
    Add-Result "charger_status" $(if ($partial -gt 0) { "PARTIAL" } else { "FAIL" }) "$partial rows"
}

# ===================== 3) Weather ncst =====================
Write-Host "`n=== 3. Weather UltraSrtNcst ===" -ForegroundColor Cyan
try {
    $base = (Get-Date).AddMinutes(-50)
    $baseDate = $base.ToString("yyyyMMdd"); $baseTime = $base.ToString("HH") + "00"
    $r = Invoke-WithRetry -Action {
        $params = @{
            serviceKey = $dataKey; pageNo = "1"; numOfRows = "20"; dataType = "JSON"
            base_date = $baseDate; base_time = $baseTime; nx = "89"; ny = "90"
        }
        Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst" -Body $params -TimeoutSec 60
    }
    if ($r.response.header.resultCode -ne "00") { throw "resultCode=$($r.response.header.resultCode)" }
    $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @(
        @($r.response.body.items.item) | ForEach-Object {
            [PSCustomObject]@{
                baseDate = $_.baseDate; baseTime = $_.baseTime; category = $_.category
                obsrValue = $_.obsrValue; nx = $_.nx; ny = $_.ny; fetchedAt = $fetchedAt
            }
        }
    )
    $path = Join-Path $outputDir "daegu_weather_ultra_ncst_$timestamp.csv"
    Write-RowsCsv -Path $path -Rows $rows -Append $false
    Write-Host "  SAVED $($rows.Count) -> $path" -ForegroundColor Green
    Add-Result "weather_ncst" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "weather_ncst" "FAIL" $_.Exception.Message
}

# ===================== 4) Weather fcst =====================
Write-Host "`n=== 4. Weather UltraSrtFcst ===" -ForegroundColor Cyan
try {
    $base = (Get-Date).AddMinutes(-50)
    $baseDate = $base.ToString("yyyyMMdd"); $baseTime = $base.ToString("HH") + "00"
    $r = Invoke-WithRetry -Action {
        $params = @{
            serviceKey = $dataKey; pageNo = "1"; numOfRows = "100"; dataType = "JSON"
            base_date = $baseDate; base_time = $baseTime; nx = "89"; ny = "90"
        }
        Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst" -Body $params -TimeoutSec 60
    }
    if ($r.response.header.resultCode -ne "00") { throw "resultCode=$($r.response.header.resultCode)" }
    $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @(
        @($r.response.body.items.item) | ForEach-Object {
            [PSCustomObject]@{
                baseDate = $_.baseDate; baseTime = $_.baseTime
                fcstDate = $_.fcstDate; fcstTime = $_.fcstTime
                category = $_.category; fcstValue = $_.fcstValue
                nx = $_.nx; ny = $_.ny; fetchedAt = $fetchedAt
            }
        }
    )
    $path = Join-Path $outputDir "daegu_weather_ultra_fcst_$timestamp.csv"
    Write-RowsCsv -Path $path -Rows $rows -Append $false
    Write-Host "  SAVED $($rows.Count) -> $path" -ForegroundColor Green
    Add-Result "weather_fcst" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "weather_fcst" "FAIL" $_.Exception.Message
}

# ===================== 5) TourAPI =====================
Write-Host "`n=== 5. TourAPI attractions ===" -ForegroundColor Cyan
$tourPath = Join-Path $outputDir "daegu_tour_attractions_$timestamp.csv"
try {
    $page = 1; $acc = 0; $total = $null
    while ($true) {
        $r = Invoke-WithRetry -Action {
            $q = "serviceKey=$([uri]::EscapeDataString($dataKey))" +
                "&MobileOS=ETC&MobileApp=EVSafeCharge&_type=json" +
                "&mapX=$daeguX&mapY=$daeguY&radius=5000&numOfRows=100&pageNo=$page&contentTypeId=12"
            Invoke-JsonUtf8 -Uri ("https://apis.data.go.kr/B551011/KorService2/locationBasedList2?" + $q) -TimeoutSec 60
        }
        if ($r.response.header.resultCode -ne "0000") { throw "resultCode=$($r.response.header.resultCode)" }
        $items = @($r.response.body.items.item)
        if ($items.Count -eq 0) { break }
        if (-not $total) { $total = [int]$r.response.body.totalCount }
        $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $rows = @(
            $items | ForEach-Object {
                [PSCustomObject]@{
                    contentid = $_.contentid; title = $_.title; addr1 = $_.addr1; addr2 = $_.addr2
                    mapx = $_.mapx; mapy = $_.mapy; dist = $_.dist
                    cat1 = $_.cat1; cat2 = $_.cat2; cat3 = $_.cat3
                    tel = $_.tel; firstimage = $_.firstimage; fetchedAt = $fetchedAt
                }
            }
        )
        Write-RowsCsv -Path $tourPath -Rows $rows -Append ($acc -gt 0)
        $acc += $rows.Count
        Write-Host "  page $page : $($rows.Count) (acc $acc/$total)"
        if ($total -and $acc -ge $total) { break }
        if ($items.Count -lt 100) { break }
        $page++; if ($page -gt 30) { break }
    }
    Add-Result "tour_attractions" "OK" "$acc rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    $partial = if (Test-Path $tourPath) { (Import-Csv $tourPath).Count } else { 0 }
    Add-Result "tour_attractions" $(if ($partial -gt 0) { "PARTIAL" } else { "FAIL" }) "$partial rows"
}

# ===================== 6) City tourism =====================
Write-Host "`n=== 6. Daegu city tourism ===" -ForegroundColor Cyan
$cityPath = Join-Path $outputDir "daegu_city_tour_$timestamp.csv"
try {
    $page = 1; $acc = 0; $total = $null
    while ($true) {
        $r = Invoke-WithRetry -Action {
            $params = @{ serviceKey = $dataKey; pageNo = "$page"; numOfRows = "100" }
            [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList" -Body $params -TimeoutSec 90)
        }
        $code = Get-XmlText $r.response.header.resultCode
        if ($code -ne "00") { throw "resultCode=$code" }
        $items = @($r.response.body.items.item)
        if ($items.Count -eq 0) { break }
        if (-not $total) { $total = Get-TotalCountFromXml $r }
        $rows = Convert-XmlItems $items
        Write-RowsCsv -Path $cityPath -Rows $rows -Append ($acc -gt 0)
        $acc += $rows.Count
        $shown = if ($total) { "$total" } else { "?" }
        Write-Host "  page $page : $($rows.Count) (acc $acc/$shown)"
        if ($total -and $acc -ge $total) { break }
        if ($items.Count -lt 100) { break }
        $page++; if ($page -gt 50) { break }
    }
    Add-Result "city_tour" "OK" "$acc rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    $partial = if (Test-Path $cityPath) { (Import-Csv $cityPath).Count } else { 0 }
    Add-Result "city_tour" $(if ($partial -gt 0) { "PARTIAL" } else { "FAIL" }) "$partial rows"
}

# ===================== 7) Walk parks =====================
Write-Host "`n=== 7. Walk parks ===" -ForegroundColor Cyan
$walkPath = Join-Path $outputDir "daegu_walk_parks_$timestamp.csv"
try {
    $page = 1; $acc = 0; $total = $null
    while ($true) {
        $r = Invoke-WithRetry -Action {
            $q = "serviceKey=$([uri]::EscapeDataString($dataKey))" +
                "&pageNo=$page&numOfRows=100&type=json&lat=$daeguY&lot=$daeguX&radius=10"
            Invoke-RestMethod -Uri ("https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?" + $q) -TimeoutSec 60
        }
        if ($r.header.resultCode -ne "00") { throw "resultCode=$($r.header.resultCode)" }
        $items = @()
        if ($r.body.items -and $r.body.items.item) { $items = @($r.body.items.item) }
        elseif ($r.body.items) { $items = @($r.body.items) }
        elseif ($r.body.item) { $items = @($r.body.item) }
        if ($items.Count -eq 0) { break }
        if (-not $total -and $r.body.totalCount) { $total = [int]$r.body.totalCount }
        $rows = Convert-ObjItems $items
        Write-RowsCsv -Path $walkPath -Rows $rows -Append ($acc -gt 0)
        $acc += $rows.Count
        Write-Host "  page $page : $($rows.Count) (acc $acc/$(if($total){$total}else{'?'}))"
        if ($total -and $acc -ge $total) { break }
        if ($items.Count -lt 100) { break }
        $page++; if ($page -gt 30) { break }
    }
    Add-Result "walk_parks" "OK" "$acc rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    $partial = if (Test-Path $walkPath) { (Import-Csv $walkPath).Count } else { 0 }
    Add-Result "walk_parks" $(if ($partial -gt 0) { "PARTIAL" } else { "FAIL" }) "$partial rows"
}

# ===================== 8/9) Traffic (best effort) =====================
Write-Host "`n=== 8. Traffic linkspeed ===" -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest1/linkspeed" -Body @{ serviceKey = $dataKey; pageNo = "1"; numOfRows = "100" } -TimeoutSec 60
    $ok = $false; $rows = @()
    if ($r -is [xml]) {
        $ok = (Get-XmlText $r.response.header.resultCode) -eq "00"
        $rows = Convert-XmlItems @($r.response.body.items.item)
    } else {
        $ok = ("$($r.header.resultCode)$($r.response.header.resultCode)" -match "00")
        $items = @(); if ($r.response.body.items.item) { $items = @($r.response.body.items.item) }
        $rows = Convert-ObjItems $items
    }
    if (-not $ok) { throw "provider outage / bad response" }
    $path = Join-Path $outputDir "daegu_traffic_linkspeed_$timestamp.csv"
    Write-RowsCsv -Path $path -Rows $rows -Append $false
    Write-Host "  SAVED $($rows.Count)" -ForegroundColor Green
    Add-Result "traffic_linkspeed" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "traffic_linkspeed" "FAIL" $_.Exception.Message
}

Write-Host "`n=== 9. Traffic incident ===" -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest/dgincident" -Body @{ serviceKey = $dataKey; pageNo = "1"; numOfRows = "100" } -TimeoutSec 60
    $ok = $false; $rows = @()
    if ($r -is [xml]) {
        $ok = (Get-XmlText $r.response.header.resultCode) -eq "00"
        $rows = Convert-XmlItems @($r.response.body.items.item)
    } else {
        $ok = ("$($r.header.resultCode)$($r.response.header.resultCode)" -match "00")
        $items = @(); if ($r.response.body.items.item) { $items = @($r.response.body.items.item) }
        $rows = Convert-ObjItems $items
    }
    if (-not $ok) { throw "provider outage / bad response" }
    $path = Join-Path $outputDir "daegu_traffic_incident_$timestamp.csv"
    Write-RowsCsv -Path $path -Rows $rows -Append $false
    Write-Host "  SAVED $($rows.Count)" -ForegroundColor Green
    Add-Result "traffic_incident" "OK" "$($rows.Count) rows"
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    Add-Result "traffic_incident" "FAIL" $_.Exception.Message
}

# ===================== 10) Kakao =====================
Write-Host "`n=== 10. Kakao nearby ===" -ForegroundColor Cyan
if (-not $kakaoKey) {
    Add-Result "kakao_nearby" "SKIP" "no key"
    Write-Host "  SKIP no key" -ForegroundColor Yellow
} else {
    try {
        $all = New-Object System.Collections.Generic.List[object]
        $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        foreach ($cat in @(
            @{ code = "CE7"; name = "cafe" },
            @{ code = "CS2"; name = "convenience" },
            @{ code = "FD6"; name = "food" }
        )) {
            $q = "category_group_code=$($cat.code)&x=$daeguX&y=$daeguY&radius=2000&sort=distance&size=15&page=1"
            $r = Invoke-WithRetry -Action {
                Invoke-RestMethod -Uri ("https://dapi.kakao.com/v2/local/search/category.json?" + $q) -Headers @{ Authorization = "KakaoAK $kakaoKey" } -TimeoutSec 60
            }
            foreach ($doc in @($r.documents)) {
                [void]$all.Add([PSCustomObject]@{
                    category = $cat.name; category_group_code = $cat.code
                    id = $doc.id; place_name = $doc.place_name; address_name = $doc.address_name
                    road_address_name = $doc.road_address_name; phone = $doc.phone
                    x = $doc.x; y = $doc.y; distance = $doc.distance
                    place_url = $doc.place_url; fetchedAt = $fetchedAt
                })
            }
            Write-Host "  $($cat.name): $($r.documents.Count)"
        }
        $path = Join-Path $outputDir "daegu_kakao_nearby_$timestamp.csv"
        Write-RowsCsv -Path $path -Rows @($all) -Append $false
        Write-Host "  SAVED $($all.Count)" -ForegroundColor Green
        Add-Result "kakao_nearby" "OK" "$($all.Count) rows"
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
        Add-Result "kakao_nearby" "FAIL" $_.Exception.Message
    }
}

# ===================== 11) TMAP =====================
Write-Host "`n=== 11. TMAP POI ===" -ForegroundColor Cyan
if (-not $tmapKey) {
    Add-Result "tmap_poi" "SKIP" "no key"
    Write-Host "  SKIP no key" -ForegroundColor Yellow
} else {
    try {
        $kw = [uri]::EscapeDataString(([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("7KCE6riw7LmYIOyztOygnOygnA=="))))
        $q = "version=1&searchKeyword=$kw&page=1&searchType=all&count=20&resCoordType=WGS84GEO&reqCoordType=WGS84GEO&centerLon=$daeguX&centerLat=$daeguY"
        $r = Invoke-WithRetry -Action {
            Invoke-RestMethod -Uri ("https://apis.openapi.sk.com/tmap/pois?" + $q) -Headers @{ appkey = $tmapKey; accept = "application/json" } -TimeoutSec 60
        }
        $fetchedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $rows = @(
            @($r.searchPoiInfo.pois.poi) | ForEach-Object {
                [PSCustomObject]@{
                    id = $_.id; name = $_.name
                    address = "$($_.upperAddrName) $($_.middleAddrName) $($_.lowerAddrName)"
                    frontLat = $_.frontLat; frontLon = $_.frontLon
                    noorLat = $_.noorLat; noorLon = $_.noorLon
                    radius = $_.radius; telNo = $_.telNo; fetchedAt = $fetchedAt
                }
            }
        )
        $path = Join-Path $outputDir "daegu_tmap_poi_chargers_$timestamp.csv"
        Write-RowsCsv -Path $path -Rows $rows -Append $false
        Write-Host "  SAVED $($rows.Count)" -ForegroundColor Green
        Add-Result "tmap_poi" "OK" "$($rows.Count) rows"
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
        Add-Result "tmap_poi" "FAIL" $_.Exception.Message
    }
}

Write-Host "`n========== DONE ==========" -ForegroundColor Yellow
$summary | Format-Table -AutoSize
Write-Host "Old file untouched: daegu_charger_status_20260716_104348.csv" -ForegroundColor DarkGray
Get-ChildItem $outputDir | Sort-Object LastWriteTime | Format-Table Name, Length, LastWriteTime -AutoSize

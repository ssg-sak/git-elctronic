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
$k = $envMap["DATA_GO_KR_KEY"]
$tmap = $envMap["TMAP_APP_KEY"]
$kakao = $envMap["KAKAO_REST_KEY"]
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$x = 128.6014; $y = 35.8714
$summary = @()

Write-Host "=== extract-new-only (skip already-have: charger/ultra/tour/parking) ===" -ForegroundColor Yellow
Write-Host "timestamp=$ts`n"

function Retry($action, $n = 4) {
  $last = $null
  for ($i = 1; $i -le $n; $i++) {
    try { return & $action } catch {
      $last = $_
      Write-Host "  retry $i/$n : $($_.Exception.Message)" -ForegroundColor DarkYellow
      Start-Sleep -Seconds (2 * $i)
    }
  }
  throw $last.Exception
}

function Save($name, $rows) {
  $p = Join-Path $out "${name}_$ts.csv"
  if (-not $rows -or @($rows).Count -eq 0) {
    Write-Host "  EMPTY $name" -ForegroundColor DarkYellow
    return $null
  }
  @($rows) | Export-Csv $p -NoTypeInformation -Encoding UTF8
  Write-Host "  SAVED $(@($rows).Count) -> $p" -ForegroundColor Green
  return $p
}

function XmlText($n) {
  if ($null -eq $n) { return $null }
  if ($n -is [string]) { return $n }
  if ($n.'#text') { return [string]$n.'#text' }
  $s = [string]$n
  if ($s -and $s -notmatch '^System\.') { return $s }
  return $null
}

function XmlRows($items) {
  $list = @($items)
  if ($list.Count -eq 0) { return @() }
  $skip = @('OuterXml','InnerXml','InnerText','Name','LocalName','NamespaceURI','Prefix','NodeType','ParentNode','OwnerDocument','IsEmpty','Attributes','HasAttributes','HasChildNodes','ChildNodes','FirstChild','LastChild','NextSibling','PreviousSibling','Value','BaseURI','SchemaInfo','#text')
  $props = $list[0] | Get-Member -MemberType Property | Where-Object { $skip -notcontains $_.Name } | Select-Object -ExpandProperty Name
  $fa = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  return @($list | ForEach-Object {
      $o = [ordered]@{ fetchedAt = $fa }
      foreach ($p in $props) { $o[$p] = XmlText $_.$p }
      [PSCustomObject]$o
    })
}

function Flatten-Obj($obj, $prefix = "") {
  $map = [ordered]@{}
  if ($null -eq $obj) { return $map }
  if ($obj -is [string] -or $obj -is [ValueType]) {
    $map[$(if ($prefix) { $prefix } else { "value" })] = $obj
    return $map
  }
  foreach ($pr in $obj.PSObject.Properties) {
    $name = if ($prefix) { "$prefix.$($pr.Name)" } else { $pr.Name }
    $val = $pr.Value
    if ($null -eq $val) {
      $map[$name] = $null
    } elseif ($val -is [Array] -or ($val -is [System.Collections.IEnumerable] -and -not ($val -is [string]))) {
      $arr = @($val)
      if ($arr.Count -eq 1 -and $arr[0] -isnot [string] -and $arr[0] -isnot [ValueType]) {
        $nested = Flatten-Obj $arr[0] $name
        foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
      } else {
        $map[$name] = ($arr | ForEach-Object { "$_" }) -join "|"
      }
    } elseif ($val.PSObject -and $val.PSObject.Properties.Count -gt 0 -and -not ($val -is [string]) -and -not ($val -is [ValueType])) {
      $nested = Flatten-Obj $val $name
      foreach ($k in $nested.Keys) { $map[$k] = $nested[$k] }
    } else {
      $map[$name] = $val
    }
  }
  return $map
}

function ObjRows($items) {
  $list = @($items)
  if ($list.Count -eq 0) { return @() }
  $fa = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  return @($list | ForEach-Object {
      $flat = Flatten-Obj $_
      $o = [ordered]@{ fetchedAt = $fa }
      foreach ($key in $flat.Keys) { $o[$key] = $flat[$key] }
      [PSCustomObject]$o
    })
}

function Get-WalkItems($body) {
  if ($null -eq $body) { return @() }
  # 실제 응답: body.items.item = [ {...}, {...} ]
  if ($body.items -and $body.items.item) {
    return @($body.items.item)
  }
  if ($body.item) { return @($body.item) }
  return @()
}

function Is-MockKey($v) {
  return (-not $v) -or ($v -match "MOCK")
}

# ---------- 1) Weather vilage (단기예보) ----------
Write-Host "=== 1. Weather getVilageFcst ===" -ForegroundColor Cyan
try {
  $now = Get-Date
  # 발표: 02,05,08,11,14,17,20,23 + 약 10분 후 제공 → 현재-1시간 기준으로 직전 발표시각
  $base = $now.AddHours(-1)
  $hours = @(2, 5, 8, 11, 14, 17, 20, 23)
  $h = [int]$base.ToString("HH")
  $btHour = ($hours | Where-Object { $_ -le $h } | Select-Object -Last 1)
  if ($null -eq $btHour) {
    $btHour = 23
    $base = $base.AddDays(-1)
  }
  $bd = $base.ToString("yyyyMMdd")
  $bt = "{0:D2}00" -f $btHour
  Write-Host "  base_date=$bd base_time=$bt nx=89 ny=90"
  $r = Retry {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst" `
      -Body @{
        serviceKey = $k; pageNo = "1"; numOfRows = "1000"; dataType = "JSON"
        base_date = $bd; base_time = $bt; nx = "89"; ny = "90"
      } -TimeoutSec 90
  }
  if ($r.response.header.resultCode -ne "00") {
    throw "code=$($r.response.header.resultCode) $($r.response.header.resultMsg)"
  }
  $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $rows = @(@($r.response.body.items.item) | ForEach-Object {
      [PSCustomObject]@{
        baseDate = $_.baseDate; baseTime = $_.baseTime
        fcstDate = $_.fcstDate; fcstTime = $_.fcstTime
        category = $_.category; fcstValue = $_.fcstValue
        nx = $_.nx; ny = $_.ny; fetchedAt = $fa
      }
    })
  Save "daegu_weather_vilage_fcst" $rows | Out-Null
  $summary += [PSCustomObject]@{ Name = "weather_vilage"; Status = "OK"; Detail = "$($rows.Count)" }
} catch {
  Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
  $summary += [PSCustomObject]@{ Name = "weather_vilage"; Status = "FAIL"; Detail = $_.Exception.Message }
}

# ---------- 2) Daegu city tourism ----------
Write-Host "`n=== 2. City tourism ===" -ForegroundColor Cyan
try {
  $all = New-Object System.Collections.Generic.List[object]
  $page = 1; $total = $null
  while ($true) {
    $r = Retry {
      [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList" `
          -Body @{ serviceKey = $k; pageNo = "$page"; numOfRows = "100" } -TimeoutSec 90)
    }
    $code = XmlText $r.response.header.resultCode
    if ($code -ne "00") { throw "code=$code $(XmlText $r.response.header.resultMsg)" }
    $items = @($r.response.body.items.item)
    if ($items.Count -eq 0) { break }
    if (-not $total) {
      $tc = XmlText $r.response.body.totalCount
      if ($tc) { $total = [int]$tc }
    }
    foreach ($it in $items) { [void]$all.Add($it) }
    Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"
    if ($total -and $all.Count -ge $total) { break }
    if ($items.Count -lt 100) { break }
    $page++; if ($page -gt 50) { break }
  }
  $rows = XmlRows $all
  Save "daegu_city_tour" $rows | Out-Null
  $summary += [PSCustomObject]@{ Name = "city_tour"; Status = "OK"; Detail = "$($rows.Count)" }
} catch {
  Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
  $summary += [PSCustomObject]@{ Name = "city_tour"; Status = "FAIL"; Detail = $_.Exception.Message }
}

# ---------- 3) Walk parks (파싱 수정) ----------
Write-Host "`n=== 3. Walk parks ===" -ForegroundColor Cyan
try {
  $all = New-Object System.Collections.Generic.List[object]
  $page = 1; $total = $null
  while ($true) {
    $q = "serviceKey=$([uri]::EscapeDataString($k))&pageNo=$page&numOfRows=100&type=json&lat=$y&lot=$x&radius=10"
    $r = Retry {
      Invoke-RestMethod -Uri ("https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?" + $q) -TimeoutSec 60
    }
    $code = $null
    if ($r.header.resultCode) { $code = [string]$r.header.resultCode }
    elseif ($r.response.header.resultCode) { $code = [string]$r.response.header.resultCode }
    if ($code -and $code -ne "00") { throw "code=$code" }

    $body = if ($r.body) { $r.body } elseif ($r.response.body) { $r.response.body } else { $r }
    $items = Get-WalkItems $body
    if ($items.Count -eq 0) {
      # 디버그: 키 구조 출력
      Write-Host "  (debug) body props: $(($body | Get-Member -MemberType NoteProperty,Property | Select-Object -ExpandProperty Name) -join ', ')"
      break
    }
    if (-not $total) {
      if ($body.totalCount) { $total = [int]$body.totalCount }
      elseif ($body.totalcount) { $total = [int]$body.totalcount }
    }
    foreach ($it in $items) { [void]$all.Add($it) }
    Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"
    if ($total -and $all.Count -ge $total) { break }
    if ($items.Count -lt 100) { break }
    $page++; if ($page -gt 30) { break }
  }
  $rows = ObjRows $all
  # 깨진 행 필터 (System.Object[] 문자열만 있는 경우)
  $rows = @($rows | Where-Object {
      $vals = $_.PSObject.Properties | Where-Object { $_.Name -ne "fetchedAt" } | ForEach-Object { [string]$_.Value }
      -not ($vals.Count -eq 1 -and $vals[0] -match '^System\.')
    })
  Save "daegu_walk_parks" $rows | Out-Null
  $summary += [PSCustomObject]@{ Name = "walk"; Status = $(if ($rows.Count -gt 0) { "OK" } else { "EMPTY" }); Detail = "$($rows.Count)" }
} catch {
  Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
  $summary += [PSCustomObject]@{ Name = "walk"; Status = "FAIL"; Detail = $_.Exception.Message }
}

# ---------- 4) Traffic ----------
Write-Host "`n=== 4. Traffic linkspeed ===" -ForegroundColor Cyan
try {
  $r = Retry {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest1/linkspeed" `
      -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "1000" } -TimeoutSec 90
  }
  $ok = $false; $rows = @()
  if ($r -is [xml]) {
    $ok = (XmlText $r.response.header.resultCode) -eq "00"
    $rows = XmlRows @($r.response.body.items.item)
  } else {
    $ok = ("$($r.header.resultCode)$($r.response.header.resultCode)" -match "00")
    $items = @()
    if ($r.response.body.items.item) { $items = @($r.response.body.items.item) }
    $rows = ObjRows $items
  }
  if (-not $ok) { throw "bad response / provider outage" }
  Save "daegu_traffic_linkspeed" $rows | Out-Null
  $summary += [PSCustomObject]@{ Name = "traffic"; Status = "OK"; Detail = "$($rows.Count)" }
} catch {
  Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
  $summary += [PSCustomObject]@{ Name = "traffic"; Status = "FAIL"; Detail = $_.Exception.Message }
}

Write-Host "`n=== 5. Traffic incident ===" -ForegroundColor Cyan
try {
  $r = Retry {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest/dgincident" `
      -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "1000" } -TimeoutSec 90
  }
  $ok = $false; $rows = @()
  if ($r -is [xml]) {
    $ok = (XmlText $r.response.header.resultCode) -eq "00"
    $rows = XmlRows @($r.response.body.items.item)
  } else {
    $ok = ("$($r.header.resultCode)$($r.response.header.resultCode)" -match "00")
    $items = @()
    if ($r.response.body.items.item) { $items = @($r.response.body.items.item) }
    $rows = ObjRows $items
  }
  if (-not $ok) { throw "bad response / provider outage" }
  Save "daegu_traffic_incident" $rows | Out-Null
  $summary += [PSCustomObject]@{ Name = "incident"; Status = "OK"; Detail = "$($rows.Count)" }
} catch {
  Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
  $summary += [PSCustomObject]@{ Name = "incident"; Status = "FAIL"; Detail = $_.Exception.Message }
}

# ---------- 6) Kakao ----------
Write-Host "`n=== 6. Kakao nearby ===" -ForegroundColor Cyan
if (Is-MockKey $kakao) {
  Write-Host "  SKIP (mock/empty KAKAO_REST_KEY)" -ForegroundColor DarkYellow
  $summary += [PSCustomObject]@{ Name = "kakao"; Status = "SKIP"; Detail = "mock key" }
} else {
  try {
    $all = New-Object System.Collections.Generic.List[object]
    $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    foreach ($cat in @(@{ c = "CE7"; n = "cafe" }, @{ c = "CS2"; n = "convenience" }, @{ c = "FD6"; n = "food" })) {
      for ($page = 1; $page -le 3; $page++) {
        $q = "category_group_code=$($cat.c)&x=$x&y=$y&radius=2000&sort=distance&size=15&page=$page"
        $r = Retry {
          Invoke-RestMethod -Uri ("https://dapi.kakao.com/v2/local/search/category.json?" + $q) `
            -Headers @{ Authorization = "KakaoAK $kakao" } -TimeoutSec 60
        }
        foreach ($d in @($r.documents)) {
          [void]$all.Add([PSCustomObject]@{
              category = $cat.n; category_group_code = $cat.c; id = $d.id
              place_name = $d.place_name; address_name = $d.address_name
              road_address_name = $d.road_address_name; phone = $d.phone
              x = $d.x; y = $d.y; distance = $d.distance; place_url = $d.place_url; fetchedAt = $fa
            })
        }
        if ($r.meta.is_end) { break }
      }
      Write-Host "  $($cat.n) done"
    }
    Save "daegu_kakao_nearby" @($all) | Out-Null
    $summary += [PSCustomObject]@{ Name = "kakao"; Status = "OK"; Detail = "$($all.Count)" }
  } catch {
    Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
    $summary += [PSCustomObject]@{ Name = "kakao"; Status = "FAIL"; Detail = $_.Exception.Message }
  }
}

# ---------- 7) TMAP ----------
Write-Host "`n=== 7. TMAP POI ===" -ForegroundColor Cyan
if (Is-MockKey $tmap) {
  Write-Host "  SKIP (mock/empty TMAP_APP_KEY)" -ForegroundColor DarkYellow
  $summary += [PSCustomObject]@{ Name = "tmap"; Status = "SKIP"; Detail = "mock key" }
} else {
  try {
    $kw = [uri]::EscapeDataString(([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("7KCE6riw7LmYIOyztOygnOygnA=="))))
    $q = "version=1&searchKeyword=$kw&page=1&searchType=all&count=20&resCoordType=WGS84GEO&reqCoordType=WGS84GEO&centerLon=$x&centerLat=$y"
    $r = Retry {
      Invoke-RestMethod -Uri ("https://apis.openapi.sk.com/tmap/pois?" + $q) `
        -Headers @{ appkey = $tmap; accept = "application/json" } -TimeoutSec 60
    }
    $fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $rows = @(@($r.searchPoiInfo.pois.poi) | ForEach-Object {
        [PSCustomObject]@{
          id = $_.id; name = $_.name
          address = "$($_.upperAddrName) $($_.middleAddrName) $($_.lowerAddrName)"
          frontLat = $_.frontLat; frontLon = $_.frontLon
          noorLat = $_.noorLat; noorLon = $_.noorLon
          radius = $_.radius; telNo = $_.telNo; fetchedAt = $fa
        }
      })
    Save "daegu_tmap_poi_chargers" $rows | Out-Null
    $summary += [PSCustomObject]@{ Name = "tmap"; Status = "OK"; Detail = "$($rows.Count)" }
  } catch {
    Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red
    $summary += [PSCustomObject]@{ Name = "tmap"; Status = "FAIL"; Detail = $_.Exception.Message }
  }
}

Write-Host "`n========== SUMMARY ==========" -ForegroundColor Yellow
$summary | Format-Table -AutoSize
Write-Host "`nNew files ($ts):"
Get-ChildItem $out -Filter "*$ts*" | Format-Table Name, Length, LastWriteTime -AutoSize

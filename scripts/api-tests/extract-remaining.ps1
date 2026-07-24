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
$k = $envMap["DATA_GO_KR_KEY"]; $tmap = $envMap["TMAP_APP_KEY"]; $kakao = $envMap["KAKAO_REST_KEY"]
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$x = 128.6014; $y = 35.8714
$summary = @()

function Retry($action, $n=5) {
  $last=$null
  for ($i=1; $i -le $n; $i++) {
    try { return & $action } catch {
      $last=$_; Write-Host "  retry $i/$n : $($_.Exception.Message)" -ForegroundColor DarkYellow
      Start-Sleep -Seconds (2*$i)
    }
  }
  throw $last.Exception
}
function Invoke-JsonUtf8 {
  param([string]$Uri, [int]$TimeoutSec = 60)
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
function Save($name, $rows) {
  $p = Join-Path $out "${name}_$ts.csv"
  if (-not $rows -or $rows.Count -eq 0) { Write-Host "  EMPTY $name"; return $null }
  $rows | Export-Csv $p -NoTypeInformation -Encoding UTF8
  Write-Host "  SAVED $($rows.Count) -> $p" -ForegroundColor Green
  return $p
}
function XmlText($n) {
  if ($null -eq $n) { return $null }
  if ($n -is [string]) { return $n }
  if ($n.'#text') { return [string]$n.'#text' }
  $s=[string]$n; if ($s -and $s -notmatch '^System\.') { return $s }; return $null
}
function XmlRows($items) {
  $list=@($items); if ($list.Count -eq 0) { return @() }
  $skip=@('OuterXml','InnerXml','InnerText','Name','LocalName','NamespaceURI','Prefix','NodeType','ParentNode','OwnerDocument','IsEmpty','Attributes','HasAttributes','HasChildNodes','ChildNodes','FirstChild','LastChild','NextSibling','PreviousSibling','Value','BaseURI','SchemaInfo','#text')
  $props=$list[0]|Get-Member -MemberType Property|Where-Object{$skip -notcontains $_.Name}|Select-Object -ExpandProperty Name
  $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  return @($list|ForEach-Object{ $o=[ordered]@{fetchedAt=$fa}; foreach($p in $props){$o[$p]=XmlText $_.$p}; [PSCustomObject]$o })
}
function ObjRows($items) {
  $list=@($items); if ($list.Count -eq 0) { return @() }
  $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  return @($list|ForEach-Object{ $o=[ordered]@{fetchedAt=$fa}; foreach($pr in $_.PSObject.Properties){ if($pr.Name -ne 'fetchedAt'){$o[$pr.Name]=$pr.Value} }; [PSCustomObject]$o })
}

# 1 Weather vilage (short-term)
Write-Host "`n=== Weather getVilageFcst ===" -ForegroundColor Cyan
try {
  $base=(Get-Date).AddHours(-1)
  # announce times: 0200,0500,0800,1100,1400,1700,2000,2300
  $h=[int]$base.ToString('HH'); $bt=switch($h){ {$_ -lt 2}{'2300'} {$_ -lt 5}{'0200'} {$_ -lt 8}{'0500'} {$_ -lt 11}{'0800'} {$_ -lt 14}{'1100'} {$_ -lt 17}{'1400'} {$_ -lt 20}{'1700'} {$_ -lt 23}{'2000'} default{'2300'} }
  if ($bt -eq '2300' -and $h -lt 2) { $base=$base.AddDays(-1) }
  $bd=$base.ToString('yyyyMMdd')
  $r = Retry { Invoke-RestMethod -Uri 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst' -Body @{serviceKey=$k;pageNo='1';numOfRows='1000';dataType='JSON';base_date=$bd;base_time=$bt;nx='89';ny='90'} -TimeoutSec 90 }
  if ($r.response.header.resultCode -ne '00') { throw "code=$($r.response.header.resultCode) $($r.response.header.resultMsg)" }
  $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  $rows=@(@($r.response.body.items.item)|ForEach-Object{[PSCustomObject]@{baseDate=$_.baseDate;baseTime=$_.baseTime;fcstDate=$_.fcstDate;fcstTime=$_.fcstTime;category=$_.category;fcstValue=$_.fcstValue;nx=$_.nx;ny=$_.ny;fetchedAt=$fa}})
  Save 'daegu_weather_vilage_fcst' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='weather_vilage';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='weather_vilage';Status='FAIL';Detail=$_.Exception.Message} }

# 2 TourAPI full pages
Write-Host "`n=== TourAPI ===" -ForegroundColor Cyan
try {
  $all=New-Object System.Collections.Generic.List[object]; $page=1; $total=$null
  while ($true) {
    $q="serviceKey=$([uri]::EscapeDataString($k))&MobileOS=ETC&MobileApp=EVSafeCharge&_type=json&mapX=$x&mapY=$y&radius=5000&numOfRows=100&pageNo=$page&contentTypeId=12"
    $r=Retry { Invoke-JsonUtf8 -Uri ("https://apis.data.go.kr/B551011/KorService2/locationBasedList2?"+$q) -TimeoutSec 60 }
    if ($r.response.header.resultCode -ne '0000') { throw "code=$($r.response.header.resultCode) $($r.response.header.resultMsg)" }
    $items=@($r.response.body.items.item); if ($items.Count -eq 0) { break }
    if (-not $total) { $total=[int]$r.response.body.totalCount }
    foreach($it in $items){[void]$all.Add($it)}
    Write-Host "  page $page $($items.Count) acc $($all.Count)/$total"
    if ($total -and $all.Count -ge $total) { break }
    if ($items.Count -lt 100) { break }
    $page++; if ($page -gt 30) { break }
  }
  $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  $rows=@($all|ForEach-Object{[PSCustomObject]@{contentid=$_.contentid;title=$_.title;addr1=$_.addr1;addr2=$_.addr2;mapx=$_.mapx;mapy=$_.mapy;dist=$_.dist;cat1=$_.cat1;cat2=$_.cat2;cat3=$_.cat3;tel=$_.tel;firstimage=$_.firstimage;fetchedAt=$fa}})
  Save 'daegu_tour_attractions' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='tour';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='tour';Status='FAIL';Detail=$_.Exception.Message} }

# 3 City tourism
Write-Host "`n=== City tourism ===" -ForegroundColor Cyan
try {
  $all=New-Object System.Collections.Generic.List[object]; $page=1; $total=$null
  while ($true) {
    $r=Retry { [xml](Invoke-RestMethod -Uri 'https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList' -Body @{serviceKey=$k;pageNo="$page";numOfRows='100'} -TimeoutSec 90) }
    $code=XmlText $r.response.header.resultCode
    if ($code -ne '00') { throw "code=$code $(XmlText $r.response.header.resultMsg)" }
    $items=@($r.response.body.items.item); if ($items.Count -eq 0) { break }
    if (-not $total) { $tc=XmlText $r.response.body.totalCount; if ($tc){$total=[int]$tc} }
    foreach($it in $items){[void]$all.Add($it)}
    Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"
    if ($total -and $all.Count -ge $total) { break }
    if ($items.Count -lt 100) { break }
    $page++; if ($page -gt 50) { break }
  }
  $rows=XmlRows $all
  Save 'daegu_city_tour' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='city_tour';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='city_tour';Status='FAIL';Detail=$_.Exception.Message} }

# 4 Walk parks
Write-Host "`n=== Walk parks ===" -ForegroundColor Cyan
try {
  $all=New-Object System.Collections.Generic.List[object]; $page=1; $total=$null
  while ($true) {
    $q="serviceKey=$([uri]::EscapeDataString($k))&pageNo=$page&numOfRows=100&type=json&lat=$y&lot=$x&radius=10"
    $r=Retry { Invoke-RestMethod -Uri ("https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?"+$q) -TimeoutSec 60 }
    if ($r.header.resultCode -ne '00') { throw "code=$($r.header.resultCode) $($r.header.resultMsg)" }
    $items=@(); if ($r.body.items){$items=@($r.body.items)} elseif ($r.body.item){$items=@($r.body.item)}
    if ($items.Count -eq 0) { break }
    if (-not $total -and $r.body.totalCount){$total=[int]$r.body.totalCount}
    foreach($it in $items){[void]$all.Add($it)}
    Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"
    if ($total -and $all.Count -ge $total) { break }
    if ($items.Count -lt 100) { break }
    $page++; if ($page -gt 30) { break }
  }
  $rows=ObjRows $all
  Save 'daegu_walk_parks' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='walk';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='walk';Status='FAIL';Detail=$_.Exception.Message} }

# 5 Traffic
Write-Host "`n=== Traffic linkspeed ===" -ForegroundColor Cyan
try {
  $r=Retry { Invoke-RestMethod -Uri 'https://apis.data.go.kr/6270000/service/rest1/linkspeed' -Body @{serviceKey=$k;pageNo='1';numOfRows='1000'} -TimeoutSec 90 }
  $ok=$false; $rows=@()
  if ($r -is [xml]) { $ok=(XmlText $r.response.header.resultCode) -eq '00'; $rows=XmlRows @($r.response.body.items.item) }
  else { $ok=("$($r.header.resultCode)$($r.response.header.resultCode)" -match '00'); $items=@(); if($r.response.body.items.item){$items=@($r.response.body.items.item)}; $rows=ObjRows $items }
  if (-not $ok) { throw 'bad response' }
  Save 'daegu_traffic_linkspeed' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='traffic';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='traffic';Status='FAIL';Detail=$_.Exception.Message} }

Write-Host "`n=== Traffic incident ===" -ForegroundColor Cyan
try {
  $r=Retry { Invoke-RestMethod -Uri 'https://apis.data.go.kr/6270000/service/rest/dgincident' -Body @{serviceKey=$k;pageNo='1';numOfRows='1000'} -TimeoutSec 90 }
  $ok=$false; $rows=@()
  if ($r -is [xml]) { $ok=(XmlText $r.response.header.resultCode) -eq '00'; $rows=XmlRows @($r.response.body.items.item) }
  else { $ok=("$($r.header.resultCode)$($r.response.header.resultCode)" -match '00'); $items=@(); if($r.response.body.items.item){$items=@($r.response.body.items.item)}; $rows=ObjRows $items }
  if (-not $ok) { throw 'bad response' }
  Save 'daegu_traffic_incident' $rows | Out-Null
  $summary += [PSCustomObject]@{Name='incident';Status='OK';Detail="$($rows.Count)"}
} catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='incident';Status='FAIL';Detail=$_.Exception.Message} }

# 6 Kakao
Write-Host "`n=== Kakao ===" -ForegroundColor Cyan
if (-not $kakao) { $summary += [PSCustomObject]@{Name='kakao';Status='SKIP';Detail='no key'} }
else {
  try {
    $all=New-Object System.Collections.Generic.List[object]; $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    foreach ($cat in @(@{c='CE7';n='cafe'},@{c='CS2';n='convenience'},@{c='FD6';n='food'})) {
      for ($page=1; $page -le 3; $page++) {
        $q="category_group_code=$($cat.c)&x=$x&y=$y&radius=2000&sort=distance&size=15&page=$page"
        $r=Retry { Invoke-RestMethod -Uri ("https://dapi.kakao.com/v2/local/search/category.json?"+$q) -Headers @{Authorization="KakaoAK $kakao"} -TimeoutSec 60 }
        foreach ($d in @($r.documents)) {
          [void]$all.Add([PSCustomObject]@{category=$cat.n;category_group_code=$cat.c;id=$d.id;place_name=$d.place_name;address_name=$d.address_name;road_address_name=$d.road_address_name;phone=$d.phone;x=$d.x;y=$d.y;distance=$d.distance;place_url=$d.place_url;fetchedAt=$fa})
        }
        if (-not $r.meta.is_end) { } else { break }
      }
      Write-Host "  $($cat.n) done"
    }
    Save 'daegu_kakao_nearby' @($all) | Out-Null
    $summary += [PSCustomObject]@{Name='kakao';Status='OK';Detail="$($all.Count)"}
  } catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='kakao';Status='FAIL';Detail=$_.Exception.Message} }
}

# 7 TMAP
Write-Host "`n=== TMAP ===" -ForegroundColor Cyan
if (-not $tmap) { $summary += [PSCustomObject]@{Name='tmap';Status='SKIP';Detail='no key'} }
else {
  try {
    $kw=[uri]::EscapeDataString(([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('7KCE6riw7LmYIOyztOygnOygnA=='))))
    $q="version=1&searchKeyword=$kw&page=1&searchType=all&count=20&resCoordType=WGS84GEO&reqCoordType=WGS84GEO&centerLon=$x&centerLat=$y"
    $r=Retry { Invoke-RestMethod -Uri ("https://apis.openapi.sk.com/tmap/pois?"+$q) -Headers @{appkey=$tmap;accept='application/json'} -TimeoutSec 60 }
    $fa=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $rows=@(@($r.searchPoiInfo.pois.poi)|ForEach-Object{[PSCustomObject]@{id=$_.id;name=$_.name;address="$($_.upperAddrName) $($_.middleAddrName) $($_.lowerAddrName)";frontLat=$_.frontLat;frontLon=$_.frontLon;noorLat=$_.noorLat;noorLon=$_.noorLon;radius=$_.radius;telNo=$_.telNo;fetchedAt=$fa}})
    Save 'daegu_tmap_poi_chargers' $rows | Out-Null
    $summary += [PSCustomObject]@{Name='tmap';Status='OK';Detail="$($rows.Count)"}
  } catch { Write-Host "  FAIL $($_.Exception.Message)" -ForegroundColor Red; $summary += [PSCustomObject]@{Name='tmap';Status='FAIL';Detail=$_.Exception.Message} }
}

Write-Host "`n========== SUMMARY ==========" -ForegroundColor Yellow
$summary | Format-Table -AutoSize
Get-ChildItem $out | Sort-Object LastWriteTime | Format-Table Name, Length, LastWriteTime -AutoSize

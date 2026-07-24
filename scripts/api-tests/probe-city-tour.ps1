[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envMap = @{}
Get-Content (Join-Path $root ".env") -Encoding UTF8 | ForEach-Object {
  if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
    $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
  }
}
$k = $envMap["DATA_GO_KR_KEY"]
$enc = [uri]::EscapeDataString($k)

function TryCall($label, $script) {
  Write-Host "`n=== $label ===" -ForegroundColor Cyan
  try {
    $r = & $script
    if ($r -is [xml]) {
      Write-Host "XML code:" ( $r.response.header.resultCode.'#text' )
      Write-Host "XML msg :" ( $r.response.header.resultMsg.'#text' )
      $n = @($r.response.body.items.item).Count
      Write-Host "items:" $n
    } else {
      Write-Host "OK type:" $r.GetType().FullName
      Write-Host ($r | ConvertTo-Json -Compress -Depth 3).Substring(0, [Math]::Min(300, (($r | ConvertTo-Json -Compress -Depth 3).Length)))
    }
  } catch {
    $resp = $_.Exception.Response
    if ($resp) {
      Write-Host "HTTP" ([int]$resp.StatusCode)
      try {
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $sr.ReadToEnd()
        if ($body.Length -gt 400) { $body = $body.Substring(0,400) }
        Write-Host "BODY:" $body
      } catch { Write-Host $_.Exception.Message }
    } else {
      Write-Host "ERR:" $_.Exception.Message
    }
  }
}

# A: Body hashtable (decoding key) — 기존 방식
TryCall "A Body decoding" {
  [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList" `
      -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "3" } -TimeoutSec 60)
}

# B: Query string with encoded key
TryCall "B Query encoded key" {
  $uri = "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList?serviceKey=$enc&pageNo=1&numOfRows=3"
  [xml](Invoke-RestMethod -Uri $uri -TimeoutSec 60)
}

# C: WebRequest for raw status
TryCall "C WebRequest Body" {
  $r = Invoke-WebRequest -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList" `
    -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "3" } -Method Get -TimeoutSec 60 -UseBasicParsing
  Write-Host "status" $r.StatusCode
  Write-Host $r.Content.Substring(0, [Math]::Min(400, $r.Content.Length))
  $r
}

# D: Compare with working TourAPI (control)
TryCall "D TourAPI control" {
  $uri = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2?serviceKey=$enc&MobileOS=ETC&MobileApp=EVSafeCharge&_type=json&mapX=128.6014&mapY=35.8714&radius=3000&numOfRows=1&pageNo=1&contentTypeId=12"
  Invoke-RestMethod -Uri $uri -TimeoutSec 60
}

# E: walk parks control (same 6270000 agency)
TryCall "E Walk parks control" {
  $uri = "https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?serviceKey=$enc&pageNo=1&numOfRows=1&type=json&lat=35.8714&lot=128.6014&radius=5"
  Invoke-RestMethod -Uri $uri -TimeoutSec 60
}

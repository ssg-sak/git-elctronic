# Daegu traffic APIs (linkspeed / dgincident) — one-shot probe with HTTP status detail
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
  if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
    $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
  }
}
$k = $envMap["DATA_GO_KR_KEY"]
if (-not $k) { Write-Host "DATA_GO_KR_KEY missing in .env" -ForegroundColor Red; exit 1 }

function Probe-TrafficApi {
  param(
    [string]$Name,
    [string]$Uri
  )
  Write-Host "`n=== $Name ===" -ForegroundColor Cyan
  Write-Host "URI: $Uri"

  # Method A: -Body (recommended by extract-new-only.ps1)
  try {
    $r = Invoke-WebRequest -Uri $Uri -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "3" } -TimeoutSec 90 -UseBasicParsing
    $snippet = ($r.Content -replace "\s+", " ").Substring(0, [Math]::Min(400, $r.Content.Length))
    Write-Host "[Body] HTTP $($r.StatusCode)" -ForegroundColor Green
    Write-Host $snippet
    return
  } catch {
    $code = $_.Exception.Response.StatusCode.value__
    $body = ""
    try {
      $stream = $_.Exception.Response.GetResponseStream()
      $reader = New-Object System.IO.StreamReader($stream)
      $body = $reader.ReadToEnd()
      $reader.Close()
    } catch { }
    $snippet = if ($body) { ($body -replace "\s+", " ").Substring(0, [Math]::Min(400, $body.Length)) } else { $_.Exception.Message }
    Write-Host "[Body] HTTP $code" -ForegroundColor Red
    Write-Host $snippet
  }

  # Method B: query string (test-all-apis style)
  try {
    $q = [uri]::EscapeDataString($k)
    $url = "${Uri}?serviceKey=$q&pageNo=1&numOfRows=3"
    $r2 = Invoke-WebRequest -Uri $url -TimeoutSec 90 -UseBasicParsing
    $snippet2 = ($r2.Content -replace "\s+", " ").Substring(0, [Math]::Min(400, $r2.Content.Length))
    Write-Host "[Query] HTTP $($r2.StatusCode)" -ForegroundColor Green
    Write-Host $snippet2
  } catch {
    $code2 = $_.Exception.Response.StatusCode.value__
    $body2 = ""
    try {
      $stream2 = $_.Exception.Response.GetResponseStream()
      $reader2 = New-Object System.IO.StreamReader($stream2)
      $body2 = $reader2.ReadToEnd()
      $reader2.Close()
    } catch { }
    $snippet2 = if ($body2) { ($body2 -replace "\s+", " ").Substring(0, [Math]::Min(400, $body2.Length)) } else { $_.Exception.Message }
    Write-Host "[Query] HTTP $code2" -ForegroundColor Red
    Write-Host $snippet2
  }
}

Probe-TrafficApi -Name "linkspeed (교통소통정보 신)" -Uri "https://apis.data.go.kr/6270000/service/rest1/linkspeed"
Probe-TrafficApi -Name "dgincident (돌발 교통정보 신)" -Uri "https://apis.data.go.kr/6270000/service/rest/dgincident"

# Control: same agency walk API (6270000) — should PASS if key is valid
Write-Host "`n=== control: dgInParkwalk (6270000 agency) ===" -ForegroundColor Cyan
try {
  $ctrl = Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList" `
    -Body @{ serviceKey = $k; pageNo = "1"; numOfRows = "1"; type = "json"; lat = "35.8714"; lot = "128.6014"; radius = "5" } -TimeoutSec 60
  $rc = "$($ctrl.header.resultCode)$($ctrl.response.header.resultCode)"
  Write-Host "control resultCode match 00: $($rc -match '00')" -ForegroundColor $(if ($rc -match '00') { 'Green' } else { 'Red' })
} catch {
  Write-Host "control FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

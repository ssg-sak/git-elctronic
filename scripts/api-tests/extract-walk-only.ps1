[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$out = Join-Path $root "docs\data\extracted"
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
  if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
    $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
  }
}
$k = $envMap["DATA_GO_KR_KEY"]
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$x = 128.6014; $y = 35.8714

Write-Host "=== Walk parks only ($ts) ===" -ForegroundColor Cyan
$all = New-Object System.Collections.Generic.List[object]
$page = 1; $total = $null
while ($true) {
  $q = "serviceKey=$([uri]::EscapeDataString($k))&pageNo=$page&numOfRows=100&type=json&lat=$y&lot=$x&radius=10"
  $r = Invoke-RestMethod -Uri ("https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?" + $q) -TimeoutSec 60
  if ($r.header.resultCode -ne "00") { throw "code=$($r.header.resultCode)" }
  if (-not $total -and $r.body.totalCount) { $total = [int]$r.body.totalCount }
  $items = @()
  if ($r.body.items -and $r.body.items.item) {
    $items = @($r.body.items.item)
  }
  if ($items.Count -eq 0) { break }
  foreach ($it in $items) { [void]$all.Add($it) }
  Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"
  if ($total -and $all.Count -ge $total) { break }
  if ($items.Count -lt 100) { break }
  $page++; if ($page -gt 30) { break }
}

$fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$rows = @($all | ForEach-Object {
    [PSCustomObject]@{
      fetchedAt  = $fa
      id         = $_.id
      mngNo      = $_.mngNo
      parkNm     = $_.parkNm
      parkType   = $_.parkType
      roadNmAddr = $_.roadNmAddr
      lotNoAddr  = $_.lotNoAddr
      lat        = $_.lat
      lot        = $_.lot
      mngInstNm  = $_.mngInstNm
      mngInstTel = $_.mngInstTel
      dongNm     = $_.dongNm
      sggNm      = $_.sggNm
    }
  })

$path = Join-Path $out "daegu_walk_parks_$ts.csv"
$rows | Export-Csv $path -NoTypeInformation -Encoding UTF8
Write-Host "SAVED $($rows.Count) -> $path" -ForegroundColor Green

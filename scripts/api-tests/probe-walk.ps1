[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envMap = @{}
Get-Content (Join-Path $root ".env") -Encoding UTF8 | ForEach-Object {
  if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
    $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
  }
}
$k = $envMap["DATA_GO_KR_KEY"]
$x = 128.6014; $y = 35.8714
$q = "serviceKey=$([uri]::EscapeDataString($k))&pageNo=1&numOfRows=3&type=json&lat=$y&lot=$x&radius=5"
$uri = "https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?" + $q
try {
  $r = Invoke-RestMethod -Uri $uri -TimeoutSec 60
  Write-Host "TYPE:" $r.GetType().FullName
  Write-Host "TOPKEYS:" (($r.PSObject.Properties.Name) -join ",")
  if ($r.header) { Write-Host "HEADER:" ($r.header | ConvertTo-Json -Compress -Depth 4) }
  if ($r.body) {
    Write-Host "BODYKEYS:" (($r.body.PSObject.Properties.Name) -join ",")
    Write-Host "TOTAL:" $r.body.totalCount
    $items = $r.body.items
    if ($null -eq $items) {
      Write-Host "ITEMS: null"
    } else {
      Write-Host "ITEMS_TYPE:" $items.GetType().FullName
      Write-Host "ITEMS_COUNT:" @($items).Count
      Write-Host "ITEMS_JSON:" ($items | ConvertTo-Json -Depth 8)
    }
  } else {
    Write-Host "RAW:" ($r | ConvertTo-Json -Depth 8)
  }
} catch {
  Write-Host "ERR:" $_.Exception.Message
  if ($_.ErrorDetails) { Write-Host $_.ErrorDetails.Message }
}

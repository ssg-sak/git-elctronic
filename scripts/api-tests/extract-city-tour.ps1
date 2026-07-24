[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"
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

function Get-NodeText($n) {
  if ($null -eq $n) { return "" }
  if ($n -is [string]) { return $n }
  if ($n.'#text') { return [string]$n.'#text' }
  try {
    $s = [string]$n
    if ($s -and $s -notmatch '^System\.') { return $s }
  } catch {}
  return ""
}

Write-Host "=== Daegu city tourism ($ts) ===" -ForegroundColor Cyan

$all = New-Object System.Collections.Generic.List[object]
$page = 1
$total = $null

while ($true) {
  $xml = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList" `
      -Body @{ serviceKey = $k; pageNo = "$page"; numOfRows = "100" } -TimeoutSec 90)

  $code = Get-NodeText $xml.response.header.resultCode
  if ($code -ne "00") {
    throw "code=$code $(Get-NodeText $xml.response.header.resultMsg)"
  }

  if (-not $total) {
    $tc = Get-NodeText $xml.response.body.totalCount
    if ($tc) { $total = [int]$tc }
  }

  $rawItems = $xml.response.body.items.item
  if ($null -eq $rawItems) { break }

  # 단일 item이면 배열이 아닐 수 있음
  $items = @($rawItems)
  if ($items.Count -eq 0) { break }

  foreach ($it in $items) {
    [void]$all.Add($it)
  }

  Write-Host "  page $page $($items.Count) acc $($all.Count)/$(if($total){$total}else{'?'})"

  if ($total -and $all.Count -ge $total) { break }
  if ($items.Count -lt 100) { break }
  $page++
  if ($page -gt 50) { break }
}

$fa = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 첫 아이템에서 자식 요소명 수집 (XML Element)
$fieldNames = New-Object System.Collections.Generic.List[string]
$sample = $all[0]
if ($sample -is [System.Xml.XmlElement]) {
  foreach ($child in $sample.ChildNodes) {
    if ($child.NodeType -eq [System.Xml.XmlNodeType]::Element) {
      if (-not $fieldNames.Contains($child.Name)) { [void]$fieldNames.Add($child.Name) }
    }
  }
} else {
  $sample.PSObject.Properties | ForEach-Object {
    if ($_.Name -notin @('OuterXml','InnerXml','InnerText','Name','LocalName','NamespaceURI','Prefix','NodeType','ParentNode','OwnerDocument','IsEmpty','Attributes','HasAttributes','HasChildNodes','ChildNodes','FirstChild','LastChild','NextSibling','PreviousSibling','Value','BaseURI','SchemaInfo','#text')) {
      [void]$fieldNames.Add($_.Name)
    }
  }
}

Write-Host "  fields: $($fieldNames -join ', ')"

$rows = @()
foreach ($it in $all) {
  $o = [ordered]@{ fetchedAt = $fa }
  foreach ($fn in $fieldNames) {
    if ($it -is [System.Xml.XmlElement]) {
      $node = $it.SelectSingleNode($fn)
      $o[$fn] = if ($node) { $node.InnerText } else { "" }
    } else {
      $o[$fn] = Get-NodeText $it.$fn
    }
  }
  $rows += [PSCustomObject]$o
}

$path = Join-Path $out "daegu_city_tour_$ts.csv"
$rows | Export-Csv $path -NoTypeInformation -Encoding UTF8
Write-Host "SAVED $($rows.Count) -> $path" -ForegroundColor Green

# 샘플 3행
Write-Host "`nSample:"
$rows | Select-Object -First 3 | Format-List

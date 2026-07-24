# TMAP Full Text Geocoding test (same appKey as routes)
param(
    [string]$Address = "Daegu Jung-gu Dongseong-ro"
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root '.env'
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
        $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$appKey = $envMap['TMAP_APP_KEY']
if (-not $appKey) {
    Write-Error 'TMAP_APP_KEY missing in .env'
    exit 1
}

if ($Address -eq 'Daegu Jung-gu Dongseong-ro') {
    $Address = [string]::Concat([char]0xB300, [char]0xAD6C, [char]0xAD11, [char]0xC5ED, [char]0xC2DC, ' ',
        [char]0xC911, [char]0xAD6C, ' ',
        [char]0xB3D9, [char]0xC131, [char]0xB85C)
}

$encoded = [System.Uri]::EscapeDataString($Address)
$base = 'https://apis.openapi.sk.com/tmap/geo/fullAddrGeo'
$query = "version=1&fullAddr=$encoded&coordType=WGS84GEO&addressFlag=F01&page=1&count=1&appKey=$appKey"
$url = "$base`?$query"

Write-Host ""
Write-Host "[Geocoding] $Address" -ForegroundColor Cyan

try {
    $resp = Invoke-RestMethod -Uri $url -Headers @{ accept = 'application/json' }
    Write-Host 'OK - geocoding works with existing TMAP_APP_KEY' -ForegroundColor Green
    $resp | ConvertTo-Json -Depth 6
    $outFile = Join-Path $PSScriptRoot 'tmap-geocoding-result.json'
    $resp | ConvertTo-Json -Depth 10 | Out-File $outFile -Encoding utf8
    Write-Host "Saved: $outFile" -ForegroundColor Yellow
}
catch {
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message -ForegroundColor Red }
    if ($_.Exception.Response) {
        Write-Host "HTTP: $([int]$_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

# UTIC 돌발 개방데이터 프로브 (키는 .env의 UTIC_API_KEY만 사용)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { throw ".env not found: $envFile" }

Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"'), "Process")
    }
}

$key = $env:UTIC_API_KEY
if (-not $key) { throw "UTIC_API_KEY missing in .env" }

$url = "http://www.utic.go.kr/guide/imsOpenData.do?key=$key"
Write-Host "GET imsOpenData.do (key length=$($key.Length))"
try {
    $resp = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec 60 -UseBasicParsing
    $body = $resp.Content
    $outDir = Join-Path $root "docs\data\extracted"
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outPath = Join-Path $outDir "utic_incident_$stamp.xml"
    Set-Content -Path $outPath -Value $body -Encoding UTF8

    $preview = if ($body.Length -gt 800) { $body.Substring(0, 800) } else { $body }
    Write-Host "status=$($resp.StatusCode) bytes=$($body.Length)"
    Write-Host "saved=$outPath"
    Write-Host "--- preview ---"
    Write-Host $preview
} catch {
    Write-Host "FAIL: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        Write-Host "HTTP $([int]$_.Exception.Response.StatusCode)"
    }
    exit 1
}

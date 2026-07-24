[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 프로젝트 루트의 .env 파일 경로 (scripts/api-tests/ -> scripts/ -> root)
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $projectRoot ".env"
$key = ""
if (Test-Path $envFile) {
    $line = (Get-Content $envFile | Where-Object { $_ -match "^DATA_GO_KR_KEY=" } | Select-Object -First 1)
    if ($line) { $key = $line -replace "^DATA_GO_KR_KEY=", "" }
}

if (-not $key -or $key -like "MOCK*") {
    Write-Error ".env에 실제 DATA_GO_KR_KEY가 없습니다. (파일: $envFile)"
    exit 1
}

Write-Host "키 확인 완료: $($key.Substring(0,8))..." -ForegroundColor DarkGray

Write-Host "`n=== 충전소 정보 (대구, 5개) ===" -ForegroundColor Cyan
try {
    $url = "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo?serviceKey=$key&pageNo=1&numOfRows=5&zcode=27"
    $result = [xml](Invoke-RestMethod -Uri $url -TimeoutSec 30)
    $items = $result.response.body.items.item
    $items | Select-Object statNm, addr, lat, lng, chgerType, useTime | Format-List
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== 충전기 실시간 상태 (대구, 5개) ===" -ForegroundColor Cyan
try {
    $url = "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus?serviceKey=$key&pageNo=1&numOfRows=5&zcode=27&period=10"
    $result = [xml](Invoke-RestMethod -Uri $url -TimeoutSec 30)
    $items = $result.response.body.items.item
    $items | Select-Object statNm, chgerId, stat, statUpdDt | Format-List
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== 기상청 현재 날씨 (대구) ===" -ForegroundColor Cyan
try {
    $base = (Get-Date).AddMinutes(-50)
    $baseDate = $base.ToString("yyyyMMdd")
    $baseTime = $base.ToString("HH") + "00"
    $url = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst?serviceKey=$key&pageNo=1&numOfRows=10&dataType=JSON&base_date=$baseDate&base_time=$baseTime&nx=89&ny=90"
    $result = Invoke-RestMethod -Uri $url -TimeoutSec 30
    $result.response.body.items.item | Format-Table -AutoSize
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
}

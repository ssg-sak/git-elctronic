# TMAP 자동차 경로 안내 API 테스트 스크립트 (실시간 교통 반영 이동시간)
# 사용법:
#   .\test-tmap-route-api.ps1     → 기본: 강남역 → 서울중구 SKT타워 전기차충전소
#   .\test-tmap-route-api.ps1 -StartX 127.1054 -StartY 37.3595 -EndX 126.9845 -EndY 37.5666
# 결과: 콘솔에 이동거리/소요시간/통행료 출력 + 전체 응답을 tmap-route-result.json 파일로 저장

param(
    [double]$StartX = 127.02761,      # 출발지 경도 (기본: 강남역)
    [double]$StartY = 37.49794,       # 출발지 위도
    [double]$EndX = 126.98452047,     # 도착지 경도 (기본: SKT타워 전기차충전소)
    [double]$EndY = 37.56656541      # 도착지 위도
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$envFile = Join-Path $root ".env"
$envMap = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match "^\s*([A-Z0-9_]+)\s*=\s*(.*)$") {
        $envMap[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
    }
}
$appKey = $envMap["TMAP_APP_KEY"]
if (-not $appKey) {
    Write-Error ".env 파일에 TMAP_APP_KEY가 없습니다."
    exit 1
}

$body = @{
    startX        = "$StartX"
    startY        = "$StartY"
    endX          = "$EndX"
    endY          = "$EndY"
    reqCoordType  = "WGS84GEO"
    resCoordType  = "WGS84GEO"
    searchOption  = "0"    # 0 = 교통최적+추천 (실시간 교통 반영)
    trafficInfo   = "Y"
} | ConvertTo-Json

Write-Host "`n[경로 탐색] ($StartY, $StartX) → ($EndY, $EndX)" -ForegroundColor Cyan

try {
    $resp = Invoke-RestMethod -Uri "https://apis.openapi.sk.com/tmap/routes?version=1" `
        -Method Post `
        -Headers @{ appKey = $appKey; accept = "application/json" } `
        -ContentType "application/json" `
        -Body $body

    $summary = $resp.features[0].properties
    $distKm = [Math]::Round($summary.totalDistance / 1000, 1)
    $timeMin = [Math]::Round($summary.totalTime / 60, 0)
    $arrival = (Get-Date).AddSeconds($summary.totalTime).ToString("HH:mm")

    Write-Host "실제 도로 이동거리 : $distKm km" -ForegroundColor Green
    Write-Host "예상 소요시간      : $timeMin 분 (실시간 교통 반영)" -ForegroundColor Green
    Write-Host "예상 도착시각      : $arrival" -ForegroundColor Green
    Write-Host "예상 통행료        : $($summary.totalFare) 원" -ForegroundColor Green
    Write-Host "경로 좌표 포인트 수: $($resp.features.Count) 개"

    $outFile = Join-Path $PSScriptRoot "tmap-route-result.json"
    $resp | ConvertTo-Json -Depth 10 | Out-File $outFile -Encoding utf8
    Write-Host "`n전체 응답 저장됨: $outFile" -ForegroundColor Yellow
}
catch {
    Write-Host "호출 실패: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "HTTP 상태: $([int]$_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

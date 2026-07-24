[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8

$key = "84412dc666fd5ec20910e654b4ca33c9a35dd3bd77f0b36d0c7e74b6be753554"
$outputDir = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "docs\data\extracted"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# ── 1. 충전소 정보 (대구, 최대 999건) ──────────────────────────
Write-Host "`n=== 충전소 기본정보 수집 중 (대구 zcode=27) ===" -ForegroundColor Cyan
# CSV 저장 경로 미리 설정
$csvPath = Join-Path $outputDir ("daegu_charger_info_" + $timestamp + ".csv")
Write-Host "  저장 경로: $csvPath" -ForegroundColor DarkGray

$allStations = @()
$page = 1
$totalCount = 9999
do {
    $params = @{ serviceKey = $key; numOfRows = "999"; pageNo = "$page"; zcode = "27" }
    try {
        $r = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo" -Body $params -TimeoutSec 90)
        $items = $r.response.body.items.item
        if ($null -ne $items) {
            $allStations += $items
            $tc = $r.response.body.totalCount
            if ($tc) { $totalCount = [int]$tc }
            Write-Host "  페이지 $page 수집: $($items.Count)건 (누적 $($allStations.Count) / 전체 $totalCount)"
        } else { break }
        $page++
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red; break
    }
} while ($allStations.Count -lt $totalCount)

# CSV 저장
$allStations | Select-Object statId, statNm, addr, lat, lng, chgerId, chgerType, useTime, busiNm, parkingFree, stat, statUpdDt |
    Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
Write-Host "  저장 완료: $csvPath ($($allStations.Count)건)" -ForegroundColor Green


# ── 2. 충전기 실시간 상태 (대구) ───────────────────────────────
Write-Host "`n=== 충전기 실시간 상태 수집 중 ===" -ForegroundColor Cyan
$params2 = @{ serviceKey = $key; numOfRows = "999"; pageNo = "1"; zcode = "27"; period = "10" }
try {
    $r2 = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus" -Body $params2 -TimeoutSec 90)
    $statusItems = $r2.response.body.items.item
    $csvPath2 = Join-Path $outputDir "daegu_charger_status_$timestamp.csv"
    $statusItems | Select-Object statId, statNm, chgerId, stat, statUpdDt |
        Export-Csv -Path $csvPath2 -NoTypeInformation -Encoding UTF8
    Write-Host "  저장 완료: $csvPath2 ($($statusItems.Count)건)" -ForegroundColor Green
    Write-Host "`n  [상태코드] 2=충전대기 3=충전중 4=운영중단 5=점검중 9=통신이상"
    $statusItems | Group-Object stat | Select-Object Name, Count | Format-Table -AutoSize
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n완료! 저장 위치: $outputDir" -ForegroundColor Yellow

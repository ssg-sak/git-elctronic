[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$key = "84412dc666fd5ec20910e654b4ca33c9a35dd3bd77f0b36d0c7e74b6be753554"

Write-Host "=== 충전소 API (zcode 없이, 90초 타임아웃) ===" -ForegroundColor Cyan
try {
    $params = @{
        serviceKey = $key
        numOfRows  = "1"
        pageNo     = "1"
    }
    $r = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo" -Body $params -TimeoutSec 90)
    Write-Host "code: $($r.response.header.resultCode) / $($r.response.header.resultMsg)" -ForegroundColor Green
    $r.response.body.items.item | Select-Object statNm, addr, stat, statUpdDt | Format-List
} catch {
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== 충전소 상태 API ===" -ForegroundColor Cyan
try {
    $params2 = @{
        serviceKey = $key
        numOfRows  = "1"
        pageNo     = "1"
        zcode      = "27"
        period     = "10"
    }
    $r2 = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus" -Body $params2 -TimeoutSec 90)
    Write-Host "code: $($r2.response.header.resultCode) / $($r2.response.header.resultMsg)" -ForegroundColor Green
    $r2.response.body.items.item | Select-Object statNm, chgerId, stat, statUpdDt | Format-List
} catch {
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

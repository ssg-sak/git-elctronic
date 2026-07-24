[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$key = (Get-Content (Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ".env") -Encoding UTF8 |
    Select-String "^DATA_GO_KR_KEY=" |
    Select-Object -First 1).Line.Split("=")[1]

Write-Host "key: $($key.Substring(0,8))..."

try {
    $url = "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo?serviceKey=$key&pageNo=1&numOfRows=5&zcode=27"
    $r = [xml](Invoke-RestMethod -Uri $url -TimeoutSec 30)
    Write-Host "code: $($r.response.header.resultCode) / $($r.response.header.resultMsg)"
    if ($r.response.header.resultCode -eq "00") {
        Write-Host "`n=== 대구 충전소 목록 ===" -ForegroundColor Green
        $r.response.body.items.item | Select-Object statNm, addr, stat, statUpdDt | Format-List
    }
} catch {
    Write-Host "오류: $($_.Exception.Message)" -ForegroundColor Red
}

# KOTSA 주차정보 API 프로브 스크립트
# .env 파일에서 DATA_GO_KR_KEY 로드
$envPath = Join-Path (Get-Location) "../../.env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*DATA_GO_KR_KEY\s*=\s*(.*)\s*$') {
            $env:DATA_GO_KR_KEY = $matches[1]
        }
    }
}

if (-not $env:DATA_GO_KR_KEY) {
    Write-Host "Error: DATA_GO_KR_KEY not found in .env file." -ForegroundColor Red
    exit 1
}

$decodedKey = $env:DATA_GO_KR_KEY

# KOTSA 주차 시설 정보 엔드포인트
# http://apis.data.go.kr/B553881/Parking/PrkSttusInfo
$baseUrl = "http://apis.data.go.kr/B553881/Parking/PrkSttusInfo"
$pageNo = 1
$numOfRows = 100

# PowerShell 7+ 에서는 Uri 구성시 자동 인코딩 문제가 발생할 수 있으므로 쿼리스트링 조합 사용
$url = "$baseUrl?serviceKey=$($env:DATA_GO_KR_KEY)&pageNo=$pageNo&numOfRows=$numOfRows&_type=json"

Write-Host "Fetching KOTSA Parking data (First $numOfRows rows)..."
Write-Host "URL: $baseUrl"

try {
    # JSON 응답 요청
    $response = Invoke-RestMethod -Uri $url -Method Get
    
    if ($response.response.header.resultCode -eq "00") {
        Write-Host "Success! Found $($response.response.body.totalCount) total parking lots." -ForegroundColor Green
        
        # 샘플 출력 (첫 3개)
        $items = $response.response.body.items.item
        $items | Select-Object -First 3 | Format-List prk_center_id, prk_plce_nm, prk_plce_entrc_la, prk_plce_entrc_lo, prk_plce_adres
        
        # 대구광역시 필터링 테스트
        $daeguItems = $items | Where-Object { $_.prk_plce_adres -match "대구" }
        Write-Host "Found $($daeguItems.Count) parking lots in Daegu in this batch." -ForegroundColor Yellow
        if ($daeguItems.Count -gt 0) {
            $daeguItems | Select-Object -First 1 | Format-List prk_center_id, prk_plce_nm, prk_plce_adres
        }
    } else {
        Write-Host "API returned an error: $($response.response.header.resultMsg)" -ForegroundColor Red
    }
} catch {
    Write-Host "Failed to request API: $_" -ForegroundColor Red
}

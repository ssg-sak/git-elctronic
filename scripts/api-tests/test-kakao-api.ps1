# 카카오 로컬 API 테스트 스크립트 (카테고리 검색 / 키워드 검색)
# 사용법:
#   .\test-kakao-api.ps1                                   → 기본: SKT타워 충전소 반경 500m 카페(CE7) 검색
#   .\test-kakao-api.ps1 -Category FD6 -Radius 700         → 반경 700m 음식점 검색
#   .\test-kakao-api.ps1 -Keyword "전기차 충전소"            → 키워드 검색
#   .\test-kakao-api.ps1 -X 127.0276 -Y 37.4979 -Category CS2  → 다른 좌표(강남역) 주변 편의점 검색
# 결과: 콘솔에 요약 표 출력 + 전체 응답을 kakao-result.json 파일로 저장
#
# 카테고리 코드: CE7=카페 FD6=음식점 CS2=편의점 CT1=문화시설 AT4=관광명소
#               PO3=공공기관 PK6=주차장 HP8=병원 PM9=약국

param(
    [string]$Category = "CE7",
    [string]$Keyword = "",
    [double]$X = 126.98452047,   # 경도 (기본: 서울중구 SKT타워 전기차충전소)
    [double]$Y = 37.56656541,    # 위도
    [int]$Radius = 500
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$envFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ".env"
$restKey = (Get-Content $envFile | Where-Object { $_ -match "^KAKAO_REST_KEY=" }) -replace "^KAKAO_REST_KEY=", ""
if (-not $restKey) {
    Write-Error ".env 파일에 KAKAO_REST_KEY가 없습니다."
    exit 1
}

$headers = @{ Authorization = "KakaoAK $restKey" }

if ($Keyword) {
    # 키워드 검색
    $encoded = [System.Uri]::EscapeDataString($Keyword)
    $url = "https://dapi.kakao.com/v2/local/search/keyword.json" +
           "?query=$encoded&x=$X&y=$Y&radius=$Radius&sort=distance"
    Write-Host "`n[키워드 검색] '$Keyword' / 중심 ($Y, $X) / 반경 ${Radius}m" -ForegroundColor Cyan
}
else {
    # 카테고리 검색
    $url = "https://dapi.kakao.com/v2/local/search/category.json" +
           "?category_group_code=$Category&x=$X&y=$Y&radius=$Radius&sort=distance"
    Write-Host "`n[카테고리 검색] $Category / 중심 ($Y, $X) / 반경 ${Radius}m" -ForegroundColor Cyan
}

try {
    $resp = Invoke-RestMethod -Uri $url -Headers $headers

    Write-Host "총 검색 결과: $($resp.meta.total_count) 건 (표시: $($resp.documents.Count)건)`n" -ForegroundColor Green

    $resp.documents |
        Select-Object place_name,
                      @{ N = "카테고리"; E = { $_.category_group_name } },
                      @{ N = "거리(m)"; E = { $_.distance } },
                      @{ N = "주소"; E = { $_.road_address_name } },
                      @{ N = "전화"; E = { $_.phone } } |
        Format-Table -AutoSize

    $outFile = Join-Path $PSScriptRoot "kakao-result.json"
    $resp | ConvertTo-Json -Depth 10 | Out-File $outFile -Encoding utf8
    Write-Host "전체 응답 저장됨: $outFile" -ForegroundColor Yellow
}
catch {
    Write-Host "호출 실패: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "HTTP 상태: $([int]$_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

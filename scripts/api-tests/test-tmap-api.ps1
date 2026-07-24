# TMAP POI 검색 API 테스트 스크립트
# 사용법: .\test-tmap-api.ps1                → 기본 키워드("SK T타워")로 검색
#         .\test-tmap-api.ps1 -Keyword "강남역 충전소"  → 원하는 키워드로 검색
# 결과: 콘솔에 요약 표 출력 + 전체 응답을 tmap-result.json 파일로 저장

param(
    [string]$Keyword = "SK T타워"
)

# 콘솔 한글 깨짐 방지
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

$encodedKeyword = [System.Uri]::EscapeDataString($Keyword)
$url = "https://apis.openapi.sk.com/tmap/pois" +
       "?version=1&searchKeyword=$encodedKeyword&page=1&searchType=all&count=20" +
       "&resCoordType=WGS84GEO&multiPoint=N&searchtypCd=A&reqCoordType=WGS84GEO&poiGroupYn=N"

Write-Host "`n검색 키워드: $Keyword" -ForegroundColor Cyan

try {
    $resp = Invoke-RestMethod -Uri $url -Headers @{ accept = "application/json"; appkey = $appKey }

    $total = $resp.searchPoiInfo.totalCount
    Write-Host "총 검색 결과: $total 건`n" -ForegroundColor Green

    $resp.searchPoiInfo.pois.poi |
        Select-Object name,
                      @{ N = "주소"; E = { "$($_.upperAddrName) $($_.middleAddrName) $($_.lowerAddrName)" } },
                      @{ N = "위도"; E = { $_.frontLat } },
                      @{ N = "경도"; E = { $_.frontLon } },
                      @{ N = "전화"; E = { $_.telNo } } |
        Format-Table -AutoSize

    # 전체 응답을 JSON 파일로 저장 (에디터에서 열어서 확인 가능)
    $outFile = Join-Path $PSScriptRoot "tmap-result.json"
    $resp | ConvertTo-Json -Depth 10 | Out-File $outFile -Encoding utf8
    Write-Host "전체 응답 저장됨: $outFile" -ForegroundColor Yellow
}
catch {
    Write-Host "호출 실패: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "HTTP 상태: $([int]$_.Exception.Response.StatusCode)" -ForegroundColor Red
    }
}

# EV SafeCharge — 전체 API 통합 검증 스크립트
# 사용법: .\test-all-apis.ps1
# 발급된 모든 API를 순서대로 호출해 PASS / FAIL 요약을 출력한다.

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$envFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ".env"
$envMap = @{}
Get-Content $envFile | Where-Object { $_ -match "^\s*([A-Z_]+)\s*=\s*(.+)$" } | ForEach-Object {
    $envMap[$Matches[1]] = $Matches[2].Trim()
}
$dataKey    = $envMap["DATA_GO_KR_KEY"]
$tmapKey    = $envMap["TMAP_APP_KEY"]
$kakaoKey   = $envMap["KAKAO_REST_KEY"]
$prkKey     = $envMap["DAEGU_PARKING_KEY"]
$prkRtKey   = $envMap["DAEGU_PARKING_RT_KEY"]

$results = @()

function Test-Api {
    param(
        [string]$Name,
        [scriptblock]$Call,   # 응답 객체 반환
        [scriptblock]$Check   # 응답 받아 $true/$false 반환
    )
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    $status = "FAIL"; $detail = ""
    # 공공 API가 간헐적으로 504를 반환하므로 1회 재시도
    foreach ($attempt in 1..2) {
        try {
            $resp = & $Call
            if (& $Check $resp) { $status = "PASS"; $detail = "" } else { $detail = "응답은 왔으나 형식이 예상과 다름" }
            break
        }
        catch {
            $detail = $_.Exception.Message
            if ($attempt -eq 1) { Write-Host "  1차 실패, 재시도..." -ForegroundColor DarkYellow; Start-Sleep -Seconds 3 }
        }
    }
    $color = if ($status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "  [$status] $detail" -ForegroundColor $color
    $script:results += [PSCustomObject]@{ API = $Name; 결과 = $status; 비고 = $detail }
}

# 대구 중심 좌표 (동성로 인근)
$daeguX = 128.6014; $daeguY = 35.8714

# ── 1. 한국환경공단 충전소 정보 ─────────────────────────────
Test-Api -Name "한국환경공단 충전소 정보 (getChargerInfo)" -Call {
    [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo?serviceKey=$dataKey&pageNo=1&numOfRows=3&zcode=27" -TimeoutSec 90)
} -Check { param($r) $r.response.header.resultCode -eq "00" }

# ── 2. 한국환경공단 충전기 상태 ─────────────────────────────
Test-Api -Name "한국환경공단 충전기 상태 (getChargerStatus)" -Call {
    [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerStatus?serviceKey=$dataKey&pageNo=1&numOfRows=3&zcode=27&period=10" -TimeoutSec 90)
} -Check { param($r) $r.response.header.resultCode -eq "00" }

# ── 3. 기상청 초단기실황 ───────────────────────────────────
# 대구 nx=89, ny=90. 실황은 매시 40분경 생성되므로 직전 정시 기준으로 조회
$base = (Get-Date).AddMinutes(-50)
$baseDate = $base.ToString("yyyyMMdd"); $baseTime = $base.ToString("HH") + "00"
Test-Api -Name "기상청 초단기실황 (getUltraSrtNcst, 대구)" -Call {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst?serviceKey=$dataKey&pageNo=1&numOfRows=10&dataType=JSON&base_date=$baseDate&base_time=$baseTime&nx=89&ny=90" -TimeoutSec 60
} -Check { param($r) $r.response.header.resultCode -eq "00" }

# ── 4. 대구 교통소통정보(신) ───────────────────────────────
# 주의: 2026-07-15 현재 게이트웨이는 정상이나 대구시 원본 서버(ATMS)가 404 반환 중 (제공기관 측 장애로 추정)
Test-Api -Name "대구 교통소통정보(신) (linkspeed)" -Call {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest1/linkspeed?serviceKey=$dataKey&pageNo=1&numOfRows=3" -TimeoutSec 60
} -Check { param($r)
    if ($r -is [xml]) { $r.response.header.resultCode -eq "00" } else { "$($r.header.resultCode)$($r.response.header.resultCode)" -match "00" }
}

# ── 5. 대구 돌발 교통정보(신) ──────────────────────────────
# 주의: 위와 동일하게 원본 서버 404 반환 중
Test-Api -Name "대구 돌발 교통정보(신) (dgincident)" -Call {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/service/rest/dgincident?serviceKey=$dataKey&pageNo=1&numOfRows=3" -TimeoutSec 60
} -Check { param($r)
    if ($r -is [xml]) { $r.response.header.resultCode -eq "00" } else { "$($r.header.resultCode)$($r.response.header.resultCode)" -match "00" }
}

# ── 6. 한국관광공사 TourAPI (KorService2, 위치기반) ─────────
Test-Api -Name "한국관광공사 TourAPI (locationBasedList2, 대구)" -Call {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/B551011/KorService2/locationBasedList2?serviceKey=$dataKey&MobileOS=ETC&MobileApp=EVSafeCharge&_type=json&mapX=$daeguX&mapY=$daeguY&radius=3000&numOfRows=3&pageNo=1&contentTypeId=12" -TimeoutSec 60
} -Check { param($r) $r.response.header.resultCode -eq "0000" }

# ── 7. 대구 관광지 ─────────────────────────────────────────
Test-Api -Name "대구 관광지 (getTourKorAttractList)" -Call {
    [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList?serviceKey=$dataKey&pageNo=1&numOfRows=3" -TimeoutSec 60)
} -Check { param($r) $r.response.header.resultCode -eq "00" }

# ── 8. 대구 산책로정보 ─────────────────────────────────────
# 좌표 파라미터는 lat/lot, 반경은 km 단위, type으로 응답 포맷 지정
Test-Api -Name "대구 산책로정보 (getDgWalkParkList)" -Call {
    Invoke-RestMethod -Uri "https://apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList?serviceKey=$dataKey&pageNo=1&numOfRows=3&type=json&lat=$daeguY&lot=$daeguX&radius=5" -TimeoutSec 60
} -Check { param($r) $r.header.resultCode -eq "00" }

# ── 9. TMAP POI 검색 ───────────────────────────────────────
Test-Api -Name "TMAP POI 검색 (pois)" -Call {
    Invoke-RestMethod -Uri "https://apis.openapi.sk.com/tmap/pois?version=1&searchKeyword=%EC%A0%84%EA%B8%B0%EC%B0%A8%20%EC%B6%A9%EC%A0%84%EC%86%8C&page=1&searchType=all&count=3&resCoordType=WGS84GEO&reqCoordType=WGS84GEO&centerLon=$daeguX&centerLat=$daeguY" -Headers @{ appkey = $tmapKey; accept = "application/json" } -TimeoutSec 60
} -Check { param($r) [int]$r.searchPoiInfo.totalCount -gt 0 }

# ── 10. TMAP 자동차 경로 ───────────────────────────────────
Test-Api -Name "TMAP 자동차 경로 (routes)" -Call {
    $body = @{ startX = "$daeguX"; startY = "$daeguY"; endX = "128.6250"; endY = "35.8850"; reqCoordType = "WGS84GEO"; resCoordType = "WGS84GEO"; searchOption = "0"; trafficInfo = "Y" } | ConvertTo-Json
    Invoke-RestMethod -Uri "https://apis.openapi.sk.com/tmap/routes?version=1" -Method Post -Headers @{ appKey = $tmapKey; accept = "application/json" } -ContentType "application/json" -Body $body -TimeoutSec 60
} -Check { param($r) [int]$r.features[0].properties.totalTime -gt 0 }

# ── 11. 카카오 로컬 카테고리 검색 ──────────────────────────
Test-Api -Name "카카오 로컬 카테고리 검색 (CE7 카페)" -Call {
    Invoke-RestMethod -Uri "https://dapi.kakao.com/v2/local/search/category.json?category_group_code=CE7&x=$daeguX&y=$daeguY&radius=500&sort=distance" -Headers @{ Authorization = "KakaoAK $kakaoKey" } -TimeoutSec 60
} -Check { param($r) [int]$r.meta.total_count -gt 0 }

# ── 12. 대구 주차장 기본정보 ───────────────────────────────
# 주의: 접속 IP 제한 — 등록된 팀 AWS 서버(3.39.251.72)에서만 호출 가능.
#       로컬 PC에서 실행하면 401(권한 없음)이 뜨는 것이 정상이다.
Test-Api -Name "대구 주차장 기본정보 (prkInfo)" -Call {
    Invoke-RestMethod -Uri "https://pis.daegu.go.kr/api/serviceApply/prkInfo?numOfRows=3&pageNo=1" -Headers @{ Authentication = $prkKey; accept = "application/json;charset=UTF-8" } -TimeoutSec 60
} -Check { param($r) "$($r | ConvertTo-Json -Depth 3 -Compress)" -match "pklt|resultCode|items" }

# ── 13. 대구 실시간 주차 혼잡도 ────────────────────────────
Test-Api -Name "대구 실시간 주차 혼잡도 (rltmPrkInfo)" -Call {
    Invoke-RestMethod -Uri "https://pis.daegu.go.kr/api/serviceApply/rltmPrkInfo?numOfRows=3&pageNo=1" -Headers @{ Authentication = $prkRtKey; accept = "application/json;charset=UTF-8" } -TimeoutSec 60
} -Check { param($r) "$($r | ConvertTo-Json -Depth 3 -Compress)" -match "pklt|prkCnf|resultCode|items" }

# ── 결과 요약 ──────────────────────────────────────────────
Write-Host "`n`n══════════════ 검증 결과 요약 ══════════════" -ForegroundColor Yellow
$results | Format-Table -AutoSize
$pass = ($results | Where-Object 결과 -eq "PASS").Count
Write-Host "$pass / $($results.Count) 통과" -ForegroundColor $(if ($pass -eq $results.Count) { "Green" } else { "Yellow" })

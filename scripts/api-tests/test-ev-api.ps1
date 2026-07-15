# 한국환경공단 전기자동차 충전소 API 테스트 스크립트
# 사용법: .\test-ev-api.ps1  (인증키는 .env 파일의 DATA_GO_KR_KEY에서 읽음)

$envFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ".env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env 파일이 없습니다. EV_API_KEY=<인증키> 형식으로 만들어 주세요."
    exit 1
}
$serviceKey = (Get-Content $envFile | Where-Object { $_ -match "^DATA_GO_KR_KEY=" }) -replace "^DATA_GO_KR_KEY=", ""
if (-not $serviceKey) {
    Write-Error ".env 파일에 DATA_GO_KR_KEY가 없습니다."
    exit 1
}

$base = "https://apis.data.go.kr/B552584/EvCharger"

function Invoke-EvApi {
    param([string]$Operation, [hashtable]$Params)

    $query = ($Params.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "&"
    $url = "$base/$Operation`?serviceKey=$serviceKey&$query"

    Write-Host "`n=== $Operation ===" -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri $url -Method Get
        # 응답이 XML이면 resultCode/resultMsg 확인
        if ($resp -is [xml]) {
            $header = $resp.response.header
            Write-Host "resultCode: $($header.resultCode)  resultMsg: $($header.resultMsg)"
            Write-Host "totalCount: $($resp.response.body.totalCount)"
            $resp.response.body.items.item | Select-Object -First 5 statNm, addr, chgerType, stat, statUpdDt | Format-Table -AutoSize
        }
        else {
            Write-Host $resp
        }
    }
    catch {
        Write-Host "호출 실패: $($_.Exception.Message)" -ForegroundColor Red
        if ($_.Exception.Response) {
            Write-Host "HTTP 상태: $([int]$_.Exception.Response.StatusCode)" -ForegroundColor Red
        }
    }
}

# 1. 충전소 정보 조회 (서울: zcode=11)
Invoke-EvApi -Operation "getChargerInfo" -Params @{ pageNo = 1; numOfRows = 5; zcode = 11 }

# 2. 충전기 상태 조회 (최근 5분 내 변경분)
Invoke-EvApi -Operation "getChargerStatus" -Params @{ pageNo = 1; numOfRows = 5; zcode = 11; period = 5 }

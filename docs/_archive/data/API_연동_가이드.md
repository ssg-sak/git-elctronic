# 공공데이터포털 API 연동 학습 가이드

**대상**: EV SafeCharge 데이터 파이프라인 팀원  
**목적**: 공공데이터포털 API를 처음 연동하는 팀원이 막힘 없이 셋업할 수 있도록 정리

---

## 1. 공공데이터포털(data.go.kr) 핵심 개념

### 인증키는 계정당 1개, 모든 API 공통

가장 많이 헷갈리는 부분입니다.

> **data.go.kr에서 발급되는 인증키는 계정당 단 1개**이며, 이 키 하나로 활용신청이 완료된 **모든 API**를 호출할 수 있습니다.

- 기상청 API 페이지에서 보이는 키 = 환경공단 API 페이지에서 보이는 키 → **동일한 키**
- 각 API마다 별도로 **활용신청(승인)**은 해야 하지만, 키 자체는 하나

```
공공데이터포털 계정
    └── 인증키 (1개, DATA_GO_KR_KEY)
            ├── 환경공단 충전소 API (활용신청 완료 시 사용 가능)
            ├── 기상청 단기예보 API (활용신청 완료 시 사용 가능)
            ├── 한국관광공사 TourAPI (활용신청 완료 시 사용 가능)
            └── ...
```

### Encoding 키 vs Decoding 키

마이페이지에서 키를 두 가지로 제공합니다:

| 종류 | 형태 | 사용 시점 |
|---|---|---|
| 일반 인증키 (Encoding) | `%2B`, `%2F` 등 URL 인코딩 포함 | URL에 직접 붙여 넣을 때 |
| 일반 인증키 (Decoding) | 원본 문자열 | `requests`, `Invoke-RestMethod` 파라미터로 전달할 때 |

> 파이썬 `requests` 라이브러리나 PowerShell `Invoke-RestMethod`의 `-Body` 파라미터 방식으로 호출할 때는 **Decoding 키**를 사용합니다.

### 신규 키 동기화 지연

- 발급 직후 최대 **1시간** 동안 401 또는 타임아웃이 발생할 수 있음
- `403 Forbidden` or `401 Unauthorized` → 키 동기화 지연 먼저 의심
- 1시간 후에도 동일하면: 활용신청 승인 여부 확인

---

## 2. 환경 설정

### .env 파일 구조

```bash
# git-elctronic/.env (커밋 금지!)

DATA_GO_KR_KEY=<마이페이지 > 개발계정 > 일반 인증키(Decoding)>

TMAP_APP_KEY=<https://openapi.sk.com/ 에서 앱 생성 후 App Key>
KAKAO_REST_KEY=<https://developers.kakao.com/ 에서 애플리케이션 등록 후 REST API 키>

DAEGU_PARKING_KEY=<pis.daegu.go.kr 에서 발급, AWS 서버 전용>
DAEGU_PARKING_RT_KEY=<pis.daegu.go.kr 에서 발급, AWS 서버 전용>
```

### 키 확인 위치

```
https://www.data.go.kr
  → 로그인
  → 마이페이지
  → 오픈API
  → 개발계정
  → 목록에서 아무 API 클릭
  → "일반 인증키 (Decoding)" 복사
```

---

## 3. API 호출 방법

### PowerShell (스크립트 파일 내)

```powershell
# ✅ -Body 해시테이블 방식 권장 (& 파싱 문제 없음)
$key = "발급받은_키"
$params = @{
    serviceKey = $key
    pageNo     = "1"
    numOfRows  = "10"
    zcode      = "27"   # 대구광역시
}
$r = [xml](Invoke-RestMethod -Uri "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo" -Body $params -TimeoutSec 90)
Write-Host $r.response.header.resultCode   # 00 = 정상
```

> [!WARNING]
> PowerShell `-Command` 인라인에서 URL에 `&`를 직접 쓰면 파싱 오류가 납니다.  
> **반드시 `.ps1` 파일로 작성하거나 `-Body` 해시테이블을 사용**하세요.

### Python (requests 라이브러리)

```python
import requests

KEY = "발급받은_키"

params = {
    "serviceKey": KEY,
    "pageNo": 1,
    "numOfRows": 10,
    "zcode": "27",  # 대구
}
resp = requests.get(
    "https://apis.data.go.kr/B552584/EvCharger/getChargerInfo",
    params=params,
    timeout=60,
)
resp.raise_for_status()
# XML 파싱
import xml.etree.ElementTree as ET
root = ET.fromstring(resp.content)
print(root.findtext(".//resultCode"))   # 00 = 정상
```

---

## 4. 주요 API 레퍼런스

### 한국환경공단 EvCharger

| 오퍼레이션 | URL | 설명 |
|---|---|---|
| `getChargerInfo` | `/B552584/EvCharger/getChargerInfo` | 충전소/충전기 정적 정보 |
| `getChargerStatus` | `/B552584/EvCharger/getChargerStatus` | 실시간 충전기 상태 |

**주요 파라미터**

| 파라미터 | 설명 | 예시 |
|---|---|---|
| `zcode` | 시도 코드 (행정구역 앞 2자리) | `27` (대구) |
| `period` | 최근 N분 변경분만 조회 (getChargerStatus 전용) | `10` |
| `numOfRows` | 페이지당 건수 | `999` |
| `pageNo` | 페이지 번호 | `1` |

**stat 상태 코드**

| 코드 | 의미 |
|---|---|
| `2` | 충전 대기 (사용 가능) |
| `3` | 충전 중 |
| `4` | 운영 중단 |
| `5` | 점검 중 |
| `9` | 통신 이상 |

### 기상청 단기예보

- 대구 격자좌표: **nx=89, ny=90**
- 위도/경도가 아닌 기상청 전용 격자좌표 사용 (약 5km 격자)
- 초단기실황: 매시 40분 이후 발표 → `base_time`을 직전 정시(`HH00`)로 맞출 것

---

## 5. 검증 스크립트 사용법

```powershell
# git-elctronic/ 폴더에서 실행

# 전체 API 통합 검증 (PASS/FAIL 요약)
powershell -ExecutionPolicy Bypass -File scripts/api-tests/test-all-apis.ps1

# 기상청 + 환경공단 키 빠른 검증
powershell -ExecutionPolicy Bypass -File scripts/api-tests/key-check.ps1

# 대구 충전소 데이터 CSV 추출
powershell -ExecutionPolicy Bypass -File scripts/api-tests/extract-daegu-data.ps1
```

---

## 6. 자주 발생하는 오류

| 오류 | 원인 | 해결 |
|---|---|---|
| `401 Unauthorized` | 키 동기화 지연 또는 활용신청 미완료 | 1시간 대기 후 재시도, 또는 마이페이지에서 승인 여부 확인 |
| `403 Forbidden` | 동일 | 동일 |
| `타임아웃 (30초+)` | 키 동기화 진행 중 게이트웨이 대기 | 1시간 대기 |
| `원본 서버 404` | 제공기관(대구시 등) 서버 장애 | 우리 문제 아님, 일시 대기 후 재확인 |
| `& 파싱 오류` | PowerShell 인라인 `-Command`에서 `&` 사용 | `.ps1` 파일 or `-Body` 해시테이블 사용 |
| `일 트래픽 초과` | EvCharger 기준 1,000건/일 | `period`, `zcode` 파라미터로 최소화 |

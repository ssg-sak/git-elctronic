# 카카오 로컬 API 메모

인증키는 `.env`의 `KAKAO_REST_KEY` 사용. 요청 헤더: `Authorization: KakaoAK {REST_KEY}`

## 호출 주소

- 카테고리 검색: `https://dapi.kakao.com/v2/local/search/category.json`
- 키워드 검색: `https://dapi.kakao.com/v2/local/search/keyword.json`

## 사용할 카테고리 코드

| 코드 | 분류 |
|---|---|
| CE7 | 카페 |
| FD6 | 음식점 |
| CS2 | 편의점 |
| CT1 | 문화시설 |
| AT4 | 관광명소 |
| PO3 | 공공기관 |
| PK6 | 주차장 |
| HP8 | 병원 |
| PM9 | 약국 |

## 요청 예시

```
GET https://dapi.kakao.com/v2/local/search/category.json
    ?category_group_code=CE7
    &x=128.6014
    &y=35.8714
    &radius=500
    &sort=distance
```

## 프로젝트 활용 계획

- 충전소 반경 500m 카페 검색
- 충전소 반경 700m 음식점 검색
- 충전소 주변 편의점·병원·공공기관 검색
- 도보 거리순으로 정렬

테스트는 `test-kakao-api.ps1` 참고.

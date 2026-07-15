# 기여 가이드

## 팀 구성과 담당 디렉터리

| 역할 | 담당 디렉터리 | 가이드 |
|---|---|---|
| 프론트엔드 | `apps/web/` | `apps/web/AGENTS.md` |
| 백엔드 | `apps/api/`, `packages/recommendation-core/` | `apps/api/AGENTS.md` |
| 데이터 수집 | `apps/data-pipeline/collection/` | `apps/data-pipeline/AGENTS.md` |
| 데이터 가공 | `apps/data-pipeline/processing/` | `apps/data-pipeline/AGENTS.md` |

자신의 담당 디렉터리 밖의 코드는 수정하지 않습니다. 다른 영역 변경이 필요하면 담당자와 합의 후 진행합니다.
`packages/shared-types/`는 공용이므로 변경 시 PR에서 프론트·백엔드 모두의 리뷰를 받습니다.

## 브랜치 전략

```
main (배포) ← dev (통합) ← feat/<영역>-<기능>
```

- 예: `feat/web-map-view`, `feat/api-recommendation`, `feat/data-collector-scheduler`
- `main`, `dev`에 직접 푸시 금지. 반드시 PR을 통해 병합합니다.

## 커밋 메시지

`[영역] 내용` 형식을 사용합니다.

- `[web] 지도 마커 위험도별 색상 적용`
- `[api] 추천 점수 계산 라우트 추가`
- `[data] 충전기 상태 수집 스케줄러 작성`
- `[docs] API 명세 갱신`

## PR 규칙

- PR 템플릿(`.github/pull_request_template.md`)을 채워서 제출합니다.
- 영역 간 인터페이스(API 명세, DB 스키마, 공용 타입) 변경은 본문에 **Breaking Change** 섹션으로 명시합니다.
- CI 통과 후 담당 영역 리뷰어 1인 이상의 승인으로 병합합니다.

## 보안 규칙

- `.env`, 인증키, 수집 원본 대용량 데이터는 절대 커밋하지 않습니다. (`.env.example`만 갱신)
- 외부 API 키는 백엔드(Express) 환경변수에만 둡니다. 프론트엔드 코드·`NEXT_PUBLIC_` 변수에 노출 금지.

## 도메인 규칙

추천 점수 가중치, 신뢰도 등급 기준 등 전 영역 공통 규칙은 루트 `AGENTS.md`를 따릅니다. 임의 변경 금지.

# experiments/ — 실험 노트 폴더 (AI·데이터 ①)

**여기에는 마크다운 실험 기록만 둔다.**  
CSV·DB·차트 바이너리 같은 **실데이터 파일은 넣지 않는다.**  
**점수·추천 이유·ML 실험은 두지 않는다** (AI·데이터 ②).

## 실험 원칙 (중요)

> **실험할 때는 확보된 데이터를 전부 고려한다.**  
> 충전·상태·기상·Tour·대구시 관광·산책·주차 mock·교통 mock 등을  
> 한 실험에서 빠뜨리지 않는다.  
> 미확보·API 장애분은 mock 또는 “해당 피처 N/A”로 **명시**한다.

품질 이슈 상세: [`NOTE_20260716_전소스_데이터품질이슈.md`](./NOTE_20260716_전소스_데이터품질이슈.md)

| 문서 | 경로 |
|---|---|
| 전처리 실험 보고서 | [`EXP-004_...`](./EXP-004_20260716_전소스전처리_실험보고서.md) |
| 전처리 학습서 | [`SANDBOX_.../reports/LEARNING_GUIDE_전소스전처리.md`](./SANDBOX_20260716_preprocess_pipeline/reports/LEARNING_GUIDE_전소스전처리.md) |
| 전처리 SANDBOX | [`SANDBOX_20260716_preprocess_pipeline/`](./SANDBOX_20260716_preprocess_pipeline/) |
| status 수집 SANDBOX | [`SANDBOX_20260717_status_periodic_collection/`](./SANDBOX_20260717_status_periodic_collection/) |

| 종류 | 위치 |
|---|---|
| 실험 계획·결과 노트 | `EXP-*.md` |
| 실험 템플릿 | `_TEMPLATE.md` |
| 로드맵 | [`_PHASES.md`](./_PHASES.md) |
| 실데이터 확장 (대기) | [`phase2_realdata/`](./phase2_realdata/) |
| 품질 비교 (대기) | [`compare_1vs2/`](./compare_1vs2/) |
| 추출 CSV | `docs/data/extracted/` |
| 개인 실험 목록 | `../SSG-SAK_이현석_실험노트.md` |

## 새 실험 추가

1. `_TEMPLATE.md` 복사 → `EXP-00N_YYYYMMDD_제목.md`
2. 입력 섹션에 **전 데이터 소스** 표기 (실 / mock / 미확보)
3. `SSG-SAK_이현석_실험노트.md` 표에 한 줄 추가
4. 주제는 정의·품질·전처리·공간결합·EDA·특성·데이터셋·status 수집만

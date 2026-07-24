# SANDBOX_20260716_preprocess_pipeline

**격리된 전처리 실험 샌드박스 (필수 보관).**  
원본 CSV는 `docs/data/extracted/` 를 **읽기만** 한다. 덮어쓰지 않는다.

> **범위**: 전처리·품질만. 점수·추천 이유·ML은 AI·데이터 ② 영역이며 이 SANDBOX에 두지 않는다.

## 문서 (보고·학습)

| 문서 | 설명 |
|---|---|
| [`../../EXP-004_20260716_전소스전처리_실험보고서.md`](../../EXP-004_20260716_전소스전처리_실험보고서.md) | 전처리 실험 보고서 |
| [`reports/LEARNING_GUIDE_전소스전처리.md`](./reports/LEARNING_GUIDE_전소스전처리.md) | 전처리 학습서 |
| [`reports/data_quality/EXECUTIVE_SUMMARY.md`](./reports/data_quality/EXECUTIVE_SUMMARY.md) | 실행 결과 요약 |
| [`reports/data_quality/data_quality_report.md`](./reports/data_quality/data_quality_report.md) | 품질 상세 |
| [`reports/data_quality/missing_value_policy.md`](./reports/data_quality/missing_value_policy.md) | 결측 정책 |

```
SANDBOX_20260716_preprocess_pipeline/
├── README.md
├── data/{raw,interim,processed,quarantine}/
├── reports/
├── src/preprocessing/
└── tests/
```

## 실행

```bash
cd git-elctronic
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline/src/preprocessing/run_pipeline.py
python -m pytest apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline/tests -v
```

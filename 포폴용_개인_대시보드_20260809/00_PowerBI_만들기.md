# 포폴용 대시보드 — DA① 20260809 (**전달 아님**)

| | |
|---|---|
| **폴더** | `포폴용_개인_대시보드_20260809/` |
| **용도** | 개인 포트폴리오만 |
| **팀/최종본** | **포함·전달하지 말 것** |
| **바로 보기** | `DA1_대시보드_20260809.xlsx` · `대시보드_바로보기.html` |
| **데이터** | `data/*.csv` |
| **점수** | 만들지 말 것 (②) |
| **현재표 as_of** | 2026-08-09T07:23:21+09:00 |

## 바로 열기

- repo: `포폴용_개인_대시보드_20260809/`
- 바탕화면: `Desktop\포폴용_개인_대시보드_20260809\`

시트(Excel): 시간대 / 요일 / 신선도 / 충전기대수 / 피처LOO / KPI / 최종피처 / 과적합

## Power BI Desktop (선택)

1. 데이터 가져오기 → 텍스트/CSV 또는 폴더  
2. 이 폴더의 `data/` 가져오기  

필수 CSV: `dim_meta`, `fact_kpi`, `fact_eda_*`, `fact_loo_deltas`, `dim_final_features`, `fact_overfit_*`, `fact_snapshot_stations`

## 재생성

```
python apps/data-pipeline/processing/tools/share/build_powerbi_pack_20260809.py
python apps/data-pipeline/processing/tools/share/build_excel_dashboard_20260809.py
python apps/data-pipeline/processing/tools/share/build_html_dashboard_20260809.py
```

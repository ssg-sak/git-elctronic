# 포폴용 · 개인 대시보드 (전달 아님)

| | |
|---|---|
| **용도** | 개인 포트폴리오 / 시각화 연습 |
| **팀 전달** | **하지 않음** — 조장·DA②·최종본과 무관 |
| **최종본** | `최종본_20260809/` 에 포함하지 않음 |

## 바로 보기

1. `DA1_대시보드_20260809.xlsx` — Excel 차트 대시보드  
2. `대시보드_바로보기.html` — 브라우저 원클릭  
3. `data/*.csv` — Power BI Desktop 가져오기용 (선택)

바탕화면 복사본: `Desktop\포폴용_개인_대시보드_20260809\`

## 재생성 (로컬만)

```
python apps/data-pipeline/processing/tools/share/build_powerbi_pack_20260809.py
python apps/data-pipeline/processing/tools/share/build_excel_dashboard_20260809.py
python apps/data-pipeline/processing/tools/share/build_html_dashboard_20260809.py
```

점수·추천 로직은 넣지 않음 (② 영역).

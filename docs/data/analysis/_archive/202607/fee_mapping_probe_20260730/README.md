# 요금 원천 프로브 (2026-07-30)

## 결론
- **CHA ON 요금 CSV**: 충전소 **1곳**(한전KDN 본사) 세션 요금 → 대구 D1 매핑 **불가**
- **한전 계시별 단가**: 요금제별 kWh 단가 표 → **백엔드 단가 레퍼런스**로 적합 (statId 직접 조인 아님)

- 최신 단가표: `docs/data/extracted/fee/fee_tariff_ref_kepco_latest.csv`
- 요약: `docs/data/analysis/fee_mapping_probe_20260730/summary.json`

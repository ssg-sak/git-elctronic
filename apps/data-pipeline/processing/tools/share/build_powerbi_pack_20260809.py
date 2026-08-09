"""Build personal portfolio dashboard pack (NOT for team handoff).

Output: 포폴용_개인_대시보드_20260809/  — never copies into 최종본.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
STAMP = "20260809"
OUT = REPO / f"포폴용_개인_대시보드_{STAMP}"
DESK = Path.home() / "Desktop" / OUT.name
EDA = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "eda"
HGB = REPO / "docs" / "data" / "analysis" / "hgb_arrival_eta_fitness_20260808"
OVER = REPO / "docs" / "data" / "analysis" / "hgb_overfit_risk_20260808"
# prefer renamed copies in final pack if present
HGB_ALT = REPO / "최종본_20260809" / "04_HGB_피처_과적합" / "hgb_arrival_eta_fitness_20260809"
OVER_ALT = REPO / "최종본_20260809" / "04_HGB_피처_과적합" / "hgb_overfit_risk_20260809"
KPI_JSON = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "kpi_report_latest.json"
SNAP = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets" / "station_feature_snapshot_latest.csv"
IQR = REPO / "docs" / "data" / "analysis" / f"iqr_outlier_scan_{STAMP}"
VALID = REPO / "docs" / "data" / "analysis" / f"data_validity_assessment_{STAMP}"
INTEG = REPO / "docs" / "data" / "analysis" / f"integration_readiness_{STAMP}"


def _hgb() -> Path:
    return HGB_ALT if HGB_ALT.is_dir() else HGB


def _over() -> Path:
    return OVER_ALT if OVER_ALT.is_dir() else OVER


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    data = OUT / "data"
    data.mkdir(parents=True)

    meta = {
        "stamp": STAMP,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "as_of": "2026-08-09T07:23:21+09:00",
        "pull": "from_lightsail_20260809_072742",
        "role": "DA① Power BI import pack — no recommendation scores",
        "plain_names": {"현재표": "snapshot", "시간표": "panel"},
    }
    pd.DataFrame([meta]).to_csv(data / "dim_meta.csv", index=False, encoding="utf-8-sig")

    # --- EDA ---
    for src_name, out_name in [
        ("e1_availability_by_hour.csv", "fact_eda_hour.csv"),
        ("e2_availability_by_dow.csv", "fact_eda_dow.csv"),
        ("e3_availability_by_charger_count.csv", "fact_eda_charger_bucket.csv"),
        ("e4_availability_by_freshness.csv", "fact_eda_freshness.csv"),
        ("e4_availability_by_reliability_grade.csv", "fact_eda_reliability_grade.csv"),
    ]:
        src = EDA / src_name
        if src.is_file():
            df = pd.read_csv(src, encoding="utf-8-sig")
            df.to_csv(data / out_name, index=False, encoding="utf-8-sig")

    e5 = EDA / "e5_panel_quality.json"
    if e5.is_file():
        j = json.loads(e5.read_text(encoding="utf-8"))
        pd.DataFrame([j]).to_csv(data / "fact_eda_panel_quality.csv", index=False, encoding="utf-8-sig")

    # --- KPI ---
    if KPI_JSON.is_file():
        kj = json.loads(KPI_JSON.read_text(encoding="utf-8"))
        rows = []
        # flexible: checks list or flat
        if isinstance(kj.get("checks"), list):
            for c in kj["checks"]:
                rows.append(
                    {
                        "kpi_id": c.get("id") or c.get("code") or c.get("name"),
                        "name": c.get("name") or c.get("title") or c.get("code"),
                        "status": c.get("status") or c.get("verdict"),
                        "value": c.get("value") or c.get("current"),
                        "target": c.get("target") or c.get("goal"),
                    }
                )
        elif isinstance(kj.get("kpis"), list):
            for c in kj["kpis"]:
                rows.append(c)
        else:
            # flatten top-level scalars
            for k, v in kj.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    rows.append({"kpi_id": k, "name": k, "status": "", "value": v, "target": ""})
        if rows:
            pd.DataFrame(rows).to_csv(data / "fact_kpi.csv", index=False, encoding="utf-8-sig")
        # also raw json for reference
        (data / "kpi_report_latest.json").write_text(
            json.dumps(kj, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- HGB feature ---
    h = _hgb()
    for name, outn in [
        ("final_feature_decisions.csv", "fact_feature_decisions.csv"),
        ("loo_deltas.csv", "fact_loo_deltas.csv"),
        ("feature_ablation_metrics.csv", "fact_feature_ablation.csv"),
        ("feature_target_association.csv", "fact_feature_association.csv"),
        ("reliability_temporal_blocks.csv", "fact_reliability_blocks.csv"),
        ("reliability_seed_stability.csv", "fact_seed_stability.csv"),
    ]:
        src = h / name
        if src.is_file():
            pd.read_csv(src, encoding="utf-8-sig").to_csv(
                data / outn, index=False, encoding="utf-8-sig"
            )
    for jname, outn in [
        ("HANDOFF_SUMMARY.json", "fact_hgb_handoff.csv"),
        ("MODEL_FITNESS_COMPLETE.json", "fact_model_fitness.csv"),
        ("final_feature_selection.json", "fact_final_feature_selection.csv"),
    ]:
        jp = h / jname
        if jp.is_file():
            j = json.loads(jp.read_text(encoding="utf-8"))
            if isinstance(j, dict):
                # flatten one level
                flat = {}
                for k, v in j.items():
                    if isinstance(v, (dict, list)):
                        flat[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        flat[k] = v
                pd.DataFrame([flat]).to_csv(data / outn, index=False, encoding="utf-8-sig")

    # final 9 features dim
    dec = h / "final_feature_decisions.csv"
    if dec.is_file():
        d = pd.read_csv(dec, encoding="utf-8-sig")
        # keep RETAIN if column exists
        for col in ("decision", "verdict", "keep", "status"):
            if col in d.columns:
                retain = d[d[col].astype(str).str.upper().str.contains("RETAIN|KEEP|FINAL|Y")]
                if len(retain):
                    d = retain
                break
        d.to_csv(data / "dim_final_features.csv", index=False, encoding="utf-8-sig")

    # --- overfit ---
    o = _over()
    for name, outn in [
        ("learning_curve.csv", "fact_overfit_learning_curve.csv"),
        ("capacity_sweep.csv", "fact_overfit_capacity.csv"),
        ("split_gap_by_spec.csv", "fact_overfit_split_gap.csv"),
        ("feature_correlation.csv", "fact_feature_correlation.csv"),
    ]:
        src = o / name
        if src.is_file():
            pd.read_csv(src, encoding="utf-8-sig").to_csv(
                data / outn, index=False, encoding="utf-8-sig"
            )
    oj = o / "OVERFIT_SUMMARY.json"
    if oj.is_file():
        j = json.loads(oj.read_text(encoding="utf-8"))
        flat = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in j.items()}
        pd.DataFrame([flat]).to_csv(data / "fact_overfit_summary.csv", index=False, encoding="utf-8-sig")

    # --- IQR ---
    if IQR.is_dir():
        for p in IQR.glob("*.csv"):
            shutil.copy2(p, data / f"fact_iqr_{p.name}")

    # --- validity / integration summaries ---
    for folder, outn in [(VALID, "fact_validity_summary.csv"), (INTEG, "fact_integration_summary.csv")]:
        if not folder.is_dir():
            continue
        for cand in ("summary.json", "README.md"):
            pass
        # prefer checks.csv / summary.json
        for p in folder.glob("*.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(j, dict) and ("checks" in j or "mvp_verdict" in j or "metrics" in j):
                if "checks" in j and isinstance(j["checks"], list):
                    pd.json_normalize(j["checks"]).to_csv(
                        data / outn.replace("summary", "checks"), index=False, encoding="utf-8-sig"
                    )
                flat = {
                    k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                    for k, v in j.items()
                    if k != "checks"
                }
                if flat:
                    pd.DataFrame([flat]).to_csv(data / outn, index=False, encoding="utf-8-sig")
                break
        for p in folder.glob("checks.csv"):
            shutil.copy2(p, data / "fact_validity_checks.csv")

    # --- 현재표 sample for map (public candidates) ---
    if SNAP.is_file():
        df = pd.read_csv(SNAP, encoding="utf-8-sig", low_memory=False)
        cols_pref = [
            "statId",
            "statNm",
            "lat",
            "lng",
            "available_count",
            "total_chargers",
            "availability_ratio_observed",
            "reliability_grade",
            "reliability_grade_effective",
            "observation_age_minutes",
            "as_of_ts",
            "recommend_public_default",
            "parking_is_mock",
            "traffic_is_mock",
        ]
        cols = [c for c in cols_pref if c in df.columns]
        # also common alt names
        for a, b in [("latitude", "lat"), ("longitude", "lng"), ("stat_id", "statId")]:
            if a in df.columns and b not in df.columns:
                df[b] = df[a]
                if b not in cols:
                    cols.append(b)
        sample = df[cols].copy() if cols else df.head(5000)
        # filter public if flag exists
        if "recommend_public_default" in sample.columns:
            pub = sample[sample["recommend_public_default"] == True]  # noqa: E712
            if len(pub):
                sample = pub
        sample.to_csv(data / "fact_snapshot_stations.csv", index=False, encoding="utf-8-sig")

    # file index
    files = sorted([p.name for p in data.glob("*")])
    pd.DataFrame({"file": files, "folder": "data"}).to_csv(
        data / "00_file_index.csv", index=False, encoding="utf-8-sig"
    )

    guide = f"""# Power BI 만들기 — DA① {STAMP}

| | |
|---|---|
| **폴더** | `포폴용_개인_대시보드_{STAMP}/` (**전달 아님 · 포폴 전용**) |
| **데이터** | `data/*.csv` (전부 UTF-8 BOM · Import 모드) |
| **점수** | **만들지 말 것** (② 영역) |
| **현재표 as_of** | 2026-08-09T07:23:21+09:00 |

## 1. 파일 열기

1. Power BI Desktop 실행  
2. **데이터 가져오기 → 텍스트/CSV**  
3. `data` 폴더의 아래 표를 **모두** 가져오기 (또는 폴더 가져오기)

필수:
- `dim_meta.csv`
- `fact_kpi.csv`
- `fact_eda_hour.csv` · `fact_eda_dow.csv` · `fact_eda_charger_bucket.csv` · `fact_eda_freshness.csv`
- `fact_feature_decisions.csv` · `fact_loo_deltas.csv` · `dim_final_features.csv`
- `fact_reliability_blocks.csv`
- `fact_overfit_learning_curve.csv` · `fact_overfit_summary.csv`
- `fact_snapshot_stations.csv` (지도)
- `fact_iqr_*.csv` (있으면)

## 2. 페이지 구성 (추천 4장)

### P1. 운영 KPI
- 카드: `dim_meta[as_of]` · KPI OK 개수  
- 표/도넛: `fact_kpi[status]`  
- 주의: FAIL/WARN만 강조

### P2. EDA 가용 패턴
- 선차트: `fact_eda_hour` → X=hour, Y=avail_mean  
- 막대: `fact_eda_dow` → dow_ko × avail_mean  
- 막대: `fact_eda_charger_bucket`  
- 스택: `fact_eda_freshness` (HIGH/NORMAL/CHECK)

### P3. HGB 피처·과적합
- 표: `dim_final_features` (최종 9)  
- 막대: `fact_loo_deltas` (Δ PR-AUC)  
- 선: `fact_overfit_learning_curve`  
- 카드: overfit / fitness PASS·WARN (`fact_overfit_summary`, `fact_model_fitness`)

### P4. 현재표 지도
- 지도: `fact_snapshot_stations` lat/lng  
- 색: availability 또는 reliability_grade  
- 툴팁: available_count, total_chargers, observation_age_minutes

## 3. 용어 (시각에 그대로)

- **현재표** = snapshot  
- **시간표** = panel (이 팩의 EDA는 시간표 집계)  
- 동대구 ETA = 학습용 고정 origin (서빙은 BE 사용자 위치)

## 4. 저장

- 포폴용으로만 저장. **최종본·조장 전달에 넣지 말 것.**

## 5. 재생성

```
python apps/data-pipeline/processing/tools/share/build_powerbi_pack_20260809.py
```

```
포폴 전용 | 대시보드 | {STAMP} | 전달 아님
```
"""
    (OUT / "00_PowerBI_만들기.md").write_text(guide, encoding="utf-8")
    (OUT / "README.md").write_text(
        f"# 포폴용 · 개인 대시보드 ({STAMP})\n\n"
        "**팀 전달 아님.** 최종본에 포함하지 않음.\n\n"
        f"먼저 [`00_PowerBI_만들기.md`](./00_PowerBI_만들기.md)\n\n데이터: `data/`\n",
        encoding="utf-8",
    )

    # DAX snippets
    (OUT / "01_DAX_예시.txt").write_text(
        "\n".join(
            [
                "// 카드용 예시 (열 이름은 가져온 뒤 맞게 수정)",
                "KPI_OK_수 = CALCULATE(COUNTROWS(fact_kpi), fact_kpi[status]=\"OK\")",
                "현재표_as_of = SELECTEDVALUE(dim_meta[as_of])",
                "가용_오전 = CALCULATE(AVERAGE(fact_eda_hour[avail_mean]), fact_eda_hour[hour]>=8, fact_eda_hour[hour]<=11)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # desktop mirror (portfolio only — not final pack)
    if DESK.exists():
        shutil.rmtree(DESK)
    shutil.copytree(OUT, DESK)

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(OUT),
                "desktop": str(DESK),
                "handoff": False,
                "n_files": len(list(data.glob("*"))),
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

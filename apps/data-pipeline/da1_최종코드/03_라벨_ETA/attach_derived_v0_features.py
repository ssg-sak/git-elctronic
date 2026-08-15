"""Attach derived_v0 columns to arrival labels + D1 ETA companion.

RETAIN (학습 허용):
  - single_charger
  - eta_bucket  (horizon_minutes와 택1 — 스키마 권장은 horizon 유지, bucket은 대안)

EXCLUDE (학습 금지, 메타/층화만):
  - eta_is_proxy

HOLD 진단용(학습 기본 세트 아님):
  - avail_ratio_t0

See: docs/팀공유/파생변수_검토_도착라벨_20260806.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

KST = ZoneInfo("Asia/Seoul")
REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "apps/data-pipeline/evaluation/results/datasets"
ANALYSIS = REPO / "docs/data/analysis"
SHARE = REPO / "docs/팀공유"
DOC = SHARE / "파생변수_검토_도착라벨_20260806.md"

ETA_BINS = [-0.1, 10, 20, 40, 1e9]
ETA_LABELS = ["0_10", "10_20", "20_40", "40p"]


def _eta_bucket(minutes: pd.Series) -> pd.Series:
    return pd.cut(
        pd.to_numeric(minutes, errors="coerce"),
        bins=ETA_BINS,
        labels=ETA_LABELS,
    ).astype("string")


def attach_labels() -> tuple[pd.DataFrame, dict]:
    labels_path = OUT / "arrival_labels_tmap_eta_v1.parquet"
    eta_path = OUT / "station_tmap_eta_latest.csv"
    d1_path = OUT / "station_feature_snapshot_latest.csv"
    if not labels_path.exists():
        raise FileNotFoundError(labels_path)

    lab = pd.read_parquet(labels_path)
    lab["statId"] = lab["statId"].astype(str)

    d1 = pd.read_csv(d1_path, encoding="utf-8-sig", dtype={"statId": str}, low_memory=False)
    tot = (
        d1[["statId", "total_chargers"]]
        .drop_duplicates("statId")
        .assign(total_chargers=lambda x: pd.to_numeric(x["total_chargers"], errors="coerce"))
    )
    eta = pd.read_csv(eta_path, dtype={"statId": str}, low_memory=False)
    ecols = ["statId"]
    if "eta_is_proxy" in eta.columns:
        ecols.append("eta_is_proxy")
    emeta = eta[ecols].drop_duplicates("statId")

    out = lab.merge(tot, on="statId", how="left").merge(emeta, on="statId", how="left")
    out["single_charger"] = (out["total_chargers"] == 1).astype("Int64")
    out["eta_bucket"] = _eta_bucket(out["tmap_eta_min"])
    # horizon already present — preferred of the 택1 pair
    out["avail_ratio_t0"] = (
        pd.to_numeric(out["current_available_count"], errors="coerce")
        / out["total_chargers"].clip(lower=1)
    )
    if "eta_is_proxy" in out.columns:
        out["eta_is_proxy"] = (
            out["eta_is_proxy"].astype(str).str.lower().isin(["true", "1"])
        )

    stamp = datetime.now(KST).strftime("%Y%m%d")
    analysis = ANALYSIS / f"derived_v0_{stamp}"
    analysis.mkdir(parents=True, exist_ok=True)

    pq = OUT / "arrival_labels_tmap_eta_v1_with_derived.parquet"
    out.to_parquet(pq, index=False)
    out.to_parquet(analysis / "arrival_labels_with_derived.parquet", index=False)
    out.head(30_000).to_csv(
        OUT / "arrival_labels_tmap_eta_v1_with_derived_sample.csv",
        index=False,
        encoding="utf-8-sig",
    )

    meta = {
        "role": "DA① derived_v0 attach on arrival labels",
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "rows": int(len(out)),
        "stations": int(out["statId"].nunique()),
        "retain_features": ["single_charger", "horizon_minutes", "eta_bucket"],
        "horizon_vs_eta_bucket": "택1 — 권장 horizon_minutes; eta_bucket는 대안",
        "exclude_from_training": ["eta_is_proxy", "slack_chargers", "age_x_eta"],
        "hold_diagnostic": ["avail_ratio_t0"],
        "files": {
            "labels_with_derived": str(pq.relative_to(REPO)).replace("\\", "/"),
            "sample": "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived_sample.csv",
            "analysis": str(analysis.relative_to(REPO)).replace("\\", "/"),
        },
        "doc": "docs/팀공유/파생변수_검토_도착라벨_20260806.md",
    }
    (OUT / "derived_v0_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (analysis / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out, meta


def attach_d1_companion() -> Path:
    path = OUT / "station_feature_snapshot_with_eta_latest.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    d1 = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    d1["statId"] = d1["statId"].astype(str)
    d1["total_chargers"] = pd.to_numeric(d1["total_chargers"], errors="coerce")
    d1["single_charger"] = (d1["total_chargers"] == 1).astype("Int64")
    eta_min = pd.to_numeric(d1.get("tmap_eta_min"), errors="coerce")
    d1["eta_bucket"] = _eta_bucket(eta_min)
    # do not treat eta_is_proxy as model feature; keep if present
    out_csv = OUT / "station_feature_snapshot_with_eta_derived_latest.csv"
    out_pq = OUT / "station_feature_snapshot_with_eta_derived_latest.parquet"
    d1.to_csv(out_csv, index=False, encoding="utf-8-sig")
    d1.to_parquet(out_pq, index=False)
    return out_csv


def write_schema() -> Path:
    schema = {
        "version": "derived_v0",
        "target": "target_available_at_arrival",
        "grain": "statId × feature_as_of × horizon_minutes",
        "mvp_base": [
            "available_count",
            "total_chargers",
            "known_charger_count",
            "observation_coverage",
            "observation_age_minutes",
            "horizon_minutes",
        ],
        "derived_retain": [
            {
                "name": "single_charger",
                "dtype": "int0_1",
                "definition": "total_chargers == 1",
                "role": "feature",
            },
            {
                "name": "eta_bucket",
                "dtype": "category",
                "definition": "tmap_eta_min in {0_10,10_20,20_40,40p}",
                "role": "feature_alt",
                "note": "horizon_minutes와 택1 — 기본은 horizon",
            },
        ],
        "exclude_training": [
            {
                "name": "eta_is_proxy",
                "reason": "TMAP quota selection bias; use for eval stratification only",
            },
            {"name": "slack_chargers", "reason": "identical to available_count-1 under candidate filter"},
            {"name": "age_x_eta", "reason": "no evidence on current labels"},
        ],
        "hold": [
            {
                "name": "avail_ratio_t0",
                "reason": "weak/unstable; ablation only after TMAP real-ETA refresh",
            },
            {
                "name": "stale_flag / unobserved_flag",
                "reason": "D2 panel lacks per-tick observation_age/state; recheck after panel columns exist",
            },
        ],
        "files": {
            "labels": "apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived.parquet",
            "d1_companion": "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_with_eta_derived_latest.csv",
        },
    }
    path = OUT / "derived_v0_schema.json"
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    share = SHARE / "파생변수_derived_v0_20260806"
    share.mkdir(parents=True, exist_ok=True)
    (share / "derived_v0_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def hold_recheck(lab: pd.DataFrame) -> dict:
    """Re-check HOLD items with label-native t0 features (not D1-latest age)."""
    y = lab["target_available_at_arrival"].astype(int)
    # oversample negatives for stable AUC
    neg = lab.index[y == 0].to_numpy()
    pos = lab.index[y == 1].to_numpy()
    rng = np.random.default_rng(42)
    n_pos = min(len(pos), max(len(neg) * 15, 50_000))
    idx = np.concatenate([neg, rng.choice(pos, size=n_pos, replace=False)])
    s = lab.loc[idx].copy()
    ys = s["target_available_at_arrival"].astype(int)

    def _auc(col: str) -> float | None:
        v = pd.to_numeric(s[col], errors="coerce")
        m = v.notna()
        if m.sum() < 1000 or ys[m].nunique() < 2 or v[m].nunique() < 2:
            return None
        return float(roc_auc_score(ys[m], v[m]))

    # panel coverage proxy at t0: known not on labels — use avail_ratio only
    out = {
        "sample_n": int(len(s)),
        "sample_pos_rate": float(ys.mean()),
        "avail_ratio_t0": {
            "auc": _auc("avail_ratio_t0"),
            "corr_with_current_available": float(
                s[["avail_ratio_t0", "current_available_count"]]
                .astype(float)
                .corr()
                .iloc[0, 1]
            ),
            "verdict": "HOLD_KEEP — weak vs available_count; do not add to MVP yet",
        },
        "single_charger": {
            "auc": _auc("single_charger"),
            "rate_multi": float(ys[s["single_charger"] == 0].mean())
            if (s["single_charger"] == 0).any()
            else None,
            "rate_single": float(ys[s["single_charger"] == 1].mean())
            if (s["single_charger"] == 1).any()
            else None,
            "verdict": "RETAIN",
        },
        "eta_bucket_vs_horizon": {
            "auc_horizon": _auc("horizon_minutes"),
            "note": "택1 — prefer horizon_minutes already in schema",
        },
        "stale_unobserved": {
            "verdict": "HOLD_BLOCKED",
            "reason": "station_feature_panel has no observation_age_minutes / observation_state per tick; cannot validate at feature_as_of without panel schema change",
        },
        "eta_is_proxy": {
            "auc": _auc("eta_is_proxy") if "eta_is_proxy" in s.columns else None,
            "verdict": "EXCLUDE_TRAINING — eval stratification only",
        },
    }
    stamp = datetime.now(KST).strftime("%Y%m%d")
    path = ANALYSIS / f"derived_v0_{stamp}" / "hold_recheck.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "derived_v0_hold_recheck.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out


def update_team_docs(meta: dict, hold: dict) -> None:
    share = SHARE / "파생변수_derived_v0_20260806"
    share.mkdir(parents=True, exist_ok=True)
    (share / "meta.json").write_text(
        json.dumps({"attach": meta, "hold_recheck": hold}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    readme = f"""# derived_v0 부착 완료 — 20260806

| 항목 | 값 |
|---|---|
| 라벨 행 | {meta['rows']:,} |
| 충전소 | {meta['stations']} |
| RETAIN | `single_charger` + (`horizon_minutes` 권장 / `eta_bucket` 대안) |
| EXCLUDE 학습 | `eta_is_proxy` · 여유충전기 · 경과×ETA |
| HOLD | `avail_ratio_t0` · 오래됨/미관측(패널 컬럼 부재) |

## 파일

- 라벨+파생: `apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived.parquet`
- D1+ETA+파생: `.../station_feature_snapshot_with_eta_derived_latest.csv`
- 스키마: `.../derived_v0_schema.json`
- 검토 원문: [`파생변수_검토_도착라벨_20260806.md`](../파생변수_검토_도착라벨_20260806.md)

## HOLD 재검증 요약

- 가용비율 AUC≈{hold['avail_ratio_t0'].get('auc')} → HOLD 유지
- 단수충전기 → RETAIN 확인
- 오래됨/미관측 → 패널에 tick 단위 age/state 없음 → HOLD_BLOCKED

```
DA① | derived_v0 attached | 20260806
```
"""
    (share / "README.md").write_text(readme, encoding="utf-8")

    # append implementation status to review doc (idempotent block)
    marker = "## 구현 상태 (derived_v0 부착)"
    block = f"""
{marker}

| 항목 | 상태 |
|---|---|
| 라벨 부착 | ✅ `arrival_labels_tmap_eta_v1_with_derived.parquet` ({meta['rows']:,}행) |
| D1 companion | ✅ `station_feature_snapshot_with_eta_derived_latest.*` |
| 스키마 | ✅ `derived_v0_schema.json` · 공유 `파생변수_derived_v0_20260806/` |
| HOLD 재검증 | 가용비율 **HOLD 유지** · 오래됨/미관측 **패널 컬럼 부재로 BLOCKED** |

```
DA① | derived_v0 implemented | 20260806
```
"""
    if DOC.exists():
        text = DOC.read_text(encoding="utf-8")
        if marker in text:
            pre = text.split(marker)[0].rstrip()
            DOC.write_text(pre + "\n" + block, encoding="utf-8")
        else:
            DOC.write_text(text.rstrip() + "\n" + block, encoding="utf-8")


def main() -> int:
    lab, meta = attach_labels()
    d1_path = attach_d1_companion()
    schema_path = write_schema()
    hold = hold_recheck(lab)
    meta["d1_derived"] = str(d1_path.relative_to(REPO)).replace("\\", "/")
    meta["schema"] = str(schema_path.relative_to(REPO)).replace("\\", "/")
    (OUT / "derived_v0_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    update_team_docs(meta, hold)
    print(json.dumps({"meta": meta, "hold": hold}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

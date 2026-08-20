"""Usage-history join QA: match quality + D1 coverage ceiling (not a bug report).

Coverage ~4–5% is expected: municipal source has ~219 stations vs ~4200 EvCharger.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")

JOIN = REPO / "docs/data/spatial_join/join_usage_history_statId.csv"
JOIN_META = REPO / "docs/data/spatial_join/join_usage_history_meta.json"
FEAT = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_history_features_latest.csv"
)
FEAT_META = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_history_features_meta.json"
)
D1 = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
)
OUT_DIR = REPO / "docs/data/analysis" / f"usage_history_qa_{datetime.now(KST).strftime('%Y%m%d')}"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    join = pd.read_csv(JOIN, dtype=str, low_memory=False)
    join["matched"] = join.get("matched", "False").astype(str).str.lower().isin(
        ["true", "1"]
    )
    join["distance_m"] = pd.to_numeric(join.get("distance_m"), errors="coerce")

    matched = join[join["matched"]]
    dist = matched["distance_m"].dropna()
    unmatched = join[~join["matched"]]

    d1_rows = 0
    d1_hist = 0
    if D1.exists():
        d1 = pd.read_csv(D1, dtype=str, usecols=lambda c: c in {"statId", "history_observed"})
        d1_rows = len(d1)
        if "history_observed" in d1.columns:
            d1_hist = int(
                d1["history_observed"].astype(str).str.lower().isin(["true", "1"]).sum()
            )

    feat_stations = 0
    if FEAT.exists():
        feat = pd.read_csv(FEAT, dtype=str, usecols=["statId"])
        feat_stations = int(feat["statId"].nunique())

    join_meta = {}
    if JOIN_META.exists():
        join_meta = json.loads(JOIN_META.read_text(encoding="utf-8"))

    summary = {
        "generated_at_kst": datetime.now(KST).isoformat(),
        "usage_stations_source": int(len(join)),
        "matched": int(matched.shape[0]),
        "unmatched": int(unmatched.shape[0]),
        "match_rate": round(float(matched.shape[0] / len(join)), 4) if len(join) else 0,
        "distance_m": {
            "min": float(dist.min()) if len(dist) else None,
            "median": float(dist.median()) if len(dist) else None,
            "p95": float(dist.quantile(0.95)) if len(dist) else None,
            "max": float(dist.max()) if len(dist) else None,
        },
        "feature_unique_statId": feat_stations,
        "d1_rows": d1_rows,
        "d1_history_observed": d1_hist,
        "d1_coverage_pct": round(100.0 * d1_hist / d1_rows, 2) if d1_rows else None,
        "coverage_ceiling_note": (
            "D1 coverage is bounded by municipal usage station count (~219), "
            "not by join failure. EvCharger master is ~4k stations."
        ),
        "join_meta": join_meta,
        "unmatched_sample": unmatched.head(20).to_dict(orient="records"),
    }

    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    unmatched.to_csv(OUT_DIR / "unmatched_usage_stations.csv", index=False, encoding="utf-8-sig")
    if len(dist):
        dist.describe().to_csv(OUT_DIR / "match_distance_describe.csv", encoding="utf-8-sig")

    readme = f"""# 이용강도(usage) 조인 QA

| 항목 | 값 |
|---|---:|
| 원천 이용 충전소 | {summary['usage_stations_source']} |
| 좌표 매칭 | {summary['matched']} ({summary['match_rate']:.1%}) |
| 미매칭 | {summary['unmatched']} |
| D1 history_observed | {d1_hist} / {d1_rows} ({summary['d1_coverage_pct']}%) |
| 거리 중앙값(m) | {summary['distance_m']['median']} |

## 해석

**D1 커버리지 ~4–5%는 조인 버그가 아니다.**  
대구시 이용현황 CSV의 충전소 수(~219)가 EvCharger 마스터(~4200)보다 훨씬 작아
상한이 원천에 묶인다. 매칭률(원천 대비)이 높으면 정상이다.

생성: {summary['generated_at_kst']}
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    # Keep feature meta aligned with D1 merge reality
    if FEAT_META.exists():
        feat_meta = json.loads(FEAT_META.read_text(encoding="utf-8"))
        feat_meta["d1_merged"] = True
        feat_meta["d1_coverage_note"] = summary["coverage_ceiling_note"]
        feat_meta["qa_report"] = str((OUT_DIR / "summary.json").relative_to(REPO)).replace(
            "\\", "/"
        )
        FEAT_META.write_text(
            json.dumps(feat_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if JOIN_META.exists():
        join_meta["d1_merged"] = True
        join_meta["d1_coverage_ceiling_note"] = summary["coverage_ceiling_note"]
        JOIN_META.write_text(
            json.dumps(join_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"OUT {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

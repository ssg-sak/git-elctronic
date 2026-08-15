"""Column-wise missingness for current DA① datasets (D1, fee, status, parking, link)."""
from __future__ import annotations

import json
import shutil
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


def is_missing(s: pd.Series) -> pd.Series:
    """True empty / pandas NA markers only.

    Do NOT treat business codes like fee_match_level='NONE' as missing.
    """
    x = s.astype(str).str.strip()
    return s.isna() | x.eq("") | x.str.lower().isin(["nan", "null", "<na>", "nat", "natype"])


def profile(path: Path, name: str, key_cols: list[str] | None = None) -> dict:
    if not path.exists():
        return {"name": name, "error": "missing file", "path": str(path)}
    df = pd.read_csv(path, dtype=str, low_memory=False)
    n = len(df)
    rows = []
    for c in df.columns:
        m = int(is_missing(df[c]).sum())
        rows.append(
            {
                "dataset": name,
                "column": c,
                "rows": n,
                "missing": m,
                "missing_pct": round(100.0 * m / n, 2) if n else None,
                "non_missing": n - m,
                "non_missing_pct": round(100.0 * (n - m) / n, 2) if n else None,
            }
        )
    miss = pd.DataFrame(rows).sort_values("missing_pct", ascending=False)
    out_csv = OUT / f"{name}_missing_by_column.csv"
    miss.to_csv(out_csv, index=False, encoding="utf-8-sig")
    bands = {
        "complete_0pct": int((miss["missing_pct"] == 0).sum()),
        "low_lt5": int(((miss["missing_pct"] > 0) & (miss["missing_pct"] < 5)).sum()),
        "mid_5_50": int(((miss["missing_pct"] >= 5) & (miss["missing_pct"] < 50)).sum()),
        "high_50_90": int(((miss["missing_pct"] >= 50) & (miss["missing_pct"] < 90)).sum()),
        "almost_all_ge90": int((miss["missing_pct"] >= 90).sum()),
    }
    key_report = []
    if key_cols:
        for c in key_cols:
            if c in miss["column"].values:
                r = miss.loc[miss["column"] == c].iloc[0]
                key_report.append(
                    {
                        "column": c,
                        "missing_pct": float(r["missing_pct"]),
                        "missing": int(r["missing"]),
                    }
                )
            else:
                key_report.append({"column": c, "missing_pct": None, "note": "not in dataset"})
    return {
        "name": name,
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "rows": n,
        "cols": int(len(df.columns)),
        "bands": bands,
        "top_missing": miss.head(20)[["column", "missing", "missing_pct"]].to_dict(
            orient="records"
        ),
        "key_columns": key_report,
        "detail_csv": str(out_csv.relative_to(REPO)).replace("\\", "/"),
    }


def write_report(summary: dict, fam_summary: pd.DataFrame) -> str:
    datasets = summary["datasets"]
    lines = [
        f"# 결측률 점검 ({summary['stamp']})",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| **작성** | AI·데이터 ① |",
        f"| **생성** | {summary['generated_at']} |",
        "| **한 줄** | D1·요금·상태·주차·링크 등 **현재 파일** 컬럼별 빈칸 비율 |",
        "",
        "## 읽는 법",
        "",
        "- **결측** = 비어 있음 또는 `nan`/`null` 문자열",
        "- 일부는 **의도적 null**(예: `eta_minutes`) → 100%여도 버그 아님",
        "- 주차·돌발·이력은 **원천 커버리지** 때문에 결측이 클 수 있음",
        "",
        "## 데이터셋 요약",
        "",
        "| 데이터셋 | 행 | 열 | 완전(0%) | 거의결측(≥90%) |",
        "|---|---:|---:|---:|---:|",
    ]
    for d in datasets:
        if "error" in d:
            lines.append(f"| {d['name']} | - | - | ERR | {d.get('error')} |")
            continue
        b = d["bands"]
        lines.append(
            f"| {d['name']} | {d['rows']:,} | {d['cols']} | {b['complete_0pct']} | {b['almost_all_ge90']} |"
        )

    lines += [
        "",
        "## D1 피처 가족별 평균 결측%",
        "",
        "| 가족 | 컬럼수 | 평균 결측% | 최대 | 최소 |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in fam_summary.to_dict(orient="records"):
        lines.append(
            f"| {r['family']} | {r['cols']} | {r['mean_missing_pct']} | {r['max_missing_pct']} | {r['min_missing_pct']} |"
        )

    d1p = next(d for d in datasets if d["name"].startswith("D1"))
    lines += [
        "",
        "## D1 결측 많은 컬럼 TOP",
        "",
        "| 컬럼 | 결측% | 결측수 |",
        "|---|---:|---:|",
    ]
    for r in d1p.get("top_missing", [])[:15]:
        lines.append(f"| `{r['column']}` | {r['missing_pct']} | {r['missing']:,} |")

    feep = next((d for d in datasets if d["name"].startswith("fee_station")), None)
    if feep and feep.get("key_columns"):
        lines += ["", "## 요금 힌트 핵심 컬럼", "", "| 컬럼 | 결측% |", "|---|---:|"]
        for r in feep["key_columns"]:
            if r.get("missing_pct") is not None:
                lines.append(f"| `{r['column']}` | {r['missing_pct']} |")

    lines += [
        "",
        "## 해석 (쉬운 말)",
        "",
        "| 높은 결측 | 의미 |",
        "|---|---|",
        "| `eta_minutes` ~100% | **의도적 null 예약** (BE/TMAP) |",
        "| usage_* 높음 | 이력 원천 커버리지 낮음 |",
        "| parking realtime / 1h | realtime 붙은 소만 값 있음 |",
        "| incident / link | 근처 매칭 없을 때 null |",
        "| 요금 sample | 운영사 미매칭 ~3% |",
        "",
        f"상세: `docs/data/analysis/missingness_{summary['stamp']}/`",
        "",
        "```",
        f"DA① | missingness check | {summary['stamp']}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    global OUT, SHARE
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stamp = datetime.now(KST).strftime("%Y%m%d")
    OUT = REPO / "docs/data/analysis" / f"missingness_{stamp}"
    SHARE = REPO / "docs/팀공유" / f"결측률_점검_{stamp}"
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)

    datasets: list[dict] = []
    d1 = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    datasets.append(
        profile(
            d1,
            "D1_station_feature_snapshot",
            key_cols=[
                "statId",
                "lat",
                "lng",
                "coord_ok",
                "available_count",
                "observed_count",
                "availability_ratio_observed",
                "status_age_minutes",
                "reliability_grade_effective",
                "observation_state",
                "usage_level",
                "eta_minutes",
                "nearest_parking_m",
                "parking_remaining_spaces",
                "parking_has_realtime",
                "nearest_incident_m",
                "nearest_link_id",
                "link_speed_kph",
            ],
        )
    )

    fee = (
        REPO
        / "docs/data/analysis/fee_operator_evorkr_probe_20260731/daegu_station_operator_fee_hint.csv"
    )
    datasets.append(
        profile(
            fee,
            "fee_station_operator_hint",
            key_cols=[
                "statId",
                "busiId",
                "busiNm",
                "fee_operator_nm",
                "fee_match_level",
                "member_won_sample",
                "nonmember_won_sample",
                "capacity_class_sample",
            ],
        )
    )

    tariff = REPO / "docs/data/extracted/fee/fee_tariff_ref_operator_evorkr_20260731.csv"
    datasets.append(
        profile(
            tariff,
            "fee_operator_tariff",
            key_cols=[
                "operator_nm",
                "capacity_class",
                "member_won_per_kwh",
                "nonmember_won_per_kwh",
                "member_note",
                "updated_at",
            ],
        )
    )

    status_dir = REPO / "docs/data/loops/loop1/snapshots"
    snaps = sorted(
        p
        for p in status_dir.rglob("daegu_charger_status_*.csv")
        if "daily" not in p.name
    )
    if snaps:
        datasets.append(
            profile(
                snaps[-1],
                "status_latest_snap",
                key_cols=["statId", "chgerId", "stat", "statUpdDt", "lat", "lng", "busiId"],
            )
        )

    park_files = sorted(
        (REPO / "docs/data/extracted/parking").rglob("parking_realtime_status*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if park_files:
        datasets.append(profile(park_files[0], "parking_realtime_latest_file"))

    link_dir = REPO / "docs/data/spatial_join"
    link_cands = sorted(link_dir.glob("*linkspeed*station*.csv"))
    if link_cands:
        datasets.append(profile(link_cands[0], "linkspeed_station_join"))

    df = pd.read_csv(d1, dtype=str, low_memory=False)
    n = len(df)
    families = {
        "identity": ["statId", "statNm", "addr", "lat", "lng", "coord_ok"],
        "status_asof": [
            "available_count",
            "observed_count",
            "availability_ratio_observed",
            "has_confirmed_available",
            "status_age_minutes",
            "observation_state",
            "reliability_grade_effective",
        ],
        "access": [
            "limitYn",
            "access_restricted",
            "recommend_public_default",
            "is_operating_now",
        ],
        "usage_history": ["usage_level", "sessions_per_charger", "history_observed"],
        "parking": [
            "nearest_parking_m",
            "parking_remaining_spaces",
            "parking_total_spaces",
            "parking_occupancy_rate",
            "parking_has_realtime",
        ],
        "incident": [c for c in df.columns if "incident" in c.lower()],
        "linkspeed": [
            c for c in df.columns if "link" in c.lower() or c.startswith("link_")
        ],
        "eta": ["eta_minutes"],
        "poi": ["poi_count_1km"],
        "parking_1h": [c for c in df.columns if "1h" in c.lower()],
    }
    fam_rows = []
    for fam, cols in families.items():
        for c in [x for x in cols if x in df.columns]:
            m = int(is_missing(df[c]).sum())
            fam_rows.append(
                {
                    "family": fam,
                    "column": c,
                    "missing_pct": round(100 * m / n, 2),
                    "missing": m,
                    "rows": n,
                }
            )
    fam_df = pd.DataFrame(fam_rows)
    fam_df.to_csv(OUT / "D1_missing_by_family.csv", index=False, encoding="utf-8-sig")
    fam_summary = (
        fam_df.groupby("family")
        .agg(
            cols=("column", "count"),
            mean_missing_pct=("missing_pct", "mean"),
            max_missing_pct=("missing_pct", "max"),
            min_missing_pct=("missing_pct", "min"),
        )
        .round(2)
        .reset_index()
        .sort_values("mean_missing_pct", ascending=False)
    )
    fam_summary.to_csv(OUT / "D1_family_summary.csv", index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "stamp": stamp,
        "datasets": datasets,
        "d1_family_summary": fam_summary.to_dict(orient="records"),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = write_report(summary, fam_summary)
    (OUT / "README.md").write_text(text, encoding="utf-8")
    (SHARE / "README.md").write_text(text, encoding="utf-8")
    for p in OUT.glob("*"):
        if p.is_file():
            shutil.copy2(p, SHARE / p.name)

    print(json.dumps(
        {
            "out": str(OUT.relative_to(REPO)).replace("\\", "/"),
            "share": str(SHARE.relative_to(REPO)).replace("\\", "/"),
            "d1_family": fam_summary.to_dict(orient="records"),
            "datasets": [
                {k: d.get(k) for k in ("name", "rows", "cols", "bands", "error")}
                for d in datasets
            ],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    OUT = Path()
    SHARE = Path()
    raise SystemExit(main())

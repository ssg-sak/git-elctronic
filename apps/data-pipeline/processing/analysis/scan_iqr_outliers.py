"""IQR outlier scan on latest D1 snapshot + share figures.

Outputs:
  docs/data/analysis/iqr_outlier_scan_<YYYYMMDD>/
  docs/팀공유/IQR_이상치검사_<YYYYMMDD>/
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
KST = ZoneInfo("Asia/Seoul")

plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COLS = [
    ("total_chargers", "충전기 수"),
    ("available_count", "가용 충전기 수"),
    ("observed_count", "관측 충전기 수"),
    ("availability_ratio_observed", "관측 가용률(0~1)"),
    ("status_age_minutes", "status age(분)"),
    ("observation_age_minutes", "observation age(분)"),
    ("nearest_parking_m", "최근접 주차(m)"),
    ("parking_occupancy_rate", "주차 점유율(%)"),
    ("parking_remaining_spaces", "주차 잔여면"),
    ("parking_remaining_delta_1h", "주차 잔여 Δ1h"),
    ("nearest_incident_m", "최근접 돌발(m)"),
    ("link_speed_kph", "링크속도(kph)"),
    ("sessions_per_charger", "sessions/충전기"),
]


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    d1_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    )
    d1 = pd.read_csv(d1_path, encoding="utf-8-sig", low_memory=False)
    as_of = str(d1["as_of_ts"].iloc[0])

    out = REPO / f"docs/data/analysis/iqr_outlier_scan_{stamp}"
    fig_dir = out / "figures"
    share = REPO / "docs" / "팀공유" / f"IQR_이상치검사_{stamp}"
    share_fig = share / "figures"
    for p in (fig_dir, share_fig, share / "data"):
        p.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    detail_frames: list[pd.DataFrame] = []

    for col, label in COLS:
        if col not in d1.columns:
            continue
        s = pd.to_numeric(d1[col], errors="coerce")
        valid = s.dropna()
        n = int(len(valid))
        if n < 20:
            continue
        q1 = float(valid.quantile(0.25))
        q3 = float(valid.quantile(0.75))
        iqr = q3 - q1
        if iqr <= 1e-12:
            mild_lo = float(valid.quantile(0.01))
            mild_hi = float(valid.quantile(0.99))
            ext_lo, ext_hi = mild_lo, mild_hi
            method = "p01-p99 (IQR≈0)"
        else:
            mild_lo = q1 - 1.5 * iqr
            mild_hi = q3 + 1.5 * iqr
            ext_lo = q1 - 3.0 * iqr
            ext_hi = q3 + 3.0 * iqr
            method = "1.5·IQR"
        mild = (s < mild_lo) | (s > mild_hi)
        extreme = (s < ext_lo) | (s > ext_hi)
        n_mild = int(mild.fillna(False).sum())
        n_ext = int(extreme.fillna(False).sum())
        rows.append(
            {
                "column": col,
                "label": label,
                "n_valid": n,
                "q1": q1,
                "median": float(valid.median()),
                "q3": q3,
                "iqr": float(iqr),
                "fence_1.5_lo": float(mild_lo),
                "fence_1.5_hi": float(mild_hi),
                "fence_3_lo": float(ext_lo),
                "fence_3_hi": float(ext_hi),
                "n_outlier_1.5iqr": n_mild,
                "pct_outlier_1.5iqr": round(100 * n_mild / len(d1), 2),
                "n_outlier_3iqr": n_ext,
                "pct_outlier_3iqr": round(100 * n_ext / len(d1), 2),
                "min": float(valid.min()),
                "max": float(valid.max()),
                "method": method,
            }
        )
        mask = extreme.fillna(False) if n_ext else mild.fillna(False)
        if mask.any():
            sub = d1.loc[mask, ["statId", "statNm", col]].copy()
            med = float(valid.median())
            vals = pd.to_numeric(sub[col], errors="coerce")
            sub = sub.assign(_dev=(vals - med).abs())
            sub = sub.sort_values("_dev", ascending=False).head(15).drop(columns=["_dev"])
            sub.insert(0, "metric", col)
            sub.insert(1, "metric_label", label)
            detail_frames.append(sub)

    sum_df = pd.DataFrame(rows)
    sum_df.to_csv(out / "iqr_summary.csv", index=False, encoding="utf-8-sig")
    sum_df.to_csv(share / "data" / "iqr_summary.csv", index=False, encoding="utf-8-sig")
    if detail_frames:
        det = pd.concat(detail_frames, ignore_index=True)
        det.to_csv(out / "iqr_outlier_examples.csv", index=False, encoding="utf-8-sig")
        det.to_csv(
            share / "data" / "iqr_outlier_examples.csv", index=False, encoding="utf-8-sig"
        )

    # Fig 1 — rates
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor="#f7f8fa")
    labels = sum_df["label"].tolist()
    y = np.arange(len(labels))
    ax.barh(
        y - 0.18,
        sum_df["pct_outlier_1.5iqr"],
        height=0.35,
        color="#c45c26",
        label="1.5·IQR %",
    )
    ax.barh(
        y + 0.18,
        sum_df["pct_outlier_3iqr"],
        height=0.35,
        color="#2f6f4e",
        label="3·IQR %",
    )
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("전체 소 대비 이상치 비율 (%)")
    ax.set_title(f"D1 IQR 이상치 비율 — as_of {as_of[:16]}", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.invert_yaxis()
    fig.tight_layout()
    for dest in (fig_dir, share_fig):
        fig.savefig(dest / "01_iqr_outlier_rates.png", dpi=160, bbox_inches="tight")
    plt.close(fig)

    # Fig 2 — boxplots
    plot_cols = [
        "total_chargers",
        "availability_ratio_observed",
        "observation_age_minutes",
        "nearest_parking_m",
        "parking_occupancy_rate",
        "parking_remaining_delta_1h",
        "link_speed_kph",
        "sessions_per_charger",
    ]
    plot_cols = [c for c in plot_cols if c in d1.columns]
    label_map = {c: lab for c, lab in COLS}
    fig, axes = plt.subplots(2, 4, figsize=(12, 6.5), facecolor="#f7f8fa")
    axes = axes.ravel()
    for i, col in enumerate(plot_cols):
        ax = axes[i]
        s = pd.to_numeric(d1[col], errors="coerce").dropna()
        lo, hi = s.quantile([0.01, 0.99])
        s_disp = s.clip(lo, hi)
        bp = ax.boxplot(
            s_disp,
            vert=True,
            widths=0.55,
            patch_artist=True,
            flierprops=dict(marker="o", markersize=3, alpha=0.35),
        )
        for box in bp["boxes"]:
            box.set_facecolor("#d9e2ec")
            box.set_edgecolor("#334e68")
        ax.set_title(
            f"{label_map.get(col, col)}\nmin={s.min():.2g} max={s.max():.2g}",
            fontsize=8,
        )
        ax.set_xticks([])
        ax.spines[["top", "right"]].set_visible(False)
    for j in range(len(plot_cols), len(axes)):
        axes[j].axis("off")
    fig.suptitle(
        "D1 주요 수치 boxplot (표시 p01–p99 clip, 제목에 전체 min/max)",
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout()
    for dest in (fig_dir, share_fig):
        fig.savefig(
            dest / "02_iqr_boxplots_key_metrics.png", dpi=160, bbox_inches="tight"
        )
    plt.close(fig)

    # Fig 3 — top distributions
    top = sum_df.sort_values("pct_outlier_1.5iqr", ascending=False).head(6)
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.2), facecolor="#f7f8fa")
    axes = axes.ravel()
    for i, row in enumerate(top.to_dict("records")):
        ax = axes[i]
        s = pd.to_numeric(d1[row["column"]], errors="coerce").dropna()
        ax.hist(s, bins=40, color="#627d98", alpha=0.9)
        ax.axvline(row["fence_1.5_lo"], color="#c45c26", ls="--", lw=1.1)
        ax.axvline(row["fence_1.5_hi"], color="#c45c26", ls="--", lw=1.1)
        ax.axvline(row["fence_3_lo"], color="#2f6f4e", ls=":", lw=1.1)
        ax.axvline(row["fence_3_hi"], color="#2f6f4e", ls=":", lw=1.1)
        ax.set_title(
            f"{row['label']}\n1.5IQR out {row['n_outlier_1.5iqr']} "
            f"({row['pct_outlier_1.5iqr']}%)",
            fontsize=8,
            loc="left",
        )
        ax.spines[["top", "right"]].set_visible(False)
    for j in range(len(top), len(axes)):
        axes[j].axis("off")
    fig.suptitle(
        "이상치 비율 상위 지표 분포 + IQR fence (주황 1.5·IQR / 녹 3·IQR)",
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout()
    for dest in (fig_dir, share_fig):
        fig.savefig(
            dest / "03_top_outlier_distributions.png", dpi=160, bbox_inches="tight"
        )
    plt.close(fig)

    readme = f"""# IQR 이상치 검사 — {stamp}

| 항목 | 값 |
|---|---|
| as_of | {as_of} |
| stations | {len(d1)} |
| 방법 | Tukey 1.5·IQR · 참고 3·IQR (IQR≈0이면 p01–p99) |

## 그림

- `figures/01_iqr_outlier_rates.png` — 지표별 이상치 비율
- `figures/02_iqr_boxplots_key_metrics.png` — boxplot
- `figures/03_top_outlier_distributions.png` — 상위 지표 분포+fence

## 주의

- `parking_occupancy_rate`는 **0~100(%)** 스케일
- 변경분 수집 특성상 age·가용 꼬리가 길 수 있음 → 전부 오류는 아님
- ETA 작업 전 현황 스냅샷용

```
DA① | IQR outlier scan | {stamp}
```
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    (share / "README.md").write_text(readme, encoding="utf-8")

    meta = {
        "stamp": stamp,
        "as_of": as_of,
        "n_stations": int(len(d1)),
        "n_metrics": int(len(sum_df)),
        "out": str(out.relative_to(REPO)).replace("\\", "/"),
        "share": str(share.relative_to(REPO)).replace("\\", "/"),
        "top_1.5iqr": sum_df.sort_values("pct_outlier_1.5iqr", ascending=False)[
            ["label", "n_outlier_1.5iqr", "pct_outlier_1.5iqr"]
        ]
        .head(8)
        .to_dict("records"),
    }
    (out / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (share / "data" / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

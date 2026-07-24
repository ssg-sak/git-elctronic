"""Classify Lightsail-pulled loop1/loop3 and report panel availability."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(REPO / "apps" / "data-pipeline"))

from build_panel import (  # noqa: E402
    MAX_CONTINUOUS_GAP_MINUTES,
    USABLE_STATES,
    availability_timeseries,
    build_state_panel,
)
from load_snapshots import load_snapshot  # noqa: E402

STAT_LABEL = {
    1: "통신이상",
    2: "충전가능",
    3: "충전중",
    4: "운영중지",
    5: "점검중",
    9: "상태미확인",
    10: "상태미확인",
}


def main() -> int:
    dest = REPO / "docs" / "data" / "loops" / "_archive" / "from_lightsail_20260723"
    out = dest / "report"
    snap = dest / "loop1" / "snapshots"
    logs = dest / "loop1" / "logs"
    loop3 = dest / "loop3"
    out.mkdir(parents=True, exist_ok=True)

    files = sorted(snap.glob("daegu_charger_status_*.csv"))
    frames: list[pd.DataFrame] = []
    meta_rows: list[dict] = []
    for path in files:
        df = load_snapshot(path)
        sid = path.stem.replace("daegu_charger_status_", "")
        if "snapshotId" not in df.columns or df["snapshotId"].isna().all():
            df["snapshotId"] = sid
        df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
        ts = pd.to_datetime(df["snapshotId"].iloc[0], format="%Y%m%d_%H%M%S")
        frames.append(df)
        vc = df["stat"].value_counts(dropna=False).to_dict()
        meta_rows.append(
            {
                "snapshot_id": sid,
                "ts": ts,
                "rows": len(df),
                "stations": int(df["statId"].nunique()),
                "chargers": int(df.groupby(["statId", "chgerId"]).ngroups),
                "stat_2": int(vc.get(2, 0)),
                "stat_3": int(vc.get(3, 0)),
                "stat_other": int(sum(v for k, v in vc.items() if k not in (2, 3))),
            }
        )

    all_df = pd.concat(frames, ignore_index=True)
    meta_df = pd.DataFrame(meta_rows).sort_values("ts")
    meta_df["gap_min"] = meta_df["ts"].diff().dt.total_seconds() / 60
    gaps = meta_df["gap_min"].dropna()
    big_gaps = meta_df.loc[
        meta_df["gap_min"] > MAX_CONTINUOUS_GAP_MINUTES,
        ["ts", "gap_min", "snapshot_id"],
    ]

    calls: list[dict] = []
    call_path = logs / "call_log.jsonl"
    if call_path.exists():
        for line in call_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                calls.append(json.loads(line))
    call_ok = sum(1 for c in calls if c.get("ok"))
    quota: dict = {}
    qp = logs / "daily_quota.json"
    if qp.exists():
        quota = json.loads(qp.read_text(encoding="utf-8"))

    panel = build_state_panel(all_df)
    ats = availability_timeseries(panel)
    ats_valid = ats[ats["usable_known"] >= 50].copy()

    sub = all_df[all_df["stat"].isin(USABLE_STATES)]
    row_w = float((sub["stat"] == 2).mean() * 100) if len(sub) else float("nan")
    per_ch = sub.groupby(["statId", "chgerId"])["stat"].apply(lambda s: (s == 2).mean())
    chg_w = float(per_ch.mean() * 100) if len(per_ch) else float("nan")
    panel_w = float(ats_valid["availability_pct"].mean()) if len(ats_valid) else float("nan")

    hourly = ats_valid.groupby(ats_valid["ts"].dt.hour)["availability_pct"].agg(
        ["mean", "min", "max", "count"]
    )
    hourly.index.name = "hour"

    ats_valid["period"] = np.where(
        ats_valid["ts"].dt.hour.between(7, 22), "주간(07-22)", "야간(23-06)"
    )
    by_period = ats_valid.groupby("period")["availability_pct"].agg(
        ["mean", "min", "max", "count"]
    )

    last_row = panel.iloc[-1].dropna()
    stat_counts = last_row.value_counts().to_dict()
    n_chargers_panel = int(last_row.shape[0])
    usable_last = last_row.isin(USABLE_STATES)
    avail_last = (
        float((last_row == 2).sum() / usable_last.sum() * 100)
        if usable_last.any()
        else float("nan")
    )

    ever = int(all_df.groupby(["statId", "chgerId"]).ngroups)
    ever_st = int(all_df["statId"].nunique())

    q33, q66 = meta_df["rows"].quantile([0.33, 0.66])

    def bucket(r: float) -> str:
        if r < q33:
            return "소형(변화적음)"
        if r < q66:
            return "중형"
        return "대형(변화많음)"

    meta_df["size_class"] = meta_df["rows"].map(bucket)
    size_summary = meta_df.groupby("size_class").agg(
        n=("rows", "count"),
        rows_mean=("rows", "mean"),
        rows_min=("rows", "min"),
        rows_max=("rows", "max"),
    )

    ls_files = sorted(
        p for p in loop3.glob("daegu_traffic_linkspeed_*.csv") if "latest" not in p.name
    )
    inc_files = sorted(
        p for p in loop3.glob("daegu_traffic_incident_*.csv") if "latest" not in p.name
    )
    traffic_rows: list[dict] = []
    for path in ls_files:
        sid = path.stem.replace("daegu_traffic_linkspeed_", "")
        ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        df = pd.read_csv(path)
        speed_col = next(
            (
                c
                for c in df.columns
                if "speed" in c.lower() or c in ("prcsSpeed", "linkSpeed", "speed")
            ),
            None,
        )
        mean_spd = (
            float(pd.to_numeric(df[speed_col], errors="coerce").mean())
            if speed_col
            else float("nan")
        )
        traffic_rows.append(
            {"ts": ts, "rows": len(df), "speed_mean": mean_spd, "file": path.name}
        )
    tr_df = pd.DataFrame(traffic_rows)
    inc_n = []
    for path in inc_files:
        sid = path.stem.replace("daegu_traffic_incident_", "")
        ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        df = pd.read_csv(path)
        inc_n.append({"ts": ts, "rows": len(df)})
    inc_df = pd.DataFrame(inc_n)

    meta_df.to_csv(out / "snapshot_inventory.csv", index=False, encoding="utf-8-sig")
    ats_valid.to_csv(out / "availability_timeseries.csv", index=False, encoding="utf-8-sig")
    hourly.to_csv(out / "availability_hourly.csv", encoding="utf-8-sig")
    if len(tr_df):
        tr_df.to_csv(out / "traffic_linkspeed_summary.csv", index=False, encoding="utf-8-sig")

    summary = {
        "source": "Lightsail 52.79.224.112",
        "pulled_to": str(dest),
        "status": {
            "snapshots": len(files),
            "first_ts": str(meta_df["ts"].iloc[0]),
            "last_ts": str(meta_df["ts"].iloc[-1]),
            "span_hours": round(
                float((meta_df["ts"].iloc[-1] - meta_df["ts"].iloc[0]).total_seconds() / 3600),
                2,
            ),
            "gap_median_min": round(float(gaps.median()), 2) if len(gaps) else None,
            "gap_mean_min": round(float(gaps.mean()), 2) if len(gaps) else None,
            "gap_p95_min": round(float(gaps.quantile(0.95)), 2) if len(gaps) else None,
            "gaps_over_25min": int((gaps > MAX_CONTINUOUS_GAP_MINUTES).sum()) if len(gaps) else 0,
            "rows_total_observations": int(len(all_df)),
            "unique_stations": ever_st,
            "unique_chargers": ever,
            "rows_per_snap_median": int(meta_df["rows"].median()),
            "rows_per_snap_mean": round(float(meta_df["rows"].mean()), 1),
            "call_log_ok": call_ok,
            "call_log_n": len(calls),
            "quota_today": quota,
            "panel_chargers_last": n_chargers_panel,
            "stat_counts_last_panel": {
                str(int(k)): int(v) for k, v in sorted(stat_counts.items()) if pd.notna(k)
            },
        },
        "availability": {
            "definition": "available(stat=2)/(available+in_use) on forward-filled panel",
            "row_weighted_pct": round(row_w, 1),
            "charger_weighted_pct": round(chg_w, 1),
            "panel_weighted_pct": round(panel_w, 1),
            "panel_min_pct": round(float(ats_valid["availability_pct"].min()), 1)
            if len(ats_valid)
            else None,
            "panel_max_pct": round(float(ats_valid["availability_pct"].max()), 1)
            if len(ats_valid)
            else None,
            "panel_last_pct": round(avail_last, 1),
            "usable_known_mean": round(float(ats_valid["usable_known"].mean()), 1)
            if len(ats_valid)
            else None,
            "by_period": {
                k: {
                    "mean": round(float(v["mean"]), 1),
                    "min": round(float(v["min"]), 1),
                    "max": round(float(v["max"]), 1),
                    "n": int(v["count"]),
                }
                for k, v in by_period.to_dict("index").items()
            },
            "hourly_mean": {
                str(int(h)): round(float(v), 1) for h, v in hourly["mean"].items()
            },
        },
        "traffic": {
            "linkspeed_ticks": len(ls_files),
            "incident_ticks": len(inc_files),
            "first_ts": str(tr_df["ts"].iloc[0]) if len(tr_df) else None,
            "last_ts": str(tr_df["ts"].iloc[-1]) if len(tr_df) else None,
            "links_per_tick": int(tr_df["rows"].median()) if len(tr_df) else None,
            "speed_kph_mean_overall": round(float(tr_df["speed_mean"].mean()), 1)
            if len(tr_df) and tr_df["speed_mean"].notna().any()
            else None,
            "incident_rows_mean": round(float(inc_df["rows"].mean()), 2) if len(inc_df) else None,
            "incident_rows_max": int(inc_df["rows"].max()) if len(inc_df) else None,
        },
        "classification": {
            "size_buckets": {
                k: {
                    "n": int(v["n"]),
                    "rows_mean": round(float(v["rows_mean"]), 1),
                    "rows_min": int(v["rows_min"]),
                    "rows_max": int(v["rows_max"]),
                }
                for k, v in size_summary.to_dict("index").items()
            },
            "big_gaps": [
                {
                    "ts": str(r.ts),
                    "gap_min": round(float(r.gap_min), 1),
                    "snapshot_id": r.snapshot_id,
                }
                for r in big_gaps.itertuples()
            ],
        },
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    st = summary["status"]
    a = summary["availability"]
    tr = summary["traffic"]
    lines = [
        "# Lightsail 수집 분류·가용률 보고 (2026-07-23)",
        "",
        f"- **소스**: `{summary['source']}` (PC off 중 systemd 수집)",
        f"- **로컬 복사**: `{dest.name}/`",
        f"- **구간**: {st['first_ts']} → {st['last_ts']} ({st['span_hours']}h)",
        "",
        "## 1. 데이터 분류",
        "",
        "| 레이어 | 건수 | 비고 |",
        "|---|---:|---|",
        f"| loop1 status 스냅샷 | {st['snapshots']} | 5분 간격 · period=10 |",
        f"| loop1 관측 행(누적) | {st['rows_total_observations']:,} | 변화분만 반환 |",
        f"| 고유 충전소 / 충전기 | {st['unique_stations']:,} / {st['unique_chargers']:,} | 패널 말단 충전기 {st['panel_chargers_last']:,} |",
        f"| loop3 linkspeed | {tr['linkspeed_ticks']} | 15분 · 링크 ≈{tr['links_per_tick']} |",
        f"| loop3 incident | {tr['incident_ticks']} | 평균 {tr['incident_rows_mean']}건/틱 |",
        "",
        "### status 스냅샷 크기 분류 (변화량)",
        "",
        "| 클래스 | 스냅샷 수 | 평균 행 | 범위 |",
        "|---|---:|---:|---|",
    ]
    for k, v in summary["classification"]["size_buckets"].items():
        lines.append(
            f"| {k} | {v['n']} | {v['rows_mean']} | {v['rows_min']}–{v['rows_max']} |"
        )
    lines += [
        "",
        "### 수집 품질 (간격)",
        "",
        f"- gap 중앙값 **{st['gap_median_min']}분** / 평균 {st['gap_mean_min']}분 / P95 {st['gap_p95_min']}분",
        f"- 25분 초과 공백: **{st['gaps_over_25min']}회**",
    ]
    if summary["classification"]["big_gaps"]:
        for g in summary["classification"]["big_gaps"][:10]:
            lines.append(f"  - {g['ts']} (+{g['gap_min']}분)")
    else:
        lines.append("- 연속 구간으로 패널 forward-fill 가능 (공백 없음)")
    lines += [
        f"- API 호출 로그: ok {st['call_log_ok']}/{st['call_log_n']} · 당일 quota `{st['quota_today']}`",
        "",
        "## 2. 가용률 (핵심)",
        "",
        "정의: 패널(충전기 1대=1표, 미반환=상태 유지 forward-fill) 기준",
        "`가용률 = 충전가능(stat=2) / (충전가능+충전중)`",
        "",
        "| 산출 방식 | 가용률 | 해석 |",
        "|---|---:|---|",
        f"| **패널(권장)** | **{a['panel_weighted_pct']}%** | 바쁜 충전기 과대표집 보정 |",
        f"| 행 가중(raw) | {a['row_weighted_pct']}% | 변화 많은 기기 과다 반영 → 편향 |",
        f"| 충전기 평균 | {a['charger_weighted_pct']}% | 관측 빈도 무시 |",
        "",
        f"- 패널 범위: **{a['panel_min_pct']}% ~ {a['panel_max_pct']}%** · 말단 시점 **{a['panel_last_pct']}%**",
        f"- 스냅샷당 사용가능 상태로 알려진 충전기 평균: **{a['usable_known_mean']}대**",
        "",
        "### 주간 vs 야간",
        "",
        "| 구간 | 평균 | 최소 | 최대 | 스냅샷 |",
        "|---|---:|---:|---:|---:|",
    ]
    for k, v in a["by_period"].items():
        lines.append(
            f"| {k} | {v['mean']}% | {v['min']}% | {v['max']}% | {v['n']} |"
        )
    lines += [
        "",
        "### 시간대별 평균 가용률",
        "",
        "| 시 | 가용률 |",
        "|---:|---:|",
    ]
    for h, v in sorted(a["hourly_mean"].items(), key=lambda x: int(x[0])):
        lines.append(f"| {h}시 | {v}% |")
    lines += [
        "",
        "### 말단 패널 상태 분포",
        "",
        "| stat | 의미 | 대수 |",
        "|---:|---|---:|",
    ]
    for k, v in st["stat_counts_last_panel"].items():
        lab = STAT_LABEL.get(int(k), "?")
        lines.append(f"| {k} | {lab} | {v} |")
    lines += [
        "",
        "## 3. 소통(loop3) 요약",
        "",
        f"- 구간: {tr['first_ts']} → {tr['last_ts']}",
        f"- 링크 평균속도(틱 평균의 평균): **{tr['speed_kph_mean_overall']} km/h**",
        f"- 돌발 건수: 평균 {tr['incident_rows_mean']} · 최대 {tr['incident_rows_max']}",
        "- 링크 좌표 부재 → 충전소 공간조인은 여전히 후속 과제",
        "",
        "## 4. 한줄 결론",
        "",
        (
            f"Lightsail 5분 status가 **{st['span_hours']}시간·{st['snapshots']}스냅샷** 연속 적재됐고, "
            f"패널 가용률 평균 **{a['panel_weighted_pct']}%** "
            f"(범위 {a['panel_min_pct']}–{a['panel_max_pct']}%). "
            f"raw 행가중 {a['row_weighted_pct']}%는 과대 편향이므로 MVP/리포트는 패널 값을 쓴다."
        ),
        "",
        "산출물: `report/summary.json`, `snapshot_inventory.csv`, `availability_timeseries.csv`, `availability_hourly.csv`",
        "",
        "```",
        "DA➀ | lightsail pull + availability report | 2026-07-23",
        "```",
        "",
    ]
    md = "\n".join(lines)
    (out / "가용률_보고_20260723.md").write_text(md, encoding="utf-8")
    docs_md = REPO / "docs" / "Lightsail_가용률보고_20260723.md"
    docs_md.write_text(md, encoding="utf-8")

    print(
        json.dumps(
            {
                "snapshots": st["snapshots"],
                "span_h": st["span_hours"],
                "gap_med": st["gap_median_min"],
                "panel_avail": a["panel_weighted_pct"],
                "panel_range": [a["panel_min_pct"], a["panel_max_pct"]],
                "row_w": a["row_weighted_pct"],
                "traffic_ticks": tr["linkspeed_ticks"],
                "speed": tr["speed_kph_mean_overall"],
                "report": str(docs_md),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

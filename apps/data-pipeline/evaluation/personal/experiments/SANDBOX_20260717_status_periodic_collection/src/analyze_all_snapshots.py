"""Analyze all collected status snapshots (live loop1 + Lightsail archive pulls)."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(REPO / "apps" / "data-pipeline"))

from build_panel import (  # noqa: E402
    MAX_CONTINUOUS_GAP_MINUTES,
    availability_timeseries,
    build_state_panel,
)
from load_snapshots import load_snapshot  # noqa: E402
from loop_paths import LOOP1_DIR, LOOP1_INDEX, LOOP1_LOGS, LOOPS_ARCHIVE, iter_status_csvs  # noqa: E402

OUT_DIR = REPO / "docs" / "data" / "analysis" / "snapshot_all_20260723"
REPORT_MD = REPO / "docs" / "보고" / "스냅샷_전체분석_20260723.md"

STAT_LABEL = {
    1: "통신이상",
    2: "충전가능",
    3: "충전중",
    4: "운영중지",
    5: "점검중",
    9: "상태미확인",
}


def _snapshot_dirs() -> list[tuple[str, Path]]:
    dirs: list[tuple[str, Path]] = [("live_loop1", LOOP1_DIR / "snapshots")]
    if LOOPS_ARCHIVE.is_dir():
        for arch in sorted(LOOPS_ARCHIVE.glob("from_lightsail_*"), reverse=True):
            snap = arch / "loop1" / "snapshots"
            if snap.is_dir():
                dirs.append((arch.name, snap))
    return [(name, p) for name, p in dirs if p.is_dir()]


def collect_unique_files() -> dict[str, tuple[str, Path]]:
    """snapshotId -> (source, path). Prefer live over archive."""
    best: dict[str, tuple[int, str, Path]] = {}
    for name, d in _snapshot_dirs():
        pri = 0 if name == "live_loop1" else 1
        for path in iter_status_csvs(d):
            sid = path.stem.replace("daegu_charger_status_", "")
            cur = best.get(sid)
            if cur is None or pri < cur[0]:
                best[sid] = (pri, name, path)
    return {sid: (src, path) for sid, (_, src, path) in best.items()}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    unique = collect_unique_files()
    if not unique:
        print("NO SNAPSHOTS")
        return 1

    frames: list[pd.DataFrame] = []
    meta_rows: list[dict] = []
    src_counts: dict[str, int] = defaultdict(int)

    for sid in sorted(unique.keys()):
        src, path = unique[sid]
        src_counts[src] += 1
        df = load_snapshot(path)
        if "snapshotId" not in df.columns or df["snapshotId"].isna().all():
            df["snapshotId"] = sid
        else:
            df["snapshotId"] = df["snapshotId"].astype(str)
        df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
        ts = pd.to_datetime(sid, format="%Y%m%d_%H%M%S")
        frames.append(df)
        vc = df["stat"].value_counts(dropna=False).to_dict()
        meta_rows.append(
            {
                "snapshot_id": sid,
                "ts": ts,
                "source": src,
                "rows": len(df),
                "stations": int(df["statId"].nunique()),
                "chargers": int(df.groupby(["statId", "chgerId"]).ngroups),
                "stat_2": int(vc.get(2, 0)),
                "stat_3": int(vc.get(3, 0)),
                "stat_other": int(sum(v for k, v in vc.items() if k not in (2, 3))),
            }
        )

    all_df = pd.concat(frames, ignore_index=True)
    meta = pd.DataFrame(meta_rows).sort_values("ts").reset_index(drop=True)
    meta["gap_min"] = meta["ts"].diff().dt.total_seconds() / 60
    meta["date"] = meta["ts"].dt.date.astype(str)
    meta["hour"] = meta["ts"].dt.hour

    gaps = meta["gap_min"].dropna()
    big = meta.loc[meta["gap_min"] > MAX_CONTINUOUS_GAP_MINUTES, ["ts", "gap_min", "snapshot_id"]]

    # size classes by row count tertiles
    q1, q2 = meta["rows"].quantile([1 / 3, 2 / 3])
    def _cls(r: float) -> str:
        if r <= q1:
            return "소형"
        if r <= q2:
            return "중형"
        return "대형"

    meta["size_class"] = meta["rows"].map(_cls)

    print("building panel...")
    panel = build_state_panel(all_df)
    ats = availability_timeseries(panel)
    ats_valid = ats.dropna(subset=["availability_pct"]).copy()
    ats_valid["availability"] = ats_valid["availability_pct"] / 100.0

    # by date coverage
    by_date = (
        meta.groupby("date")
        .agg(
            snapshots=("snapshot_id", "count"),
            rows_sum=("rows", "sum"),
            gap_med=("gap_min", "median"),
            gap_max=("gap_min", "max"),
            gaps_gt25=("gap_min", lambda s: int((s.dropna() > 25).sum())),
            first_ts=("ts", "min"),
            last_ts=("ts", "max"),
        )
        .reset_index()
    )

    # merge availability by date
    if not ats_valid.empty:
        ats_valid["date"] = ats_valid["ts"].dt.date.astype(str)
        avail_by_date = (
            ats_valid.groupby("date")["availability"]
            .agg(["mean", "min", "max", "count"])
            .reset_index()
            .rename(columns={"mean": "avail_mean", "min": "avail_min", "max": "avail_max", "count": "avail_ticks"})
        )
        by_date = by_date.merge(avail_by_date, on="date", how="left")

    # night vs day
    if not ats_valid.empty:
        ats_valid["tod"] = np.where(ats_valid["ts"].dt.hour.between(7, 22), "주간(07-22)", "야간(23-06)")
        tod = (
            ats_valid.groupby("tod")["availability"]
            .agg(["mean", "min", "max", "count"])
            .reset_index()
        )
    else:
        tod = pd.DataFrame()

    # raw vs panel availability (overall)
    usable = all_df[all_df["stat"].isin([2, 3])]
    raw_avail = float((usable["stat"] == 2).mean()) if len(usable) else None
    panel_avail = float(ats_valid["availability"].mean()) if len(ats_valid) else None

    # call log (live only)
    call_ok = call_n = None
    call_path = LOOP1_LOGS / "call_log.jsonl"
    if call_path.exists():
        ok = n = 0
        for line in call_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n += 1
            try:
                rec = json.loads(line)
                if rec.get("ok") is True or rec.get("http_status") == 200:
                    ok += 1
            except json.JSONDecodeError:
                pass
        call_ok, call_n = ok, n

    # persist tables
    meta.to_csv(OUT_DIR / "snapshot_inventory.csv", index=False, encoding="utf-8-sig")
    by_date.to_csv(OUT_DIR / "by_date.csv", index=False, encoding="utf-8-sig")
    if not ats_valid.empty:
        ats_valid.to_csv(OUT_DIR / "availability_timeseries.csv", index=False, encoding="utf-8-sig")
    if not tod.empty:
        tod.to_csv(OUT_DIR / "availability_tod.csv", index=False, encoding="utf-8-sig")
    big.to_csv(OUT_DIR / "big_gaps.csv", index=False, encoding="utf-8-sig")

    summary = {
        "unique_snapshots": len(meta),
        "source_counts": dict(src_counts),
        "span_hours": float((meta["ts"].iloc[-1] - meta["ts"].iloc[0]).total_seconds() / 3600),
        "first_ts": str(meta["ts"].iloc[0]),
        "last_ts": str(meta["ts"].iloc[-1]),
        "event_rows": int(len(all_df)),
        "unique_stations": int(all_df["statId"].nunique()),
        "unique_chargers": int(all_df.groupby(["statId", "chgerId"]).ngroups),
        "gap_median_min": float(gaps.median()) if len(gaps) else None,
        "gap_mean_min": float(gaps.mean()) if len(gaps) else None,
        "gap_p95_min": float(gaps.quantile(0.95)) if len(gaps) else None,
        "gaps_gt_25": int(len(big)),
        "panel_avail_mean": panel_avail,
        "raw_avail_mean": raw_avail,
        "panel_avail_min": float(ats_valid["availability"].min()) if len(ats_valid) else None,
        "panel_avail_max": float(ats_valid["availability"].max()) if len(ats_valid) else None,
        "panel_chargers_end": int(panel.iloc[-1].notna().sum()) if len(panel) else 0,
        "call_log_ok": call_ok,
        "call_log_n": call_n,
        "live_index_rows": int(sum(1 for _ in LOOP1_INDEX.open(encoding="utf-8")) - 1)
        if LOOP1_INDEX.exists()
        else None,
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    size_tbl = (
        meta.groupby("size_class")["rows"]
        .agg(["count", "mean", "min", "max"])
        .reindex(["소형", "중형", "대형"])
    )

    lines = [
        "# status 스냅샷 전체 분석 (2026-07-23)",
        "",
        "- **범위**: live `loop1/snapshots` + `_archive/from_lightsail_20260723(_pm)` **고유 snapshotId 합집합**",
        "- **중복**: 같은 ID면 live 우선",
        f"- **구간**: `{summary['first_ts']}` → `{summary['last_ts']}` ({summary['span_hours']:.2f}h)",
        "",
        "## 1. 규모",
        "",
        "| 항목 | 값 |",
        "|---|---:|",
        f"| 고유 스냅샷 | {summary['unique_snapshots']} |",
        f"| 소스 live / archive_pm / archive_am | {src_counts.get('live_loop1', 0)} / {src_counts.get('archive_pm', 0)} / {src_counts.get('archive_am', 0)} |",
        f"| 이벤트 행(누적) | {summary['event_rows']:,} |",
        f"| 고유 충전소 / 충전기 | {summary['unique_stations']:,} / {summary['unique_chargers']:,} |",
        f"| 패널 말단 관측 충전기 | {summary['panel_chargers_end']:,} |",
        f"| live index 행 | {summary['live_index_rows']} |",
        "",
        "### 일자별",
        "",
        "| 날짜 | 스냅샷 | 이벤트행합 | gap중앙(분) | gap최대 | gap>25 | 패널가용률 평균 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in by_date.iterrows():
        am = f"{r['avail_mean']*100:.1f}%" if pd.notna(r.get("avail_mean")) else "—"
        lines.append(
            f"| {r['date']} | {int(r['snapshots'])} | {int(r['rows_sum']):,} | "
            f"{r['gap_med']:.2f} | {r['gap_max']:.1f} | {int(r['gaps_gt25'])} | {am} |"
        )

    lines += [
        "",
        "### 스냅샷 크기(변화량) 분류",
        "",
        "| 클래스 | 개수 | 평균 행 | 범위 |",
        "|---|---:|---:|---|",
    ]
    for cls, r in size_tbl.iterrows():
        if pd.isna(r["count"]):
            continue
        lines.append(
            f"| {cls} | {int(r['count'])} | {r['mean']:.1f} | {int(r['min'])}–{int(r['max'])} |"
        )

    lines += [
        "",
        "## 2. 수집 품질 (간격)",
        "",
        f"- gap 중앙값 **{summary['gap_median_min']:.2f}분** / 평균 {summary['gap_mean_min']:.2f}분 / P95 {summary['gap_p95_min']:.2f}분",
        f"- 25분 초과 공백: **{summary['gaps_gt_25']}회**",
    ]
    if len(big):
        lines.append("")
        lines.append("| 시각 | gap(분) | snapshot |")
        lines.append("|---|---:|---|")
        for _, r in big.head(20).iterrows():
            lines.append(f"| {r['ts']} | {r['gap_min']:.1f} | `{r['snapshot_id']}` |")
        if len(big) > 20:
            lines.append(f"| … | … | (총 {len(big)}건, `big_gaps.csv`) |")

    if call_n:
        lines.append(f"- live call_log: ok {call_ok}/{call_n}")

    lines += [
        "",
        "## 3. 가용률",
        "",
        "정의: 패널(충전기 1대=1표, 미반환=상태 유지 forward-fill, gap>25분이면 세그먼트 끊음)",
        "`가용률 = 충전가능(2) / (충전가능+충전중)`",
        "",
        "| 방식 | 가용률 |",
        "|---|---:|",
        f"| **패널(권장)** | **{panel_avail*100:.1f}%** |" if panel_avail is not None else "| 패널 | — |",
        f"| 행 가중(raw) | {raw_avail*100:.1f}% |" if raw_avail is not None else "| raw | — |",
    ]
    if panel_avail is not None:
        lines.append(
            f"- 패널 범위: **{summary['panel_avail_min']*100:.1f}% ~ {summary['panel_avail_max']*100:.1f}%**"
        )

    if not tod.empty:
        lines += ["", "### 주간 vs 야간", "", "| 구간 | 평균 | 최소 | 최대 | 틱 |", "|---|---:|---:|---:|---:|"]
        for _, r in tod.iterrows():
            lines.append(
                f"| {r['tod']} | {r['mean']*100:.1f}% | {r['min']*100:.1f}% | {r['max']*100:.1f}% | {int(r['count'])} |"
            )

    lines += [
        "",
        "## 4. 해석",
        "",
        "- live `loop1`은 로컬 수집 구간(대략 7/17~7/22 밤)이 중심이고, **7/22 밤~7/23 오후**는 Lightsail archive pull이 채움.",
        "- 변경분 API라 스냅샷 행 수는 ‘그 시각 전체 충전기’가 아니라 **period 내 변화분**.",
        "- 가용률은 **패널 기준**을 쓸 것 (raw는 바쁜 기기 과대표집).",
        "",
        "## 5. 산출물",
        "",
        f"- 보고: `{REPORT_MD.relative_to(REPO).as_posix()}`",
        f"- 표: `{OUT_DIR.relative_to(REPO).as_posix()}/`",
        "",
        "```",
        "DA➀ | snapshot all analysis | 2026-07-23",
        "```",
        "",
    ]

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"WROTE {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

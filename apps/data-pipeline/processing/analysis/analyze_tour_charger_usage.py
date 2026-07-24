"""Tour ↔ nearby chargers + holiday/weekend usage lift (batch, daily-friendly).

Links each TourAPI attraction to nearby EvCharger stations, then compares
daily usage on weekdays vs weekends vs KR public holidays.

Not a 5-min Lightsail collection loop — run once / daily when inputs refresh.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_USAGE, EXTRACTED_DAILY, EXTRACTED_TOUR

OUT_DIR = REPO / "docs" / "data" / "analysis" / "tour_charger_usage"
REPORT = REPO / "docs" / "관광지_주변충전_이용분석_20260723.md"

PRIMARY_R = 500
# keep nearest stations even if radius empty of usage — for pair table
MAX_PAIRS_PER_TOUR = 8


# Minimal KR public holidays (no external package). Extend as needed.
def kr_holidays(years: range | list[int]) -> set[date]:
    fixed = [
        (1, 1),  # 신정
        (3, 1),  # 삼일절
        (5, 5),  # 어린이날
        (6, 6),  # 현충일
        (8, 15),  # 광복절
        (10, 3),  # 개천절
        (10, 9),  # 한글날
        (12, 25),  # 성탄
    ]
    # Lunar / substitute / temporary (approx observed dates used in KR calendars)
    lunar_etc = {
        2024: [
            date(2024, 2, 9),
            date(2024, 2, 10),
            date(2024, 2, 11),
            date(2024, 2, 12),  # 설 연휴
            date(2024, 4, 10),  # 국회의원선거
            date(2024, 5, 6),  # 어린이날 대체
            date(2024, 5, 15),  # 부처님오신날
            date(2024, 9, 16),
            date(2024, 9, 17),
            date(2024, 9, 18),  # 추석
        ],
        2025: [
            date(2025, 1, 28),
            date(2025, 1, 29),
            date(2025, 1, 30),  # 설
            date(2025, 3, 3),  # 삼일절 대체
            date(2025, 5, 5),
            date(2025, 5, 6),  # 부처님오신날 연휴 성격
            date(2025, 10, 5),
            date(2025, 10, 6),
            date(2025, 10, 7),
            date(2025, 10, 8),  # 추석 연휴
        ],
        2026: [
            date(2026, 2, 16),
            date(2026, 2, 17),
            date(2026, 2, 18),  # 설
            date(2026, 5, 24),  # 부처님오신날
            date(2026, 5, 25),  # 대체
            date(2026, 9, 24),
            date(2026, 9, 25),
            date(2026, 9, 26),  # 추석
        ],
    }
    out: set[date] = set()
    for y in years:
        for m, d in fixed:
            out.add(date(y, m, d))
        out.update(lunar_etc.get(y, []))
    return out


def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dl = np.radians(lng2 - lng1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def day_bucket(d: date, hol: set[date]) -> str:
    if d in hol:
        return "holiday"
    if d.weekday() >= 5:
        return "weekend"
    return "weekday"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    tour = pd.read_csv(
        EXTRACTED_TOUR / "daegu_tour_attractions_20260717_194107.csv", dtype=str
    )
    tour["lat"] = pd.to_numeric(tour["mapy"], errors="coerce")
    tour["lng"] = pd.to_numeric(tour["mapx"], errors="coerce")
    tour = tour.dropna(subset=["lat", "lng"]).drop_duplicates("contentid").reset_index(drop=True)

    info = pd.read_csv(
        EXTRACTED_DAILY / "2026-07-22" / "daegu_charger_info_20260722_latest.csv",
        dtype=str,
    )
    info["lat"] = pd.to_numeric(info["lat"], errors="coerce")
    info["lng"] = pd.to_numeric(info["lng"], errors="coerce")
    info = info.dropna(subset=["lat", "lng", "statId"])
    stations = info.groupby("statId", as_index=False).agg(
        statNm=("statNm", "first"),
        lat=("lat", "first"),
        lng=("lng", "first"),
        n_chargers=("chgerId", "nunique"),
    )

    join = pd.read_csv(REPO / "docs/data/spatial_join/join_usage_history_statId.csv", dtype=str)
    join = join[join["matched"].astype(str).str.lower().isin(["true", "1"])]
    usage = pd.read_csv(
        EXTRACTED_CHARGER_USAGE / "daegu_charger_usage_daily_20260331.csv",
        encoding="cp949",
        dtype=str,
    )
    colmap = {
        "일자": "date",
        "충전소아이디": "station_id_daegu",
        "사용횟수": "sessions",
        "충전량": "kwh",
    }
    usage = usage.rename(columns={k: v for k, v in colmap.items() if k in usage.columns})
    usage["sessions"] = pd.to_numeric(usage["sessions"], errors="coerce").fillna(0.0)
    usage["kwh"] = pd.to_numeric(usage["kwh"], errors="coerce").fillna(0.0)
    usage["date"] = pd.to_datetime(usage["date"], errors="coerce")
    usage = usage.dropna(subset=["date", "station_id_daegu"])

    u_stat = usage.merge(
        join[["station_id_daegu", "statId"]].drop_duplicates("station_id_daegu"),
        on="station_id_daegu",
        how="inner",
    )
    # station × day
    daily = (
        u_stat.groupby(["statId", "date"], as_index=False)
        .agg(sessions=("sessions", "sum"), kwh=("kwh", "sum"))
    )
    years = sorted(daily["date"].dt.year.dropna().unique().astype(int).tolist())
    hol = kr_holidays(years)
    daily["day_type"] = daily["date"].dt.date.map(lambda d: day_bucket(d, hol))

    # control: all matched stations by day type
    control = (
        daily.groupby("day_type")["sessions"]
        .mean()
        .rename("control_sessions_mean")
        .to_dict()
    )

    dmat = haversine_m(
        tour["lat"].to_numpy()[:, None],
        tour["lng"].to_numpy()[:, None],
        stations["lat"].to_numpy()[None, :],
        stations["lng"].to_numpy()[None, :],
    )

    pair_rows: list[dict] = []
    tour_rows: list[dict] = []
    daytype_rows: list[dict] = []

    for i, tr in tour.iterrows():
        dists = dmat[i]
        within = np.where(dists <= PRIMARY_R)[0]
        # if none within radius, still take nearest 3 for inspection
        if len(within) == 0:
            within = np.argsort(dists)[:3]
            link_mode = "nearest_fallback"
        else:
            # prefer closer; cap
            order = within[np.argsort(dists[within])][:MAX_PAIRS_PER_TOUR]
            within = order
            link_mode = f"within_{PRIMARY_R}m"

        near = stations.iloc[within].copy()
        near["distance_m"] = dists[within]

        linked_ids = set(near["statId"].tolist())
        near_daily = daily[daily["statId"].isin(linked_ids)].copy()

        # per-station link + usage summary
        for _, st in near.iterrows():
            sid = st["statId"]
            sd = near_daily[near_daily["statId"] == sid]
            by_t = sd.groupby("day_type")["sessions"].agg(["mean", "sum", "count"])
            wd = float(by_t.loc["weekday", "mean"]) if "weekday" in by_t.index else float("nan")
            we = float(by_t.loc["weekend", "mean"]) if "weekend" in by_t.index else float("nan")
            ho = float(by_t.loc["holiday", "mean"]) if "holiday" in by_t.index else float("nan")
            pair_rows.append(
                {
                    "contentid": tr["contentid"],
                    "tour_title": tr["title"],
                    "statId": sid,
                    "statNm": st["statNm"],
                    "distance_m": round(float(st["distance_m"]), 1),
                    "n_chargers": int(st["n_chargers"]),
                    "link_mode": link_mode,
                    "has_usage_days": int(len(sd)),
                    "sessions_mean_weekday": round(wd, 3) if pd.notna(wd) else None,
                    "sessions_mean_weekend": round(we, 3) if pd.notna(we) else None,
                    "sessions_mean_holiday": round(ho, 3) if pd.notna(ho) else None,
                    "holiday_vs_weekday": round(ho / wd, 3)
                    if pd.notna(ho) and pd.notna(wd) and wd > 0
                    else None,
                    "weekend_vs_weekday": round(we / wd, 3)
                    if pd.notna(we) and pd.notna(wd) and wd > 0
                    else None,
                }
            )

        # tour-level: pool nearby stations' daily rows
        if len(near_daily):
            # average sessions across linked stations per calendar day, then by day_type
            per_day = near_daily.groupby(["date", "day_type"], as_index=False)["sessions"].mean()
            g = per_day.groupby("day_type")["sessions"].agg(["mean", "median", "count", "sum"])
        else:
            g = pd.DataFrame(columns=["mean", "median", "count", "sum"])

        def gget(t: str, col: str):
            if t in g.index:
                return float(g.loc[t, col])
            return float("nan")

        wd_m, we_m, ho_m = gget("weekday", "mean"), gget("weekend", "mean"), gget("holiday", "mean")
        tour_rows.append(
            {
                "contentid": tr["contentid"],
                "title": tr["title"],
                "addr1": tr.get("addr1"),
                "lat": tr["lat"],
                "lng": tr["lng"],
                "link_mode": link_mode,
                "linked_stations": int(len(near)),
                "linked_with_usage": int(near["statId"].isin(daily["statId"].unique()).sum()),
                "sessions_mean_weekday": round(wd_m, 3) if pd.notna(wd_m) else None,
                "sessions_mean_weekend": round(we_m, 3) if pd.notna(we_m) else None,
                "sessions_mean_holiday": round(ho_m, 3) if pd.notna(ho_m) else None,
                "holiday_vs_weekday": round(ho_m / wd_m, 3)
                if pd.notna(ho_m) and pd.notna(wd_m) and wd_m > 0
                else None,
                "weekend_vs_weekday": round(we_m / wd_m, 3)
                if pd.notna(we_m) and pd.notna(wd_m) and wd_m > 0
                else None,
                "holiday_days": int(gget("holiday", "count")) if pd.notna(gget("holiday", "count")) else 0,
                "weekday_days": int(gget("weekday", "count")) if pd.notna(gget("weekday", "count")) else 0,
                "weekend_days": int(gget("weekend", "count")) if pd.notna(gget("weekend", "count")) else 0,
            }
        )

        for tname in ("weekday", "weekend", "holiday"):
            daytype_rows.append(
                {
                    "contentid": tr["contentid"],
                    "title": tr["title"],
                    "day_type": tname,
                    "sessions_mean": tour_rows[-1].get(f"sessions_mean_{tname}"),
                    "n_days": tour_rows[-1].get(f"{tname}_days"),
                    "control_mean": round(float(control.get(tname, float("nan"))), 3),
                }
            )

    pairs = pd.DataFrame(pair_rows)
    toursum = pd.DataFrame(tour_rows)
    daytype = pd.DataFrame(daytype_rows)

    pairs.to_csv(OUT_DIR / "tour_station_links.csv", index=False, encoding="utf-8-sig")
    toursum.to_csv(OUT_DIR / "tour_daytype_summary.csv", index=False, encoding="utf-8-sig")
    daytype.to_csv(OUT_DIR / "tour_daytype_long.csv", index=False, encoding="utf-8-sig")

    # who has holiday lift?
    lifted = toursum.dropna(subset=["holiday_vs_weekday"]).sort_values(
        "holiday_vs_weekday", ascending=False
    )
    lifted_ge = lifted[lifted["holiday_vs_weekday"] >= 1.1]
    weekend_lift = toursum.dropna(subset=["weekend_vs_weekday"]).sort_values(
        "weekend_vs_weekday", ascending=False
    )

    # station-level holiday lift among linked pairs with enough days
    pair_lift = pairs.dropna(subset=["holiday_vs_weekday"]).sort_values(
        "holiday_vs_weekday", ascending=False
    )

    meta = {
        "generated_at": now,
        "primary_radius_m": PRIMARY_R,
        "tour_n": int(len(tour)),
        "stations_n": int(len(stations)),
        "refresh": "daily_batch_recommended",
        "not_a_collection_loop": True,
        "control_sessions_mean": {k: round(float(v), 3) for k, v in control.items()},
        "holidays_in_range": len(hol),
        "tours_with_holiday_lift_ge_1_1": int(len(lifted_ge)),
        "usage_date_min": str(daily["date"].min().date()),
        "usage_date_max": str(daily["date"].max().date()),
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 관광지 ↔ 주변 충전소 · 공휴일/주말 이용 분석",
        "",
        "| | |",
        "|---|---|",
        "| **작성** | 2026-07-23 · AI·데이터 ① |",
        "| **목적** | 관광지에 **특정 충전소를 연결**한 뒤, **공휴일·주말에 더 쓰이는지** 확인 |",
        f"| **연결** | 반경 **{PRIMARY_R}m** (없으면 최근접 3곳) · 관광지당 최대 {MAX_PAIRS_PER_TOUR}소 |",
        f"| **이용 기간** | {meta['usage_date_min']} ~ {meta['usage_date_max']} |",
        f"| **공휴일 달력** | KR 고정+설/추석 등 {meta['holidays_in_range']}일 (내장 목록) |",
        "",
        "## 0. 운영 — 서버 5분 루프? / 주간?",
        "",
        "**수집 루프(status·소통)와 다름.** 이건 연결·집계 배치다.",
        "",
        "| | 권장 |",
        "|---|---|",
        "| **재실행** | **일간** (Tour 재추출·이용 CSV 갱신 있는 날 포함) |",
        "| 주간만 | 비추천 — 공휴일 효과는 **일 단위** 라벨이라 일간이 맞음 |",
        "| Lightsail 5분 systemd | **하지 않음** (숫자에 의미 없는 중복 연산) |",
        "| 선택 | 서버에 **매일 1회 cron**으로 리포트만 갱신 |",
        "",
        "## 1. 방법",
        "",
        "```text",
        "관광지 (TourAPI 좌표)",
        "   └─ 주변 특정 충전소 연결 (500m / fallback 최근접)",
        "          └─ 그 소들의 일별 이용",
        "                 ├─ weekday (평일)",
        "                 ├─ weekend (토·일, 공휴일 제외)",
        "                 └─ holiday (공휴일·대체공휴일)",
        "```",
        "",
        "지표: `holiday_vs_weekday` = 공휴일 일평균 세션 / 평일 일평균 세션  ",
        "(>1 이면 공휴일에 더 많이 씀)",
        "",
        f"전체(관광 무관) 대조 일평균 세션: 평일 {control.get('weekday', float('nan')):.3f} · "
        f"주말 {control.get('weekend', float('nan')):.3f} · 공휴일 {control.get('holiday', float('nan')):.3f}",
        "",
        "## 2. 관광지 단위 — 공휴일에 더 쓰이나?",
        "",
        f"- 공휴일/평일 비율을 계산할 수 있는 관광지: **{len(lifted)}**",
        f"- 그중 `holiday_vs_weekday` ≥ 1.1 (공휴일 +10%↑): **{len(lifted_ge)}**",
        "",
        "### 공휴일 리프트 TOP 10 (관광지)",
        "",
        "| 관광지 | 연결 소 | 평일 | 주말 | 공휴일 | 공휴일/평일 | 주말/평일 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in lifted.head(10).iterrows():
        lines.append(
            f"| {r['title']} | {int(r['linked_stations'])} | {r['sessions_mean_weekday']} | "
            f"{r['sessions_mean_weekend']} | {r['sessions_mean_holiday']} | "
            f"**{r['holiday_vs_weekday']}** | {r['weekend_vs_weekday']} |"
        )

    lines += [
        "",
        "### 주말 리프트 TOP 5 (참고)",
        "",
        "| 관광지 | 주말/평일 | 공휴일/평일 |",
        "|---|---:|---:|",
    ]
    for _, r in weekend_lift.head(5).iterrows():
        lines.append(
            f"| {r['title']} | {r['weekend_vs_weekday']} | {r['holiday_vs_weekday']} |"
        )

    lines += [
        "",
        "## 3. 충전소 단위 — 관광지에 붙은 특정 소",
        "",
        "연결표(`tour_station_links.csv`)에서 공휴일 리프트가 큰 **개별 충전소** TOP 10:",
        "",
        "| 관광지 | 충전소 | 거리m | 평일 | 공휴일 | 공휴일/평일 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, r in pair_lift.head(10).iterrows():
        lines.append(
            f"| {r['tour_title']} | {r['statNm']} ({r['statId']}) | {r['distance_m']} | "
            f"{r['sessions_mean_weekday']} | {r['sessions_mean_holiday']} | **{r['holiday_vs_weekday']}** |"
        )

    lines += [
        "",
        "## 4. 해석",
        "",
        "1. **연결이 먼저** — 관광지↔특정 `statId`를 고정해야 “공휴일에 그 소가 더 쓰이나”를 말할 수 있다.",
        "2. **공휴일 ≠ 주말** — 둘을 나눠야 관광 수요 힌트가 된다.",
        "3. 시 이용 조인(약 200소) 밖이면 비율이 비어 있음 → 커버리지 한계.",
        "4. 리프트 >1 이어도 **인과(관광 때문에)** 단정 금지. 입지·상권 공통 효과 가능 → 대조군·후속 status 피크와 같이 볼 것.",
        "",
        "## 5. 산출물",
        "",
        "| 파일 | 내용 |",
        "|---|---|",
        "| `docs/보고/관광지_주변충전_이용분석_20260723.md` | 본 보고서 |",
        "| `.../tour_station_links.csv` | 관광지–충전소 **연결** + 평일/주말/공휴일 |",
        "| `.../tour_daytype_summary.csv` | 관광지 단위 요약 |",
        "| `.../tour_daytype_long.csv` | day_type long form |",
        "",
        "```",
        "python apps/data-pipeline/processing/analysis/analyze_tour_charger_usage.py",
        "# 권장: 일 1회 또는 입력 CSV 갱신 시",
        "```",
        "",
        "```",
        "DA➀ | tour-station holiday lift | 2026-07-23 | daily batch",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                **meta,
                "top_holiday_tour": lifted.iloc[0]["title"] if len(lifted) else None,
                "top_holiday_ratio": float(lifted.iloc[0]["holiday_vs_weekday"]) if len(lifted) else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

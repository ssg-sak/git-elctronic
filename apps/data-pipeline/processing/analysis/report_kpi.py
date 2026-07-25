"""Generate / refresh docs/data/운영/KPI_보고서.md from live DA➀ artifacts.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/report_kpi.py

Reads: status index/quota, UTIC meta, join meta, D1 snapshot, usage join meta.
Writes: docs/data/운영/KPI_보고서.md (+ JSON sidecar under evaluation/results/)
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import LOOP1_INDEX, LOOP1_LOGS, iter_status_csvs, loop2_dir, status_snapshots_dir

KST = ZoneInfo("Asia/Seoul")
OUT_MD = REPO / "docs" / "data" / "운영" / "KPI_보고서.md"
OUT_JSON = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "kpi_report_latest.json"
CRITERIA = "docs/data/운영/KPI.md"


def _now() -> datetime:
    return datetime.now(KST)


def status_today(today: date) -> dict:
    idx_path = LOOP1_INDEX
    out: dict = {
        "ticks": 0,
        "first": None,
        "last": None,
        "gap_median_min": None,
        "gap_max_min": None,
        "gaps_gt_12": 0,
        "latest_snapshot": None,
        "latest_rows": None,
        "latest_avail_pct": None,
    }
    if idx_path.exists():
        idx = pd.read_csv(idx_path)
        col0 = idx.columns[0]
        idx["ts"] = pd.to_datetime(idx[col0].astype(str), format="%Y%m%d_%H%M%S", errors="coerce")
        t = idx.dropna(subset=["ts"])
        t = t[t["ts"].dt.date == today].sort_values("ts")
        if len(t):
            gaps = t["ts"].diff().dt.total_seconds() / 60
            out["ticks"] = int(len(t))
            out["first"] = str(t["ts"].iloc[0])
            out["last"] = str(t["ts"].iloc[-1])
            if gaps.notna().any():
                out["gap_median_min"] = round(float(gaps.dropna().median()), 2)
                out["gap_max_min"] = round(float(gaps.dropna().max()), 2)
                out["gaps_gt_12"] = int((gaps.dropna() > 12).sum())

    snaps = [
        p
        for p in iter_status_csvs(status_snapshots_dir())
        if f"_{today.strftime('%Y%m%d')}_" in p.name
    ]
    if snaps:
        latest = snaps[-1]
        out["latest_snapshot"] = latest.name
        df = pd.read_csv(latest, dtype=str)
        out["latest_rows"] = int(len(df))
        if "stat" in df.columns:
            s = df["stat"].astype(str).str.strip()
            av = s.isin(["2", "02", "2.0"])
            out["latest_avail_pct"] = round(float(av.mean()) * 100, 1) if len(df) else None

    qpath = LOOP1_LOGS / "daily_quota.json"
    if qpath.exists():
        q = json.loads(qpath.read_text(encoding="utf-8"))
        out["quota_date"] = q.get("date")
        out["calls"] = int(q.get("calls") or 0)
    else:
        out["calls"] = None
        out["quota_date"] = None
    return out


def utic_status(today: date) -> dict:
    utic_dir = loop2_dir()
    meta_path = utic_dir / "utic_incident_meta_latest.json"
    out: dict = {
        "ticks_today": 0,
        "fetched_at": None,
        "daegu_records": None,
        "national_records": None,
        "join_matched": None,
        "join_stations": None,
        "join_match_rate": None,
        "age_minutes": None,
        "k3_ok": False,
    }
    today_files = sorted(
        p
        for p in utic_dir.glob(f"daegu_traffic_incident_utic_{today.strftime('%Y%m%d')}_*.csv")
        if "latest" not in p.name
    )
    out["ticks_today"] = len(today_files)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        out["fetched_at"] = meta.get("fetched_at")
        out["daegu_records"] = meta.get("daegu_records")
        out["national_records"] = meta.get("national_records")
        if out["fetched_at"]:
            try:
                ft = datetime.fromisoformat(str(out["fetched_at"]))
                if ft.tzinfo is None:
                    ft = ft.replace(tzinfo=KST)
                out["age_minutes"] = round((_now() - ft).total_seconds() / 60, 1)
                out["k3_ok"] = out["age_minutes"] is not None and out["age_minutes"] <= 60
            except ValueError:
                pass
    join_meta = REPO / "docs" / "data" / "spatial_join" / "join_traffic_incident_utic_meta.json"
    if join_meta.exists():
        jm = json.loads(join_meta.read_text(encoding="utf-8"))
        out["join_matched"] = jm.get("matched")
        out["join_stations"] = jm.get("stations")
        out["join_match_rate"] = jm.get("match_rate")
    return out


def d1_status() -> dict:
    d1 = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    out: dict = {"exists": d1.exists()}
    if not d1.exists():
        return out
    d = pd.read_csv(d1, dtype=str, low_memory=False)
    out["rows"] = int(len(d))
    out["as_of_ts"] = d["as_of_ts"].iloc[0] if "as_of_ts" in d.columns else None
    for c in ("availability_ratio_observed", "unobserved_rate"):
        if c in d.columns:
            out[c] = round(float(pd.to_numeric(d[c], errors="coerce").mean()), 3)
    if "has_confirmed_available" in d.columns:
        h = d["has_confirmed_available"].astype(str).str.lower().isin(["true", "1", "yes"])
        out["has_confirmed_available_pct"] = round(float(h.mean()) * 100, 1)
        out["has_confirmed_available_n"] = int(h.sum())
    for c in ("traffic_is_mock", "traffic_source", "parking_is_mock", "parking_source"):
        if c in d.columns:
            out[c] = str(d[c].iloc[0])
    if "reliability_grade_effective" in d.columns:
        out["reliability"] = d["reliability_grade_effective"].value_counts().to_dict()
    elif "reliability_grade" in d.columns:
        out["reliability"] = d["reliability_grade"].value_counts().to_dict()
    if out.get("as_of_ts"):
        try:
            at = datetime.fromisoformat(str(out["as_of_ts"]))
            if at.tzinfo is None:
                at = at.replace(tzinfo=KST)
            out["as_of_age_hours"] = round((_now() - at).total_seconds() / 3600, 2)
        except ValueError:
            out["as_of_age_hours"] = None

    # --- public pool (recommend_public_default) ---
    if "recommend_public_default" in d.columns:
        pub = d["recommend_public_default"].astype(str).str.lower().isin(["true", "1", "yes"])
        out["public_n"] = int(pub.sum())
        out["restricted_n"] = int((~pub).sum())
        dp = d.loc[pub]
        if len(dp):
            for c in ("availability_ratio_observed", "unobserved_rate"):
                if c in dp.columns:
                    out[f"public_{c}"] = round(
                        float(pd.to_numeric(dp[c], errors="coerce").mean()), 3
                    )
            if "has_confirmed_available" in dp.columns:
                hp = dp["has_confirmed_available"].astype(str).str.lower().isin(
                    ["true", "1", "yes"]
                )
                out["public_has_confirmed_available_pct"] = round(float(hp.mean()) * 100, 1)
                out["public_has_confirmed_available_n"] = int(hp.sum())
        if "usage_level" in d.columns:
            hist = d["history_observed"].astype(str).str.lower().isin(["true", "1", "yes"]) if "history_observed" in d.columns else d["usage_level"].notna() & (d["usage_level"].astype(str).str.strip() != "")
            out["usage_level_coverage_n"] = int(hist.sum())
            out["public_usage_level_coverage_n"] = int((pub & hist).sum()) if len(d) else 0
            if "usage_level" in dp.columns and len(dp):
                out["public_usage_level_counts"] = (
                    dp.loc[dp["usage_level"].astype(str).str.strip() != "", "usage_level"]
                    .value_counts()
                    .to_dict()
                )
    return out


def usage_status() -> dict:
    path = REPO / "docs/data/spatial_join/join_usage_history_meta.json"
    if not path.exists():
        return {"exists": False}
    m = json.loads(path.read_text(encoding="utf-8"))
    m["exists"] = True
    feat = REPO / "apps/data-pipeline/evaluation/results/datasets/station_history_features_meta.json"
    if feat.exists():
        fm = json.loads(feat.read_text(encoding="utf-8"))
        m["feature_rows"] = fm.get("feature_rows")
        m["d1_merged"] = fm.get("d1_merged")
    return m


def evaluate(st: dict, ut: dict, d1: dict) -> list[dict]:
    rows = []
    # K1
    k1_ok = st["ticks"] > 0 and (st.get("gaps_gt_12") or 0) <= 1 and (
        st.get("gap_median_min") is None or st["gap_median_min"] <= 12
    )
    rows.append(
        {
            "id": "K1",
            "name": "status 루프 연속성",
            "value": f"틱 {st['ticks']} · median {st.get('gap_median_min')}분 · gap>12={st.get('gaps_gt_12')}",
            "target": "≈5분 · gap≤2",
            "status": "OK" if k1_ok else ("WARN" if st["ticks"] else "FAIL"),
        }
    )
    # K2
    calls = st.get("calls")
    k2_ok = calls is not None and calls <= 800
    k2_warn = calls is not None and calls >= 900
    rows.append(
        {
            "id": "K2",
            "name": "EvCharger 일일 호출",
            "value": f"{calls} / 1000" if calls is not None else "—",
            "target": "≤800",
            "status": "FAIL" if k2_warn else ("OK" if k2_ok else "WARN"),
        }
    )
    # K3
    rows.append(
        {
            "id": "K3",
            "name": "UTIC 돌발 루프",
            "value": f"오늘 {ut['ticks_today']}회 · age={ut.get('age_minutes')}분 · 대구 {ut.get('daegu_records')}건",
            "target": "≈15분 · 최근 1시간 내 성공",
            "status": "OK" if ut.get("k3_ok") else ("WARN" if ut["ticks_today"] else "FAIL"),
        }
    )
    # K4
    jm = ut.get("join_matched")
    k4_ok = jm is not None and int(jm) > 0
    rows.append(
        {
            "id": "K4",
            "name": "UTIC 조인 커버",
            "value": f"{jm}/{ut.get('join_stations')} (rate={ut.get('join_match_rate')})",
            "target": "matched > 0",
            "status": "OK" if k4_ok else "FAIL",
        }
    )
    # K5–K8
    rows.append(
        {
            "id": "K5",
            "name": "D1 관측 가용률",
            "value": str(d1.get("availability_ratio_observed", "—")),
            "target": "추세 보고용 (단정 금지)",
            "status": "OK" if d1.get("exists") else "FAIL",
        }
    )
    k6 = d1.get("has_confirmed_available_pct")
    rows.append(
        {
            "id": "K6",
            "name": "확정 가용 소 비율",
            "value": f"{k6}% ({d1.get('has_confirmed_available_n')}/{d1.get('rows')})" if k6 is not None else "—",
            "target": "≥50%",
            "status": "OK" if (k6 is not None and k6 >= 50) else ("WARN" if k6 is not None else "FAIL"),
        }
    )
    k7 = d1.get("unobserved_rate")
    rows.append(
        {
            "id": "K7",
            "name": "미관측률",
            "value": str(k7) if k7 is not None else "—",
            "target": "≤0.5",
            "status": "OK" if (k7 is not None and k7 <= 0.5) else ("WARN" if k7 is not None else "FAIL"),
        }
    )
    age_h = d1.get("as_of_age_hours")
    rows.append(
        {
            "id": "K8",
            "name": "D1 신선도",
            "value": f"{d1.get('as_of_ts')} (age={age_h}h)",
            "target": "당일·최근 (핸드오프 전 재빌드)",
            "status": "OK" if (age_h is not None and age_h <= 6) else ("WARN" if age_h is not None else "FAIL"),
        }
    )
    traf_ok = str(d1.get("traffic_is_mock", "")).lower() in ("false", "0")
    park_ok = str(d1.get("parking_source", "")) in ("none", "kotsa") or str(d1.get("parking_is_mock")).lower() == "true"
    rows.append(
        {
            "id": "K9",
            "name": "mock 혼입",
            "value": f"traffic={d1.get('traffic_source')}/mock={d1.get('traffic_is_mock')} · parking={d1.get('parking_source')}",
            "target": "traffic 실 · 주차 mock거리 미투입",
            "status": "OK" if (traf_ok and park_ok) else "WARN",
        }
    )
    rows.append(
        {
            "id": "K10",
            "name": "일일 점검 health",
            "value": "status_daily/ 참고 (자동 판정은 루프 체크포인트)",
            "target": "healthy 또는 사유 기록",
            "status": "OK" if st["ticks"] else "WARN",
        }
    )
    return rows


def render_md(payload: dict) -> str:
    st, ut, d1, usage, kpis = payload["status"], payload["utic"], payload["d1"], payload["usage"], payload["kpis"]
    lines = [
        "# DA➀ KPI 보고서",
        "",
        "| | |",
        "|---|---|",
        f"| **생성** | {payload['generated_at']} |",
        f"| **기준일** | {payload['report_date']} |",
        f"| **정의 정본** | [`KPI.md`](./KPI.md) |",
        f"| **갱신** | `python apps/data-pipeline/processing/analysis/report_kpi.py` |",
        "",
        "> 이 파일은 **스크립트가 덮어쓴다**. 수동 메모는 [`KPI.md`](./KPI.md) §6 기준선에 남긴다.",
        "",
        "---",
        "",
        "## 1. 판정 요약",
        "",
        "| ID | KPI | 현재 값 | 목표 | 상태 |",
        "|---|---|---|---|---|",
    ]
    for r in kpis:
        lines.append(f"| {r['id']} | {r['name']} | {r['value']} | {r['target']} | **{r['status']}** |")

    ok_n = sum(1 for r in kpis if r["status"] == "OK")
    lines += [
        "",
        f"**OK {ok_n}/{len(kpis)}**",
        "",
        "---",
        "",
        "## 2. 운영 상세",
        "",
        "### Status (K1·K2)",
        "",
        f"- 당일 틱: **{st['ticks']}**",
        f"- 구간: {st.get('first')} ~ {st.get('last')}",
        f"- 간격 median/max: {st.get('gap_median_min')} / {st.get('gap_max_min')} 분",
        f"- gap>12분: {st.get('gaps_gt_12')}",
        f"- API 호출: **{st.get('calls')} / 1000** (quota date={st.get('quota_date')})",
        f"- 최신 스냅샷: `{st.get('latest_snapshot')}` · 행 {st.get('latest_rows')} · period 가용 {st.get('latest_avail_pct')}%",
        "",
        "> period 가용%는 변경분만 분모 — 대구 전체 가용률로 말하지 말 것.",
        "",
        "### UTIC (K3·K4)",
        "",
        f"- 당일 추출: **{ut['ticks_today']}**",
        f"- 최신 fetched_at: {ut.get('fetched_at')} (age {ut.get('age_minutes')}분)",
        f"- 대구/전국: {ut.get('daegu_records')} / {ut.get('national_records')}",
        f"- 조인: {ut.get('join_matched')} / {ut.get('join_stations')} (rate={ut.get('join_match_rate')})",
        "",
        "---",
        "",
        "## 3. D1 품질 (K5–K9)",
        "",
        f"- as_of: `{d1.get('as_of_ts')}` (age {d1.get('as_of_age_hours')}h)",
        f"- 행: {d1.get('rows')}",
        f"- 관측 가용률 mean: **{d1.get('availability_ratio_observed')}**",
        f"- 미관측률 mean: **{d1.get('unobserved_rate')}**",
        f"- 확정 가용: **{d1.get('has_confirmed_available_pct')}%** ({d1.get('has_confirmed_available_n')}/{d1.get('rows')})",
        f"- traffic: source=`{d1.get('traffic_source')}` mock=`{d1.get('traffic_is_mock')}`",
        f"- parking: source=`{d1.get('parking_source')}` mock=`{d1.get('parking_is_mock')}`",
    ]
    if d1.get("reliability"):
        lines.append(f"- reliability: `{d1['reliability']}`")

    lines += [
        "",
        "### 공용 후보만 (recommend_public_default)",
        "",
        "> 일반 사용자 추천은 **이쪽 숫자**를 본다. 전체와 섞지 말 것.",
        "",
        f"- 공용 / 제한: **{d1.get('public_n')}** / {d1.get('restricted_n')} (전체 {d1.get('rows')})",
        f"- 공용 관측 가용률 mean: **{d1.get('public_availability_ratio_observed')}**",
        f"- 공용 미관측률 mean: **{d1.get('public_unobserved_rate')}**",
        f"- 공용 확정 가용: **{d1.get('public_has_confirmed_available_pct')}%** "
        f"({d1.get('public_has_confirmed_available_n')}/{d1.get('public_n')})",
    ]
    if d1.get("public_usage_level_counts"):
        lines.append(f"- 공용 소 usage_level: `{d1['public_usage_level_counts']}`")
    if d1.get("usage_level_coverage_n") is not None:
        lines.append(
            f"- 이용강도 커버: 전체 {d1.get('usage_level_coverage_n')} · "
            f"공용 {d1.get('public_usage_level_coverage_n')}"
        )

    lines += [
        "",
        "---",
        "",
        "## 4. 이용강도 피처 (보조)",
        "",
    ]
    if usage.get("exists"):
        lines += [
            f"- 조인: **{usage.get('matched')}/{usage.get('usage_stations')}** (rate={usage.get('match_rate')}, {usage.get('radius_m')}m)",
            f"- 기간: {usage.get('date_min')} ~ {usage.get('date_max')}",
            f"- 피처 행: {usage.get('feature_rows')} · D1 merge={usage.get('d1_merged')}",
            f"- 파일: `{usage.get('output')}` · `station_history_features_latest.csv`",
        ]
    else:
        lines.append("- (아직 없음)")

    lines += [
        "",
        "---",
        "",
        "## 5. 다음 액션",
        "",
        "- 루프 OFF 전이면 저녁에 한 번 더 `report_kpi.py` 실행",
        "- K8 WARN이면 D1 재빌드 후 재실행",
        "- K3 FAIL이면 UTIC 키/IP 확인 (학원 vs 집)",
        "- 기준선 한 줄은 [`KPI.md`](./KPI.md) §6에 수동 추가",
        "",
        "```",
        f"DA➀ | KPI report | {payload['report_date']}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    today = _now().date()
    st = status_today(today)
    ut = utic_status(today)
    d1 = d1_status()
    usage = usage_status()
    kpis = evaluate(st, ut, d1)
    payload = {
        "generated_at": _now().isoformat(),
        "report_date": str(today),
        "criteria": CRITERIA,
        "status": st,
        "utic": ut,
        "d1": d1,
        "usage": usage,
        "kpis": kpis,
    }
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_md(payload), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"ok": True, "md": str(OUT_MD.relative_to(REPO)).replace("\\", "/"), "json": str(OUT_JSON.relative_to(REPO)).replace("\\", "/"), "ok_count": sum(1 for r in kpis if r["status"] == "OK")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

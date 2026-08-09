"""Probe systematic coverage gaps similar to 두류역서한포레스트."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[2]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import latest_daily_charger_info
KST = ZoneInfo("Asia/Seoul")
OUT = REPO / f"docs/팀공유/인포커버리지갭_{datetime.now(KST).strftime('%Y%m%d')}"


def main() -> int:
    info_path = latest_daily_charger_info() or (
        REPO
        / "docs/data/extracted/daily/2026-07-25/daegu_charger_info_20260725_latest.csv"
    )
    info = pd.read_csv(info_path, dtype=str, low_memory=False)
    d1 = pd.read_csv(
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv",
        encoding="utf-8-sig",
        low_memory=False,
    )

    brand_sites = [
        "두류역서한포레스트",
        "반월당서한포레스트",
        "청라언덕역서한포레스트",
        "범어서한포레스트",
        "만촌역서한포레스트",
    ]
    brand_rows = []
    for s in brand_sites:
        hit = info[info["statNm"].astype(str).str.contains(re.escape(s), na=False)]
        brand_rows.append(
            {
                "site_query": s,
                "info_charger_rows": int(len(hit)),
                "info_stations": int(hit["statId"].nunique()) if len(hit) else 0,
                "example_names": "|".join(sorted(hit["statNm"].dropna().unique())[:8]),
            }
        )
    brand_df = pd.DataFrame(brand_rows)

    info_st = set(info["statId"])
    d1_st = set(d1["statId"].astype(str))
    overlap = {
        "info_stations": len(info_st),
        "d1_stations": len(d1_st),
        "info_not_in_d1": len(info_st - d1_st),
        "d1_not_in_info": len(d1_st - info_st),
    }

    obs = d1["observation_state"].value_counts(dropna=False).to_dict()
    unobs_rate = float((d1["observation_state"] == "UNOBSERVED").mean())

    res_stats = {}
    if "name_suggests_residential" in d1.columns:
        # bool-ish
        res_mask = d1["name_suggests_residential"].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        ) | (d1["name_suggests_residential"] == True)  # noqa: E712
        res = d1[res_mask]
        res_stats = {
            "residential_stations": int(len(res)),
            "residential_unobserved_rate": float(
                (res["observation_state"] == "UNOBSERVED").mean()
            )
            if len(res)
            else None,
            "residential_history_rate": float(res["history_observed"].mean())
            if "history_observed" in res.columns and len(res)
            else None,
            "overall_history_rate": float(d1["history_observed"].mean())
            if "history_observed" in d1.columns
            else None,
        }

    pattern_rows = []
    for pat in [
        "포레스트",
        "이다음",
        "자이",
        "힐스테이트",
        "푸르지오",
        "e편한세상",
        "센트레빌",
        "서한",
    ]:
        sub = d1[d1["statNm"].astype(str).str.contains(pat, na=False)]
        if sub.empty:
            pattern_rows.append(
                {
                    "name_pattern": pat,
                    "stations": 0,
                    "unobserved_rate": None,
                    "history_rate": None,
                }
            )
            continue
        pattern_rows.append(
            {
                "name_pattern": pat,
                "stations": int(len(sub)),
                "unobserved_rate": float(
                    (sub["observation_state"] == "UNOBSERVED").mean()
                ),
                "history_rate": float(sub["history_observed"].mean())
                if "history_observed" in sub.columns
                else None,
            }
        )
    pattern_df = pd.DataFrame(pattern_rows)

    # delYn=Y still in dump
    del_y = int((info["delYn"].astype(str).str.upper() == "Y").sum()) if "delYn" in info else None
    stations_del = (
        int(info.loc[info["delYn"].astype(str).str.upper() == "Y", "statId"].nunique())
        if "delYn" in info
        else None
    )

    # stations with blank/missing coords
    lat = pd.to_numeric(info.get("lat"), errors="coerce")
    bad_coord_stations = int(info.loc[lat.isna(), "statId"].nunique())

    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "concern": "real complex exists but EvCharger name/id missing (like 두류역서한포레스트)",
        "brand_site_checks": brand_rows,
        "overlap_info_vs_d1": overlap,
        "observation_state_counts": {str(k): int(v) for k, v in obs.items()},
        "unobserved_rate_d1": unobs_rate,
        "residential": res_stats,
        "name_pattern_quality": pattern_rows,
        "info_delYn_Y_charger_rows": del_y,
        "info_delYn_Y_stations": stations_del,
        "info_missing_coord_stations": bad_coord_stations,
        "interpretation": [
            "Type A gap: complex exists, no matching statNm in info (두류역서한포레스트) — unknown size without external apt registry",
            "Type B gap: in info but UNOBSERVED in status — measurable and large",
            "Type C gap: in info but no usage history — common for residential/restricted",
            "Cannot claim completeness of Daegu EV inventory from EvCharger alone",
        ],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    brand_df.to_csv(OUT / "brand_site_presence.csv", index=False, encoding="utf-8-sig")
    pattern_df.to_csv(OUT / "name_pattern_quality.csv", index=False, encoding="utf-8-sig")
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = [
        "# 인포/관측 커버리지 갭 우려 — 점검 메모 (2026-07-31)",
        "",
        "## 한 줄",
        "두류역서한포레스트처럼 **실단지인데 공공 info에 이름이 없는 구멍은 더 있을 가능성이 높다.** "
        "다만 지금 파이프라인만으로는 그 **전체 개수를 셀 수 없다.** "
        "대신 **info엔 있는데 상태/이력이 비는 Type B·C 갭은 이미 크게 관측된다.**",
        "",
        "## 서한포레스트 브랜드 샘플",
    ]
    for r in brand_rows:
        md.append(
            f"- `{r['site_query']}` → info 충전소 {r['info_stations']}곳 "
            f"(예: {r['example_names'] or '없음'})"
        )
    md += [
        "",
        "## 측정 가능한 갭 (D1)",
        f"- UNOBSERVED 비율: **{unobs_rate:.1%}**",
        f"- info 충전소 {overlap['info_stations']} / D1 {overlap['d1_stations']}",
        f"- info∉D1 {overlap['info_not_in_d1']} · D1∉info {overlap['d1_not_in_info']}",
    ]
    if res_stats:
        md.append(
            f"- 주거성 이름 후보 {res_stats.get('residential_stations')}곳 · "
            f"UNOBSERVED {res_stats.get('residential_unobserved_rate')} · "
            f"이용이력 {res_stats.get('residential_history_rate')}"
        )
    md += [
        "",
        "## 왜 우려가 맞나",
        "1. EvCharger는 **등록·노출된 충전기**만 담음 (단지 내부 미등록/지연 등록 가능)",
        "2. 입주자 전용·운영사 앱 전용은 공공 목록에 늦거나 안 뜰 수 있음",
        "3. 이름 불일치(관리사무소/운영사명)로 **있어도 못 찾을** 수 있음",
        "4. status는 변경분이라 info에 있어도 관측이 비는 경우가 많음",
        "",
        "## 팀에 말할 톤",
        "- MVP 추천은 **관측 가능한 공개 충전소** 기준이 맞음",
        "- ‘대구 전체 충전기 완전 목록’을 주장하면 안 됨",
        "- 신축 단지·아파트 내부 충전기는 **구조적 과소표집** 가능 → 모니터링 항목으로 남김",
        "",
    ]
    (OUT / "README_쉬운설명.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

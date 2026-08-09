"""Pull charger-related data for 2025/2026 Daegu move-in seed complexes.

For each complex:
  - name match in EvCharger info
  - OSM geocode (dong+name / gu+dong)
  - nearby stations within 300m / 500m
  - D1 rows for nearby + name-matched ids

NOT official registry. Blog/list based sample for coverage monitoring.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import sys

_PROCESSING = Path(__file__).resolve().parents[2]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import latest_daily_charger_info
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")
SEED = REPO / "docs/data/analysis/new_apt_coverage/daegu_movein_seed_2025_2026.csv"
INFO = latest_daily_charger_info() or (
    REPO
    / "docs/data/extracted/daily/2026-07-25/daegu_charger_info_20260725_latest.csv"
)
D1 = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
)
OUT = REPO / "docs/팀공유/신축단지_충전데이터팩_20260731"


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def tokens(name: str) -> list[str]:
    n = re.sub(r"[\s\(\)（）·∙\-/Ⅲ]", "", str(name))
    n = n.replace("3차", "3")
    out = [n]
    if len(n) >= 8:
        out.append(n[:8])
    if len(n) >= 10:
        out.append(n[:10])
    return list(dict.fromkeys(out))


def match_info(info: pd.DataFrame, complex_name: str) -> pd.DataFrame:
    mask = None
    for t in tokens(complex_name):
        if len(t) < 6:
            continue
        m = info["statNm"].astype(str).str.contains(re.escape(t), na=False)
        mask = m if mask is None else (mask | m)
    if mask is None:
        return info.iloc[0:0]
    return info.loc[mask].copy()


def verdict(names: list[str], complex_name: str) -> str:
    if not names:
        return "MISSING_IN_INFO"
    core = re.sub(r"[\s\(\)]", "", complex_name)
    for nm in names:
        nn = re.sub(r"[\s\(\)]", "", str(nm))
        if core[:8] in nn or nn[:8] in core:
            return "FOUND_NAME"
    return "POSSIBLE_RELATED"


def geocode(query: str) -> tuple[float | None, float | None, str]:
    q = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(
        "https://nominatim.openstreetmap.org/search?" + q,
        headers={"User-Agent": "EVSafeCharge-coverage/1.0 (research)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        if not data:
            return None, None, "no_hit"
        return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get(
            "display_name", ""
        )[:120]
    except Exception as e:
        return None, None, f"error:{e}"


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    seed = pd.read_csv(SEED, dtype=str)
    info = pd.read_csv(INFO, dtype=str, low_memory=False)
    info["lat_f"] = pd.to_numeric(info.get("lat"), errors="coerce")
    info["lng_f"] = pd.to_numeric(info.get("lng"), errors="coerce")
    d1 = pd.read_csv(D1, encoding="utf-8-sig", low_memory=False)

    OUT.mkdir(parents=True, exist_ok=True)
    per_dir = OUT / "per_complex"
    if per_dir.exists():
        shutil.rmtree(per_dir)
    per_dir.mkdir()

    summary_rows = []
    all_nearby = []
    all_name = []

    for i, apt in seed.iterrows():
        cid = apt["complex_id"]
        cname = apt["complex_name"]
        print(f"[{i+1}/{len(seed)}] {cname}")

        hit = match_info(info, cname)
        st = hit.drop_duplicates("statId") if len(hit) else hit
        names = st["statNm"].dropna().astype(str).tolist() if len(st) else []
        ids = st["statId"].astype(str).tolist() if len(st) else []
        v = verdict(names, cname)

        # geocode: try complex then gu+dong
        queries = [
            f"대구 {cname}",
            f"대구광역시 {apt['gu']} {apt['dong']} {cname}",
            f"대구광역시 {apt['gu']} {apt['dong']}",
        ]
        lat = lng = None
        geo_src = ""
        for q in queries:
            time.sleep(1.1)
            lat, lng, geo_src = geocode(q)
            if lat is not None:
                break

        nearby300 = nearby500 = pd.DataFrame()
        if lat is not None:
            ok = info.dropna(subset=["lat_f", "lng_f"]).copy()
            ok["dist_m"] = ok.apply(
                lambda r: haversine_m(lat, lng, r["lat_f"], r["lng_f"]), axis=1
            )
            nearby300 = ok[ok["dist_m"] <= 300].sort_values("dist_m")
            nearby500 = ok[ok["dist_m"] <= 500].sort_values("dist_m")

        near_ids = set()
        if len(nearby500):
            near_ids |= set(nearby500["statId"].astype(str))
        near_ids |= set(ids)
        d1m = d1[d1["statId"].astype(str).isin(near_ids)] if near_ids else d1.iloc[0:0]

        # write per complex
        cdir = per_dir / cid
        cdir.mkdir()
        meta = {
            **apt.to_dict(),
            "match_verdict": v,
            "matched_stations": int(len(st)),
            "matched_statIds": ids,
            "matched_statNms": names,
            "geocode_lat": lat,
            "geocode_lng": lng,
            "geocode_note": geo_src,
            "nearby_300m_stations": int(nearby300["statId"].nunique())
            if len(nearby300)
            else 0,
            "nearby_500m_stations": int(nearby500["statId"].nunique())
            if len(nearby500)
            else 0,
            "nearby_500m_chargers": int(len(nearby500)),
            "d1_rows_for_nearby_or_name": int(len(d1m)),
        }
        (cdir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if len(hit):
            hit.to_csv(cdir / "info_name_match.csv", index=False, encoding="utf-8-sig")
            tmp = hit.copy()
            tmp["complex_id"] = cid
            tmp["complex_name"] = cname
            all_name.append(tmp)
        if len(nearby500):
            nearby500.drop_duplicates("statId").to_csv(
                cdir / "nearby_stations_500m.csv", index=False, encoding="utf-8-sig"
            )
            nearby500.to_csv(
                cdir / "nearby_chargers_500m.csv", index=False, encoding="utf-8-sig"
            )
            tmp = nearby500.drop_duplicates("statId").copy()
            tmp["complex_id"] = cid
            tmp["complex_name"] = cname
            tmp["cohort"] = apt["cohort"]
            all_nearby.append(tmp)
        if len(d1m):
            d1m.to_csv(cdir / "d1_nearby_or_name.csv", index=False, encoding="utf-8-sig")

        summary_rows.append(meta)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(OUT / "complex_charger_summary.csv", index=False, encoding="utf-8-sig")
    if all_nearby:
        pd.concat(all_nearby, ignore_index=True).to_csv(
            OUT / "all_nearby_stations_500m.csv", index=False, encoding="utf-8-sig"
        )
    if all_name:
        pd.concat(all_name, ignore_index=True).to_csv(
            OUT / "all_info_name_matches.csv", index=False, encoding="utf-8-sig"
        )

    vc = summary["match_verdict"].value_counts().to_dict()
    by_cohort = (
        summary.groupby("cohort")["match_verdict"]
        .value_counts()
        .unstack(fill_value=0)
        .to_dict()
    )
    pack_meta = {
        "generated_at": datetime.now(KST).isoformat(),
        "seed_file": str(SEED.relative_to(REPO)).replace("\\", "/"),
        "n_complexes": int(len(summary)),
        "n_2025": int((summary["cohort"] == "2025").sum()),
        "n_2026": int((summary["cohort"] == "2026").sum()),
        "verdict_counts": {str(k): int(v) for k, v in vc.items()},
        "verdict_by_cohort": by_cohort,
        "avg_nearby_500m_stations": float(summary["nearby_500m_stations"].mean()),
        "completeness_note": {
            "2025": "Aligned to savetime blog table (~9,291 hh). Not MLIT official registry; lists can differ by source.",
            "2026": "Confirmed/pre-sale move-in sample (~6k hh class). More may appear later.",
            "why_2026": "Include for early registration monitoring; MISSING expected until near move-in/API register.",
        },
    }
    (OUT / "summary.json").write_text(
        json.dumps(pack_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # easy readme
    lines = [
        f"# 신축단지 충전 데이터 팩 ({stamp})",
        "",
        "## 이게 다니? (2025)",
        "- **공식 전수 명단은 아님.** 부동산 입주 정리 블로그 표(약 9,291세대)에 맞춘 **모니터링 시드**.",
        "- 출처마다 단지가 조금씩 다름 (일정 변경·오피스텔 포함 여부).",
        f"- 이번 시드 2025: **{(summary['cohort']=='2025').sum()}개 단지** (죽전행복주택·영대 오피스텔 포함해 이전 20개보다 보강).",
        "",
        "## 2026도 넣어야 하나?",
        "- **넣어야 함 (모니터링용).** 입주 전이라도 충전기가 먼저 등록될 수 있고, 입주 직후 등록 지연도 볼 수 있음.",
        "- 다만 지금은 **MISSING이 정상인 구간**이 많을 수 있음. ‘미반영=버그’로 단정하지 말 것.",
        f"- 이번 시드 2026: **{(summary['cohort']=='2026').sum()}개 단지** (범어자이·대명자이 등).",
        "",
        "## 이름 매칭 결과",
        f"- FOUND_NAME: {vc.get('FOUND_NAME', 0)}",
        f"- POSSIBLE_RELATED: {vc.get('POSSIBLE_RELATED', 0)}",
        f"- MISSING_IN_INFO: {vc.get('MISSING_IN_INFO', 0)}",
        "",
        "## 단지별 요약 (발췌)",
        "| 단지 | 입주 | 판정 | 500m내 충전소 |",
        "|---|---|---|---:|",
    ]
    for _, r in summary.sort_values(["cohort", "move_in_ym"]).iterrows():
        lines.append(
            f"| {r['complex_name']} | {r['move_in_ym']} | {r['match_verdict']} | {r['nearby_500m_stations']} |"
        )
    lines += [
        "",
        "## 폴더",
        "- `complex_charger_summary.csv` — 한눈에",
        "- `per_complex/<id>/` — 단지별 info매칭·인근·D1",
        "- `all_nearby_stations_500m.csv` — 인근 통합",
        "- `daegu_movein_seed_2025_2026.csv` — 시드",
        "",
        "## 해석",
        "- 이름 MISSING ≠ 인근에 충전기 없음 (반경 검색으로 보완).",
        "- 반경 충전소 ≠ 단지 내부 충전기.",
        "- MVP는 관측 가능 EvCharger 기준 유지.",
        "",
    ]
    (OUT / "README_쉬운설명.md").write_text("\n".join(lines), encoding="utf-8")
    shutil.copy2(SEED, OUT / "daegu_movein_seed_2025_2026.csv")

    pack = f"EV_SafeCharge_신축단지_충전데이터팩_{stamp}"
    desk = DESK / pack
    if desk.exists():
        shutil.rmtree(desk)
    shutil.copytree(OUT, desk)
    zpath = DESK / f"{pack}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in desk.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f"{pack}/{f.relative_to(desk).as_posix()}")

    print(json.dumps(pack_meta, ensure_ascii=False, indent=2))
    print(
        summary[
            [
                "complex_name",
                "cohort",
                "move_in_ym",
                "match_verdict",
                "nearby_500m_stations",
                "matched_stations",
            ]
        ].to_string(index=False)
    )
    print("ZIP", zpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

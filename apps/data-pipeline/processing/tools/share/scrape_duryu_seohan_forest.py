"""Collect all available repo data related to 두류역서한포레스트 chargers."""
from __future__ import annotations

import json
import math
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[5]
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")

# AptRank / public listing
APT = {
    "name": "두류역서한포레스트",
    "addr": "대구광역시 달서구 야외음악당로47길 76",
    "lot": "대구광역시 달서구 두류동 2369",
    "move_in_year": 2025,
    "households": 480,
    # OSM Nominatim road centroid for 야외음악당로47길 (building-level may differ)
    "lat": 35.8580111,
    "lng": 128.5607417,
    "coord_source": "nominatim_야외음악당로47길",
}

NAME_PAT = re.compile(r"두류.*서한|서한.*두류|두류역서한|두류역\s*서한", re.I)


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_info(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    for c in df.columns:
        if c.lower() == "statid":
            df = df.rename(columns={c: "statId"})
        if c.lower() == "statnm":
            df = df.rename(columns={c: "statNm"})
    return df


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    pack = f"EV_SafeCharge_두류역서한포레스트_데이터_{stamp}"
    out_docs = REPO / "docs" / "팀공유" / f"두류역서한포레스트_{stamp}"
    out_desk = DESK / pack
    out_docs.mkdir(parents=True, exist_ok=True)
    if out_desk.exists():
        shutil.rmtree(out_desk)
    out_desk.mkdir(parents=True, exist_ok=True)

    info_path = (
        REPO
        / "docs/data/extracted/daily/2026-07-25/daegu_charger_info_20260725_latest.csv"
    )
    info = load_info(info_path)
    info["lat_f"] = pd.to_numeric(info.get("lat"), errors="coerce")
    info["lng_f"] = pd.to_numeric(info.get("lng"), errors="coerce")

    # 1) name hit in all info dumps + service/flagged
    name_hits = []
    info_files = list(
        (REPO / "docs/data/extracted/daily").glob("**/daegu_charger_info_*.csv")
    ) + list((REPO / "docs/data/extracted/charger/info").glob("daegu_charger_info_*.csv"))
    for p in sorted(set(info_files)):
        try:
            df = load_info(p)
        except Exception as e:
            continue
        if "statNm" not in df.columns:
            continue
        hit = df[df["statNm"].astype(str).str.contains(NAME_PAT, na=False)].copy()
        if hit.empty:
            # also exact-ish contains
            hit = df[
                df["statNm"].astype(str).str.contains("두류역서한포레스트", na=False)
            ].copy()
        if not hit.empty:
            hit["source_file"] = str(p.relative_to(REPO)).replace("\\", "/")
            name_hits.append(hit)
    name_df = (
        pd.concat(name_hits, ignore_index=True) if name_hits else pd.DataFrame()
    )
    name_df.to_csv(
        out_docs / "01_info_name_match.csv", index=False, encoding="utf-8-sig"
    )

    # refine apt coords from nearby known landmark if we find dense cluster
    # Use address keyword 야외음악당로47 or 두류동 2369
    addr_hit = info[
        info["addr"].astype(str).str.contains("야외음악당로47|두류동 2369|두류동2369", na=False)
        | info["statNm"].astype(str).str.contains("두류역서한", na=False)
    ].copy()
    addr_hit.to_csv(
        out_docs / "02_info_addr_keyword.csv", index=False, encoding="utf-8-sig"
    )

    # Prefer exact address match; otherwise keep Nominatim road centroid (do NOT
    # median all 야외음악당로* stations — that drifts to 삼정그린빌 on 39길).
    if not addr_hit.empty and addr_hit["lat_f"].notna().any():
        APT["lat"] = float(addr_hit["lat_f"].dropna().mean())
        APT["lng"] = float(addr_hit["lng_f"].dropna().mean())
        APT["coord_source"] = "info_addr_match"
    else:
        APT["coord_source"] = APT.get("coord_source", "nominatim_야외음악당로47길")

    # 2) radius search 100/300/500/1000m
    ok = info.dropna(subset=["lat_f", "lng_f"]).copy()
    ok["dist_m"] = ok.apply(
        lambda r: haversine_m(APT["lat"], APT["lng"], r["lat_f"], r["lng_f"]), axis=1
    )
    radius_rows = []
    for rad in (100, 250, 300, 500, 1000):
        sub = ok[ok["dist_m"] <= rad].copy()
        sub["radius_m"] = rad
        radius_rows.append(sub)
        sub.sort_values("dist_m").drop_duplicates("statId").to_csv(
            out_docs / f"03_nearby_stations_within_{rad}m.csv",
            index=False,
            encoding="utf-8-sig",
        )
    near = ok[ok["dist_m"] <= 500].sort_values("dist_m")
    st_near = near.drop_duplicates("statId")[
        [
            c
            for c in (
                "statId",
                "statNm",
                "addr",
                "lat",
                "lng",
                "busiNm",
                "delYn",
                "dist_m",
            )
            if c in near.columns
        ]
    ].copy()
    st_near.to_csv(
        out_docs / "03_nearby_stations_within_500m_unique.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # charger-level within 500m
    near.to_csv(
        out_docs / "03_nearby_chargers_within_500m.csv",
        index=False,
        encoding="utf-8-sig",
    )

    target_ids = set(st_near["statId"].tolist())
    # also any name match ids
    if not name_df.empty and "statId" in name_df.columns:
        target_ids |= set(name_df["statId"].dropna().astype(str))

    # 3) D1 snapshot
    d1_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    )
    d1 = pd.read_csv(d1_path, encoding="utf-8-sig", low_memory=False)
    d1_hit = d1[
        d1["statId"].astype(str).isin(target_ids)
        | d1["statNm"].astype(str).str.contains(NAME_PAT, na=False)
        | d1["statNm"].astype(str).str.contains("두류역서한", na=False)
    ].copy()
    # attach distance if possible
    if "lat" in d1_hit.columns:
        d1_hit["dist_m_from_apt"] = d1_hit.apply(
            lambda r: haversine_m(APT["lat"], APT["lng"], r["lat"], r["lng"])
            if pd.notna(r.get("lat")) and pd.notna(r.get("lng"))
            else None,
            axis=1,
        )
    d1_hit.to_csv(out_docs / "04_d1_snapshot.csv", index=False, encoding="utf-8-sig")

    # 4) D2 panel sample for nearby ids (may be large — filter)
    panel_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_panel_latest.parquet"
    )
    panel = pd.read_parquet(panel_path)
    panel_hit = panel[panel["statId"].astype(str).isin(target_ids)].copy()
    panel_hit.to_parquet(out_docs / "05_d2_panel_nearby.parquet", index=False)
    # summary per station
    if not panel_hit.empty:
        g = (
            panel_hit.groupby("statId")
            .agg(
                first_ts=("panel_ts", "min"),
                last_ts=("panel_ts", "max"),
                n_ticks=("panel_ts", "count"),
                mean_avail=("availability_ratio_observed", "mean"),
            )
            .reset_index()
        )
        names = st_near.set_index("statId")["statNm"].to_dict() if len(st_near) else {}
        g["statNm"] = g["statId"].map(names)
        g.to_csv(
            out_docs / "05_d2_panel_station_summary.csv",
            index=False,
            encoding="utf-8-sig",
        )
    else:
        g = pd.DataFrame()

    # 5) ME history
    me_path = (
        REPO
        / "docs/data/extracted/charger/usage/me_history_daegu_20260724/daegu_me_history_all.csv"
    )
    me = pd.read_csv(
        me_path,
        dtype=str,
        usecols=[
            "충전소명",
            "충전기ID",
            "주소",
            "충전시작일시",
            "충전종료일시",
            "충전량",
            "station_key",
            "month",
        ],
        low_memory=False,
    )
    me_name = me[
        me["충전소명"].astype(str).str.contains(NAME_PAT, na=False)
        | me["충전소명"].astype(str).str.contains("두류역서한", na=False)
        | me["주소"].astype(str).str.contains("야외음악당로47", na=False)
    ].copy()
    me_name.to_csv(out_docs / "06_me_history_name_addr.csv", index=False, encoding="utf-8-sig")
    # nearby by joining charger names from info near list
    near_names = set(st_near["statNm"].dropna().astype(str)) if len(st_near) else set()
    me_near = me[me["충전소명"].astype(str).isin(near_names)].copy()
    me_near.to_csv(
        out_docs / "06_me_history_nearby_station_names.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # 6) parking joins
    park_files = [
        REPO / "docs/data/spatial_join/join_parking_team5_1000m.csv",
        REPO
        / "docs/팀공유/토요일_통합테스트_20260725/spatial_join/join_parking_team5_1000m.csv",
    ]
    park_hits = []
    for pf in park_files:
        if not pf.exists():
            continue
        pdf = pd.read_csv(pf, dtype=str, low_memory=False)
        sid_col = "statId" if "statId" in pdf.columns else None
        if sid_col:
            ph = pdf[pdf[sid_col].isin(target_ids)].copy()
        else:
            ph = pdf.iloc[0:0]
        if "statNm" in pdf.columns:
            ph2 = pdf[pdf["statNm"].astype(str).str.contains(NAME_PAT, na=False)]
            ph = pd.concat([ph, ph2], ignore_index=True).drop_duplicates()
        if not ph.empty:
            ph["source_file"] = str(pf.relative_to(REPO)).replace("\\", "/")
            park_hits.append(ph)
    park_df = pd.concat(park_hits, ignore_index=True) if park_hits else pd.DataFrame()
    park_df.to_csv(out_docs / "07_parking_join.csv", index=False, encoding="utf-8-sig")

    # 7) info master new-station pack mention
    new_path = REPO / "docs/팀공유/인포신규충전소_20260731/info_new_stations_overall.csv"
    new_df = pd.read_csv(new_path, dtype=str) if new_path.exists() else pd.DataFrame()
    if not new_df.empty:
        new_hit = new_df[
            new_df["statId"].isin(target_ids)
            | new_df["statNm"].astype(str).str.contains("두류", na=False)
        ]
    else:
        new_hit = pd.DataFrame()
    new_hit.to_csv(
        out_docs / "08_info_new_related_duryu.csv", index=False, encoding="utf-8-sig"
    )

    # 8) external notes
    notes = {
        "apartment": APT,
        "external_web": {
            "aptrank": "https://www.aptrank.com/apt_detail.php?aptnameuid=68097",
            "aptrank_nearby_charger_named": "대구 두류역서한포레스트 (249m, 25대) — listed on apt page; may be POI aggregate",
            "note": "EvCharger official info dump (2026-07-25) has NO statNm exactly matching 두류역서한포레스트",
        },
        "counts": {
            "info_name_match_rows": int(len(name_df)),
            "info_addr_keyword_rows": int(len(addr_hit)),
            "nearby_500m_stations": int(len(st_near)),
            "nearby_500m_charger_rows": int(len(near)),
            "d1_rows": int(len(d1_hit)),
            "d2_rows": int(len(panel_hit)),
            "me_name_rows": int(len(me_name)),
            "me_nearby_name_rows": int(len(me_near)),
            "parking_join_rows": int(len(park_df)),
        },
        "generated_at": datetime.now(KST).isoformat(),
    }
    (out_docs / "summary.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # README
    lines = [
        f"# 두류역서한포레스트 충전기 관련 데이터 수집 ({stamp})",
        "",
        "## 핵심 결론",
        "- 아파트 **두류역서한포레스트**는 실재함 (달서구 야외음악당로47길 76 / 두류동 2369, 2025 입주).",
        "- 우리 **EvCharger info(7/25)에는 `statNm=두류역서한포레스트` 충전소가 없음**.",
        "- ME 이용현황에도 동일 이름 **0건**.",
        "- 따라서 ‘단지명으로 등록된 충전기’ 데이터가 아니라, **좌표 반경 인근 충전소**를 긁어 모음.",
        "",
        f"## 검색 중심 좌표",
        f"- lat={APT['lat']}, lng={APT['lng']} (source: {APT.get('coord_source')})",
        f"- 주소: {APT['addr']}",
        "",
        f"## 500m 이내 충전소 ({len(st_near)}곳)",
    ]
    for _, r in st_near.head(40).iterrows():
        lines.append(
            f"- `{r['statId']}` {r.get('statNm','')} / {r.get('addr','')} / {float(r['dist_m']):.0f}m"
        )
    if len(st_near) > 40:
        lines.append(f"- … 외 {len(st_near)-40}곳 (CSV 참고)")
    lines += [
        "",
        "## 파일 목록",
        "| 파일 | 내용 |",
        "|---|---|",
        "| `01_info_name_match.csv` | info에서 이름 매칭 (보통 비어 있음) |",
        "| `02_info_addr_keyword.csv` | 주소 키워드 매칭 |",
        "| `03_nearby_stations_within_*m.csv` | 반경별 충전소 |",
        "| `03_nearby_chargers_within_500m.csv` | 500m 충전기 단위 |",
        "| `04_d1_snapshot.csv` | D1 스냅샷 |",
        "| `05_d2_panel_nearby.parquet` | D2 패널 (인근) |",
        "| `05_d2_panel_station_summary.csv` | D2 요약 |",
        "| `06_me_history_*.csv` | 이용현황 |",
        "| `07_parking_join.csv` | 주차 조인 |",
        "| `08_info_new_related_duryu.csv` | 인포 신규 중 두류 관련 |",
        "| `summary.json` | 메타 |",
        "",
        "## 해석 주의",
        "- 아파트랭킹에 ‘대구 두류역서한포레스트 충전기 25대’가 보이더라도, **공공 EvCharger 마스터에 동일 명칭이 없으면** 민간 POI/단지 내부 미등록·다른 ID일 수 있음.",
        "- 인근 `두류역공영주차장(HM710135)` 등은 **단지 충전기가 아님**.",
        "",
    ]
    (out_docs / "README_쉬운설명.md").write_text("\n".join(lines), encoding="utf-8")

    # copy + zip
    for f in out_docs.iterdir():
        shutil.copy2(f, out_desk / f.name)
    zip_path = DESK / f"{pack}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_desk.rglob("*"):
            if f.is_file():
                zf.write(f, arcname=f"{pack}/{f.relative_to(out_desk).as_posix()}")

    print(json.dumps(notes, ensure_ascii=False, indent=2))
    print("ZIP", zip_path)
    print("NEAR500")
    print(st_near.head(20).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

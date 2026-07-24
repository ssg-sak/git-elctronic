# -*- coding: utf-8 -*-
"""One-shot DQ check for DA① latest artifacts (2026-07-23)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
issues: list[dict] = []


def flag(sev: str, code: str, msg: str, detail=None) -> None:
    issues.append({"sev": sev, "code": code, "msg": msg, "detail": detail})
    print(f"[{sev}] {code}: {msg}" + (f" | {detail}" if detail is not None else ""))


def main() -> int:
    # ── INFO ─────────────────────────────────────────────
    info_p = REPO / "docs/data/extracted/charger/info/daegu_charger_info_20260723_latest.csv"
    info = pd.read_csv(info_p, dtype=str)
    print("\n=== INFO", info_p.name, "rows", len(info), "cols", len(info.columns))

    for c in ["statId", "chgerId", "lat", "lng", "chgerType", "stat", "useTime", "delYn", "fetchedAt"]:
        if c not in info.columns:
            flag("HIGH", "INFO_MISSING_COL", f"missing column {c}")

    info["lat_n"] = pd.to_numeric(info["lat"], errors="coerce")
    info["lng_n"] = pd.to_numeric(info["lng"], errors="coerce")
    info["output_n"] = (
        pd.to_numeric(info["output"], errors="coerce") if "output" in info.columns else np.nan
    )

    for c in ["statId", "chgerId"]:
        n = int(info[c].isna().sum() + (info[c].astype(str).str.strip() == "").sum())
        if n:
            flag("HIGH", "INFO_NULL_KEY", f"{c} null/blank", n)

    dup = int(info.duplicated(subset=["statId", "chgerId"], keep=False).sum())
    if dup:
        flag("HIGH", "INFO_DUP_CHARGER", "duplicate statId+chgerId rows", dup)

    bad_coord = info["lat_n"].isna() | info["lng_n"].isna()
    out_bbox = (
        ~((info["lat_n"].between(35.55, 36.45)) & (info["lng_n"].between(128.25, 129.05)))
        & ~bad_coord
    )
    flag("INFO", "INFO_COORD_NULL", "lat/lng null", int(bad_coord.sum()))
    flag(
        "INFO",
        "INFO_COORD_OUT_BBOX",
        "outside Daegu-ish bbox (may include Gunwi)",
        int(out_bbox.sum()),
    )

    zero = ((info["lat_n"] == 0) | (info["lng_n"] == 0)) & ~bad_coord
    if zero.any():
        flag("HIGH", "INFO_COORD_ZERO", "lat/lng == 0", int(zero.sum()))

    # identical coordinates many stations (possible bad geocode copy)
    xy = info.dropna(subset=["lat_n", "lng_n"]).copy()
    xy["xy"] = xy["lat_n"].round(6).astype(str) + "," + xy["lng_n"].round(6).astype(str)
    pile = xy.groupby("xy")["statId"].nunique()
    pile_bad = pile[pile >= 10]
    if len(pile_bad):
        top = pile_bad.sort_values(ascending=False).head(5)
        flag(
            "MED",
            "INFO_COORD_COLLISION",
            "≥10 stations share same lat/lng (6dp)",
            f"n_points={len(pile_bad)} top={top.to_dict()}",
        )

    ct = info["chgerType"].fillna("(null)").value_counts()
    print("chgerType top:\n", ct.head(12).to_string())
    known = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "10"}
    blank_ct = info["chgerType"].isna() | (info["chgerType"].astype(str).str.strip() == "")
    if blank_ct.any():
        flag("MED", "INFO_CHGERTYPE_BLANK", "blank chgerType", int(blank_ct.sum()))
    unk_mask = ~info["chgerType"].fillna("").isin(known) & ~blank_ct
    unk_codes = sorted(set(info.loc[unk_mask, "chgerType"].astype(str)))
    if unk_codes:
        flag(
            "MED",
            "INFO_CHGERTYPE_UNKNOWN_CODE",
            f"unmapped codes {unk_codes}",
            int(unk_mask.sum()),
        )

    if "stat" in info.columns:
        print("info.stat dist:\n", info["stat"].fillna("(null)").value_counts().to_string())
        blank_stat = info["stat"].isna() | (info["stat"].astype(str).str.strip() == "")
        if blank_stat.mean() > 0.05:
            flag(
                "MED",
                "INFO_STAT_STALE_RISK",
                "info embeds stat — do NOT use as live availability",
                f"blank={blank_stat.mean():.1%} · treat status from loop1 only",
            )

    ut_blank = (
        info["useTime"].isna()
        | (info["useTime"].astype(str).str.strip() == "")
        | (info["useTime"].astype(str).str.lower().isin(["nan", "none", "~", "-"]))
    )
    flag(
        "INFO",
        "INFO_USETIME_BLANK",
        "useTime blank/vague",
        f"{int(ut_blank.sum())} ({ut_blank.mean():.1%})",
    )

    # always-open false friends
    vague_open = info["useTime"].fillna("").str.contains(
        r"매장\s*(영업|운영)|운영시간\s*이용|시설\s*운영", regex=True, na=False
    )
    if vague_open.any():
        flag(
            "MED",
            "INFO_USETIME_VAGUE",
            "useTime points to store hours (F08→UNKNOWN)",
            int(vague_open.sum()),
        )

    closed = info["useTime"].fillna("").str.contains(r"비개방|개방불가", regex=True, na=False)
    if closed.any():
        flag("INFO", "INFO_USETIME_CLOSED", "useTime says closed/non-open", int(closed.sum()))

    if "delYn" in info.columns:
        print("delYn:\n", info["delYn"].fillna("(null)").value_counts().to_string())
        del_y = (info["delYn"].astype(str).str.upper() == "Y").sum()
        if del_y:
            flag("INFO", "INFO_DELYN_Y", "delYn=Y rows still in dump (filter for service)", int(del_y))

    slow = info["chgerType"].isin(["02", "08"])
    fast = info["chgerType"].isin(["01", "04", "05", "06", "10"])
    weird_slow = slow & info["output_n"].gt(50)
    weird_fast = fast & info["output_n"].lt(20) & info["output_n"].notna()
    if weird_slow.any():
        flag("MED", "INFO_OUTPUT_VS_TYPE_SLOW", "type 02/08 but output>50kW", int(weird_slow.sum()))
    if weird_fast.any():
        flag("LOW", "INFO_OUTPUT_VS_TYPE_FAST", "fast type but output<20kW", int(weird_fast.sum()))

    out_missing = info["output_n"].isna().mean()
    flag("INFO", "INFO_OUTPUT_MISSING", "output null share", f"{out_missing:.1%}")

    print("stations", info["statId"].nunique(), "chargers", len(info))

    if "zcode" in info.columns:
        print("zcode:\n", info["zcode"].fillna("(null)").value_counts().head().to_string())
        n27 = int((info["zcode"].astype(str) != "27").sum())
        if n27:
            flag("MED", "INFO_ZCODE_NOT_27", "non-27 zcode rows", n27)

    # ── HOURS ────────────────────────────────────────────
    hours_p = REPO / "docs/data/extracted/charger/hours/daegu_charger_hours_latest.csv"
    if hours_p.is_file():
        hours = pd.read_csv(hours_p, dtype=str)
        print("\n=== HOURS", len(hours))
        info_stat = set(info["statId"].dropna().unique())
        h_stat = set(hours["statId"].dropna().unique())
        only_h = h_stat - info_stat
        only_i = info_stat - h_stat
        flag(
            "INFO",
            "HOURS_COVERAGE",
            f"hours stations {len(h_stat)} / info stations {len(info_stat)}",
            f"only_hours={len(only_h)} only_info={len(only_i)}",
        )
        if only_h:
            flag("MED", "HOURS_ORPHAN_STAT", "hours statId not in latest info", len(only_h))
        # hours is a curated subset — large only_info is expected but should be documented
        if len(only_i) > 1000:
            flag(
                "MED",
                "HOURS_SUBSET_NOT_FULL",
                "hours is NOT full station universe — do not treat as complete useTime table",
                f"info_only={len(only_i)} · hours may be filtered extract",
            )
        m = hours.merge(
            info.drop_duplicates("statId")[["statId", "useTime"]],
            on="statId",
            how="inner",
            suffixes=("_h", "_i"),
        )
        mism = m["useTime_h"].fillna("") != m["useTime_i"].fillna("")
        if mism.any():
            flag("HIGH", "HOURS_USETIME_MISMATCH", "hours vs info useTime differ", int(mism.sum()))
        else:
            flag("OK", "HOURS_USETIME_MATCH", "hours useTime matches info on overlap", len(m))

        # duplicate stations in hours
        hd = int(hours.duplicated(subset=["statId"], keep=False).sum())
        if hd:
            flag("HIGH", "HOURS_DUP_STAT", "duplicate statId in hours", hd)

    # ── reliability ──────────────────────────────────────
    rel = REPO / "docs/data/analysis/snapshot_all_20260723/reliability_checks.json"
    if rel.is_file():
        data = json.loads(rel.read_text(encoding="utf-8"))
        print("\n=== RELIABILITY keys", list(data.keys())[:12])
        # flexible structure
        failed = []
        if isinstance(data.get("checks"), list):
            for c in data["checks"]:
                if not c.get("pass", c.get("ok", True)):
                    failed.append(c.get("id") or c)
        elif "all_pass" in data and not data["all_pass"]:
            failed.append("all_pass=false")
        if failed:
            flag("HIGH", "STATUS_RELIABILITY_FAIL", "reliability checks failed", str(failed)[:200])
        else:
            flag("OK", "STATUS_RELIABILITY", "snapshot reliability artifact present", "see JSON")

    # gap / age from summary csv if any
    by_date = REPO / "docs/data/analysis/snapshot_all_20260723/reliability_by_date.csv"
    if by_date.is_file():
        bd = pd.read_csv(by_date)
        print("reliability_by_date:\n", bd.head(10).to_string())

    # ── STATUS latest live file ───────────────────────────
    snap_dir = REPO / "docs/data/loops/loop1"
    latest_status = None
    for pattern in ("**/status_snapshots/*.csv", "**/snapshots/*.csv", "**/*status*.csv"):
        found = sorted(snap_dir.glob(pattern))
        if found:
            latest_status = found[-1]
            break
    if latest_status and latest_status.is_file():
        st = pd.read_csv(latest_status, dtype=str, nrows=50000)
        print("\n=== STATUS sample", latest_status.relative_to(REPO), "rows_read", len(st))
        need = ["statId", "chgerId", "stat"]
        for c in need:
            if c not in st.columns:
                flag("HIGH", "STATUS_MISSING_COL", f"{latest_status.name} missing {c}")
        if "stat" in st.columns:
            print("status.stat:\n", st["stat"].fillna("(null)").value_counts().to_string())
            bad_stat = ~st["stat"].fillna("").isin(
                list("123459") + ["01", "02", "03", "04", "05", "09"]
            ) & st["stat"].notna()
            # allow empty?
            if bad_stat.any():
                codes = sorted(set(st.loc[bad_stat, "stat"].astype(str)))[:20]
                flag("MED", "STATUS_UNKNOWN_STAT_CODE", f"unexpected stat codes {codes}", int(bad_stat.sum()))
        if {"statId", "chgerId"}.issubset(st.columns):
            d = int(st.duplicated(subset=["statId", "chgerId"], keep=False).sum())
            if d:
                flag("MED", "STATUS_DUP_IN_TICK", "dup keys inside one status file", d)
    else:
        flag("MED", "STATUS_LIVE_NOT_FOUND", "could not locate live loop1 status csv", str(snap_dir))

    # ── TMAP sample ──────────────────────────────────────
    tmap = REPO / "docs/data/analysis/tmap_eta_sample_20260723/haversine_vs_tmap_eta.csv"
    if tmap.is_file():
        t = pd.read_csv(tmap)
        same = t.groupby(["lat", "lng"])["statId"].nunique()
        multi = same[same > 1]
        if len(multi):
            flag(
                "INFO",
                "TMAP_SHARED_COORDS",
                "multiple statId share identical lat/lng in ETA sample",
                int(len(multi)),
            )
        # ST600335/336 identical — parking lots
        if (t["haversine_km"] < 0.05).any() and (t["tmap_eta_min"] > 3).any():
            flag(
                "INFO",
                "TMAP_NEAR_ORIGIN_ARTIFACT",
                "near-origin stations: tiny haversine but multi-min TMAP (routing/access)",
                "not a bug — do not rank by haversine",
            )

    # ── Parking / daily gaps ─────────────────────────────
    flag(
        "HIGH",
        "PARKING_STILL_FAIL",
        "parking APIs KEY NOT REGISTERED / mock — occupancy features invalid",
        "docs/data/주차/주차_재수집_프로브_20260723.md",
    )

    daily = REPO / "docs/data/extracted/daily"
    if daily.exists():
        for d in ["2026-07-18", "2026-07-19", "2026-07-20"]:
            p = daily / d
            if not p.exists():
                flag("MED", "DAILY_DIR_MISSING", f"no daily folder {d}")
                continue
            has_info = any("info" in f.name.lower() for f in p.rglob("*.csv"))
            if not has_info:
                flag(
                    "MED",
                    "DAILY_INFO_MISSING",
                    f"no charger info dump for {d}",
                    "cannot backfill historical master from API",
                )

    # ── EDA doc inconsistency ────────────────────────────
    # quality_summary still says parking mock 7/23 wait — ok
    # CHECK 0 on events vs old EDA CHECK 68% — document drift
    flag(
        "INFO",
        "DOC_DRIFT_FRESHNESS",
        "EDA §14 CHECK~68% is old D1(statUpdDt-only); §16 event CHECK~0% — do not mix",
        "use §16 / snapshot_all for current freshness",
    )

    out = REPO / "docs/data/analysis/dq_check_20260723"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(issues).to_csv(out / "issues.csv", index=False, encoding="utf-8-sig")
    (out / "issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")

    # severity counts
    sev = pd.Series([i["sev"] for i in issues]).value_counts().to_dict()
    print("\n=== SEV", sev)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Diff daily charger info dumps → team zip on Desktop (new info-master stations)."""
from __future__ import annotations

import json
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


def load_stations(path: Path) -> tuple[set[str], pd.DataFrame]:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    if "statId" not in df.columns:
        for c in df.columns:
            if c.lower() == "statid":
                df = df.rename(columns={c: "statId"})
                break
    keep = [
        c
        for c in (
            "statId",
            "statNm",
            "addr",
            "addrDetail",
            "lat",
            "lng",
            "busiId",
            "bnm",
            "busiNm",
            "delYn",
            "chgerId",
        )
        if c in df.columns
    ]
    st = df[keep].copy()
    if "chgerId" in df.columns:
        n_ch = df.groupby("statId")["chgerId"].nunique()
    else:
        n_ch = df.groupby("statId").size()
    base = st.drop_duplicates("statId").copy()
    base["charger_count"] = base["statId"].map(n_ch).astype(int)
    return set(base["statId"].dropna().astype(str)), base


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    pack_name = f"EV_SafeCharge_인포신규충전소_팀공유_{stamp}"
    out_docs = REPO / "docs" / "팀공유" / f"인포신규충전소_{stamp}"
    out_desk = DESK / pack_name
    out_docs.mkdir(parents=True, exist_ok=True)
    if out_desk.exists():
        shutil.rmtree(out_desk)
    out_desk.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    for p in sorted(
        (REPO / "docs/data/extracted/daily").glob("**/daegu_charger_info_*_latest.csv")
    ):
        m = re.search(r"(20\d{6})", p.name)
        if m:
            paths[m.group(1)] = p
    dates = sorted(paths)
    if len(dates) < 2:
        raise SystemExit("need at least 2 daily info dumps")

    series = {d: load_stations(paths[d]) for d in dates}

    rows: list[dict] = []
    prev: str | None = None
    for d in dates:
        ids, st = series[d]
        if prev is None:
            prev = d
            continue
        pids = series[prev][0]
        for sid in sorted(ids - pids):
            r = st[st["statId"] == sid].iloc[0].to_dict()
            r["appeared_between_from"] = prev
            r["appeared_between_to"] = d
            r["change_type"] = "NEW_IN_INFO"
            rows.append(r)
        for sid in sorted(pids - ids):
            pst = series[prev][1]
            r = pst[pst["statId"] == sid].iloc[0].to_dict()
            r["appeared_between_from"] = prev
            r["appeared_between_to"] = d
            r["change_type"] = "GONE_FROM_INFO"
            rows.append(r)
        prev = d

    chg = pd.DataFrame(rows)
    new = chg[chg["change_type"] == "NEW_IN_INFO"].copy()
    gone = chg[chg["change_type"] == "GONE_FROM_INFO"].copy()

    first, last = dates[0], dates[-1]
    overall_new_ids = series[last][0] - series[first][0]
    overall_new = series[last][1][series[last][1]["statId"].isin(overall_new_ids)].copy()
    overall_new["first_baseline"] = first
    overall_new["compare_to"] = last

    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "definition": (
            "statId newly present in daegu_charger_info daily dump "
            "(info master), not status first-seen"
        ),
        "compare_window": {"from": first, "to": last},
        "station_count_by_date": {d: len(series[d][0]) for d in dates},
        "new_station_count_overall": int(len(overall_new)),
        "gone_event_count": int(len(gone)),
        "note_seohan": "No Seohan-named station newly appeared in info during this window",
        "sources": {
            d: str(paths[d].relative_to(REPO)).replace("\\", "/") for d in dates
        },
    }

    pref = [
        "statId",
        "statNm",
        "addr",
        "charger_count",
        "appeared_between_from",
        "appeared_between_to",
        "change_type",
        "lat",
        "lng",
        "busiNm",
        "bnm",
    ]
    cols = [c for c in pref if c in chg.columns] + [
        c for c in chg.columns if c not in pref
    ]
    chg[cols].to_csv(
        out_docs / "info_master_station_changes.csv", index=False, encoding="utf-8-sig"
    )
    overall_new.to_csv(
        out_docs / "info_new_stations_overall.csv", index=False, encoding="utf-8-sig"
    )
    (out_docs / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 인포(마스터) 신규 충전소 — 팀 공유 ({stamp})",
        "",
        "## 이게 뭐예요?",
        "공공 API **충전소 기본정보(info)** 덤프를 날짜별로 비교해서,",
        "**예전에 없다가 나중에 `statId`가 새로 생긴 충전소**(신설·신규 등록으로 보이는 것)를 모았습니다.",
        "",
        "status에 늦게 찍힌 것과는 **다릅니다**. 인포 마스터에 행이 생긴 경우만 봅니다.",
        "",
        "## 비교 구간",
        f"- 시작: `{first}` ({len(series[first][0])}개 충전소)",
        f"- 끝: `{last}` ({len(series[last][0])}개 충전소)",
        f"- 전체 신규: **{len(overall_new)}곳**",
        "",
        "## 신규 목록 (전체)",
    ]
    for _, r in overall_new.sort_values("statNm").iterrows():
        lines.append(
            f"- `{r['statId']}` {r.get('statNm', '')} / {r.get('addr', '')} "
            f"(충전기 {r.get('charger_count', '?')}대)"
        )

    lines += ["", "## 구간별 변동"]
    for d_from, d_to in zip(dates, dates[1:]):
        n = len(
            new[
                (new["appeared_between_from"] == d_from)
                & (new["appeared_between_to"] == d_to)
            ]
        )
        g = len(
            gone[
                (gone["appeared_between_from"] == d_from)
                & (gone["appeared_between_to"] == d_to)
            ]
        )
        lines.append(f"- `{d_from}` → `{d_to}`: 신규 +{n}, 소실 -{g}")

    lines += [
        "",
        "## 파일",
        "| 파일 | 내용 |",
        "|---|---|",
        "| `info_new_stations_overall.csv` | 구간 전체에서 새로 생긴 충전소 |",
        "| `info_master_station_changes.csv` | 날짜 구간별 신규/소실 |",
        "| `summary.json` | 메타·정의 |",
        "| `README_쉬운설명.md` | 이 문서 |",
        "",
        "## 참고",
        "- **서한** 이름 충전소는 이 기간 인포 신규에 **없음** (이미 있던 것).",
        "- 인포에 생겼다고 해서 그날 공사·개통한 것은 아닐 수 있음 (API 등록 시점).",
        "- 전용 피처 컬럼(`info_first_seen` 등)은 아직 D1에 없음. 필요 시 후속 작업.",
        "",
    ]
    (out_docs / "README_쉬운설명.md").write_text("\n".join(lines), encoding="utf-8")

    for f in out_docs.iterdir():
        shutil.copy2(f, out_desk / f.name)

    zip_path = DESK / f"{pack_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in out_desk.iterdir():
            zf.write(f, arcname=f"{pack_name}/{f.name}")

    print(f"DOCS {out_docs}")
    print(f"DESK_FOLDER {out_desk}")
    print(f"ZIP {zip_path}")
    print(f"NEW {len(overall_new)}")
    print(overall_new[["statId", "statNm"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

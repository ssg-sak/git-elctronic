"""Compare recent Daegu move-in complexes vs EvCharger info (name coverage).

Seed CSV is a monitoring sample — NOT a complete apartment registry.
Match = info.statNm contains key tokens from complex_name (fuzzy, Korean).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
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
DESK = Path.home() / "Desktop"
KST = ZoneInfo("Asia/Seoul")
SEED = REPO / "docs/data/analysis/new_apt_coverage/daegu_2025_movein_seed.csv"
INFO = latest_daily_charger_info() or (
    REPO
    / "docs/data/extracted/daily/2026-07-25/daegu_charger_info_20260725_latest.csv"
)
D1 = (
    REPO
    / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
)
OUT = REPO / f"docs/팀공유/신축단지_인포대조_{datetime.now(KST).strftime('%Y%m%d')}"


def tokens(name: str) -> list[str]:
    """Build search tokens; keep distinctive chunks."""
    n = re.sub(r"[\s\(\)（）·∙\-/]", "", str(name))
    # alias map for common roman/number variants
    aliases = {
        "해링턴플레이스감삼3차": ["해링턴플레이스감삼", "해링턴플레이스감삼Ⅲ", "해링턴플레이스감삼3"],
        "힐스테이트대구역퍼스트2차": ["힐스테이트대구역퍼스트2", "힐스테이트대구역퍼스트"],
        "e편한세상동대구역센텀스퀘어": ["e편한세상동대구역", "이편한세상동대구역센텀"],
        "더센트럴화성파크드림": ["센트럴화성파크드림", "화성파크드림신천"],
        "화성파크드림구수산공원": ["화성파크드림구수산", "구수산공원"],
    }
    if name in aliases:
        return aliases[name]
    out = [n]
    # also without leading 대구
    if n.startswith("대구"):
        out.append(n[2:])
    # shorten brand+core: drop trailing 주상복합 already cleaned
    if len(n) >= 6:
        out.append(n)
    return list(dict.fromkeys(out))


def match_info(info: pd.DataFrame, complex_name: str) -> pd.DataFrame:
    """Strict-ish name search: full/near-full complex tokens only.

    Avoid brand+district AND (e.g. 자이∧대구역) — too many false hits.
    """
    toks = tokens(complex_name)
    mask = None
    for t in toks:
        if len(t) < 6:
            continue
        m = info["statNm"].astype(str).str.contains(re.escape(t), na=False)
        mask = m if mask is None else (mask | m)
    # secondary: strip common suffixes and retry 8+ chars
    core = re.sub(r"[\s\(\)（）]", "", complex_name)
    for n in (8, 10, 12):
        if len(core) >= n:
            m = info["statNm"].astype(str).str.contains(re.escape(core[:n]), na=False)
            mask = m if mask is None else (mask | m)
    if mask is None:
        return info.iloc[0:0]
    return info.loc[mask].copy()


def verdict(n_stations: int, names: list[str], complex_name: str) -> str:
    if n_stations == 0:
        return "MISSING_IN_INFO"
    core = re.sub(r"[\s\(\)]", "", complex_name)
    for nm in names:
        nn = re.sub(r"[\s\(\)]", "", str(nm))
        if core[:8] in nn or nn[:8] in core:
            return "FOUND_NAME"
    return "POSSIBLE_RELATED"


def main() -> int:
    seed = pd.read_csv(SEED, dtype=str)
    seed = seed[seed.get("source", pd.Series(dtype=str)).ne("skip")].copy()
    info = pd.read_csv(INFO, dtype=str, low_memory=False)
    d1 = pd.read_csv(D1, encoding="utf-8-sig", low_memory=False)

    rows = []
    detail_frames = []
    for _, apt in seed.iterrows():
        hit = match_info(info, apt["complex_name"])
        st = hit.drop_duplicates("statId") if len(hit) else hit
        names = st["statNm"].dropna().astype(str).tolist() if len(st) else []
        ids = st["statId"].astype(str).tolist() if len(st) else []
        v = verdict(len(st), names, apt["complex_name"])

        # D1 observation for matched ids
        d1m = d1[d1["statId"].astype(str).isin(ids)] if ids else d1.iloc[0:0]
        unobs = (
            float((d1m["observation_state"] == "UNOBSERVED").mean())
            if len(d1m)
            else None
        )
        hist = (
            float(d1m["history_observed"].mean())
            if len(d1m) and "history_observed" in d1m.columns
            else None
        )

        rows.append(
            {
                **apt.to_dict(),
                "match_verdict": v,
                "matched_stations": int(len(st)),
                "matched_charger_rows": int(len(hit)),
                "matched_statIds": "|".join(ids[:12]),
                "matched_statNms": "|".join(names[:8]),
                "d1_unobserved_rate": unobs,
                "d1_history_rate": hist,
            }
        )
        if len(hit):
            tmp = hit.copy()
            tmp["complex_id"] = apt["complex_id"]
            tmp["complex_name"] = apt["complex_name"]
            tmp["match_verdict"] = v
            detail_frames.append(tmp)

    result = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "new_apt_vs_info.csv", index=False, encoding="utf-8-sig")
    if detail_frames:
        pd.concat(detail_frames, ignore_index=True).to_csv(
            OUT / "new_apt_matched_chargers.csv", index=False, encoding="utf-8-sig"
        )
    else:
        pd.DataFrame().to_csv(
            OUT / "new_apt_matched_chargers.csv", index=False, encoding="utf-8-sig"
        )

    counts = result["match_verdict"].value_counts().to_dict()
    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "seed_n": int(len(result)),
        "info_file": str(INFO.relative_to(REPO)).replace("\\", "/"),
        "verdict_counts": {str(k): int(v) for k, v in counts.items()},
        "missing": result.loc[
            result["match_verdict"] == "MISSING_IN_INFO", "complex_name"
        ].tolist(),
        "found": result.loc[
            result["match_verdict"] == "FOUND_NAME", "complex_name"
        ].tolist(),
        "possible": result.loc[
            result["match_verdict"] == "POSSIBLE_RELATED", "complex_name"
        ].tolist(),
        "caveats": [
            "Seed is 2025 Daegu move-in SAMPLE from public blog lists, not official registry",
            "Name match ≠ on-site chargers inside the complex",
            "MISSING means no similar statNm in EvCharger dump — may still have nearby public chargers",
            "Move-in date ≠ charger registration date",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 신축 단지 입주 × EvCharger info 대조 (1차 샘플)",
        "",
        f"생성: {summary['generated_at']}",
        "",
        "## 방법",
        "1. 2025 대구 입주 예정/완료 단지 **시드 목록** 작성",
        "2. info `statNm`에 단지명·핵심 토큰이 있는지 검색",
        "3. 판정: `FOUND_NAME` / `POSSIBLE_RELATED` / `MISSING_IN_INFO`",
        "",
        "## 결과 요약",
        f"- 시드 단지: **{summary['seed_n']}**",
        f"- FOUND_NAME: **{counts.get('FOUND_NAME', 0)}**",
        f"- POSSIBLE_RELATED: **{counts.get('POSSIBLE_RELATED', 0)}**",
        f"- MISSING_IN_INFO: **{counts.get('MISSING_IN_INFO', 0)}**",
        "",
        "### 이름 매칭 없음 (Type A 후보)",
    ]
    for n in summary["missing"]:
        lines.append(f"- {n}")
    lines += ["", "### 이름 매칭됨"]
    for n in summary["found"]:
        lines.append(f"- {n}")
    if summary["possible"]:
        lines += ["", "### 관련명 가능 (수동 확인)"]
        for n in summary["possible"]:
            lines.append(f"- {n}")
    lines += [
        "",
        "## 주의",
        "- 시드는 **전수조사 아님** (블로그·입주 리스트 기반 샘플).",
        "- 매칭돼도 단지 내부 충전기가 아닐 수 있음.",
        "- 매칭 실패 = 공공 info에 유사 이름이 없음 (인근 공용 충전기는 있을 수 있음).",
        "",
        "## 다음 단계",
        "- 시드 확장 (2024 하반기·2026 입주)",
        "- 주소/좌표 반경 매칭 추가",
        "- 분기 1회 재대조 + KPI K11 보고",
        "",
    ]
    (OUT / "README_쉬운설명.md").write_text("\n".join(lines), encoding="utf-8")

    # desktop zip
    pack = "EV_SafeCharge_신축단지_인포대조_20260731"
    desk = DESK / pack
    if desk.exists():
        shutil.rmtree(desk)
    desk.mkdir(parents=True)
    for f in OUT.iterdir():
        shutil.copy2(f, desk / f.name)
    shutil.copy2(SEED, desk / "daegu_2025_movein_seed.csv")
    zpath = DESK / f"{pack}.zip"
    if zpath.exists():
        zpath.unlink()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in desk.iterdir():
            zf.write(f, arcname=f"{pack}/{f.name}")

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(result[["complex_name", "move_in_ym", "match_verdict", "matched_stations", "matched_statNms"]].to_string(index=False))
    print("ZIP", zpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

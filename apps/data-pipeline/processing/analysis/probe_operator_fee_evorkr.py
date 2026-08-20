"""Ingest ev.or.kr operator fee XLS and probe join to Daegu busiId/busiNm/bnm."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
FEE = REPO / "docs/data/extracted/fee"
OUT = REPO / "docs/data/analysis/fee_operator_evorkr_probe_20260731"
SHARE = REPO / "docs/팀공유/요금_BE전달_20260731"


def _norm(s: object) -> str:
    t = str(s).strip().lower().replace(" ", "")
    for a, b in [
        ("(주)", ""),
        ("주식회사", ""),
        ("㈜", ""),
        ("기후에너지환경부", "환경부"),
        ("한국전력", "한전"),
        ("한국전력공사", "한전"),
    ]:
        t = t.replace(a, b)
    return t


# Manual aliases: fee operator_nm → tokens that may appear in busiNm/bnm
ALIASES: dict[str, list[str]] = {
    "기후에너지환경부": ["환경부", "기후에너지환경부", "환경부"],
    "한국전력": ["한국전력", "한전"],
    "한국전력공사": ["한국전력", "한전"],
    "한전케이디엔": ["한전케이디엔", "한전kdn", "kdn"],
    "gs차지비": ["gs차지비", "차지비"],
    "파워큐브": ["파워큐브"],
    "에버온": ["에버온"],
    "채비": ["채비"],
    "현대자동차": ["현대자동차", "현대차"],
    "테슬라": ["테슬라"],
    "휴맥스이브이": ["휴맥스"],
    "이브이시스": ["이브이시스"],
    "스타코프": ["스타코프"],
    "대영채비": ["대영채비", "채비"],
}


def load_fee_xls(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, engine="xlrd", header=None)
    hdr_i = None
    for i in range(min(12, len(raw))):
        row = [str(x) for x in raw.iloc[i].tolist()]
        if any("사업자" in x for x in row):
            hdr_i = i
            break
    if hdr_i is None:
        raise ValueError("header row with 사업자명 not found")
    # row hdr_i = labels, hdr_i+1 = subheader → data from hdr_i+2
    df = raw.iloc[hdr_i + 2 :].copy()
    df.columns = [
        "seq",
        "operator_nm",
        "fee_type",
        "capacity_class",
        "member_won_per_kwh",
        "member_note",
        "nonmember_won_per_kwh",
        "updated_at",
    ]
    df = df.dropna(subset=["operator_nm"])
    df = df[df["operator_nm"].astype(str).str.strip().ne("")]
    df = df[df["operator_nm"].astype(str).str.lower().ne("nan")]
    df["seq"] = pd.to_numeric(df["seq"], errors="coerce")
    df = df.dropna(subset=["seq"])
    for c in ["member_won_per_kwh", "nonmember_won_per_kwh"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["operator_nm"] = df["operator_nm"].astype(str).str.strip()
    df["fee_type"] = df["fee_type"].astype(str).str.strip()
    df["capacity_class"] = df["capacity_class"].astype(str).str.strip()
    return df.reset_index(drop=True)


def find_info() -> Path:
    info_dir = REPO / "docs/data/extracted/charger/info"
    for pat in ("daegu_charger_info*latest*.csv", "daegu_charger_info*service*.csv", "*.csv"):
        cands = sorted(info_dir.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
        if cands:
            return cands[0]
    raise FileNotFoundError("daegu charger info csv not found")


def match_operator(name: str, fee_ops_norm: dict[str, str]) -> str | None:
    n = _norm(name)
    if n in fee_ops_norm:
        return fee_ops_norm[n]
    for fee_n, canon in fee_ops_norm.items():
        if fee_n and (fee_n in n or n in fee_n):
            return canon
    for key, aliases in ALIASES.items():
        kn = _norm(key)
        if kn in n or n in kn or any(_norm(a) in n for a in aliases):
            # return canonical fee name if present
            for a in [key, *aliases]:
                an = _norm(a)
                if an in fee_ops_norm:
                    return fee_ops_norm[an]
            if kn in fee_ops_norm:
                return fee_ops_norm[kn]
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    src = Path(r"C:\Users\PC\Downloads\전기차 충전 요금(2026-07-31).xls")
    if not src.exists():
        # fallback already in repo
        src = FEE / "ev_or_kr_operator_fee_20260731.xls"
    FEE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)

    dest_xls = FEE / "ev_or_kr_operator_fee_20260731.xls"
    if src.resolve() != dest_xls.resolve():
        shutil.copy2(src, dest_xls)

    fee = load_fee_xls(dest_xls)
    ref_csv = FEE / "fee_tariff_ref_operator_evorkr_20260731.csv"
    fee.to_csv(ref_csv, index=False, encoding="utf-8-sig")

    fee_ops = sorted(fee["operator_nm"].unique())
    fee_ops_norm = {_norm(o): o for o in fee_ops}

    info_path = find_info()
    info = pd.read_csv(info_path, dtype=str, low_memory=False)
    need = ["statId", "busiId", "busiNm", "bnm"]
    for c in need:
        if c not in info.columns:
            raise KeyError(f"missing {c} in {info_path}")
    stations = info[need].drop_duplicates("statId").copy()
    stations["match_name"] = stations["bnm"].fillna(stations["busiNm"])
    stations["fee_operator_nm"] = stations["match_name"].map(
        lambda x: match_operator(x, fee_ops_norm)
    )
    stations["fee_match_level"] = stations["fee_operator_nm"].apply(
        lambda x: "OPERATOR_TYPE" if pd.notna(x) and x else "NONE"
    )

    # attach a representative member rate (급속 100kW미만 우선, else first)
    rep = (
        fee.sort_values(["operator_nm", "capacity_class"])
        .groupby("operator_nm", as_index=False)
        .first()[
            [
                "operator_nm",
                "fee_type",
                "capacity_class",
                "member_won_per_kwh",
                "nonmember_won_per_kwh",
                "updated_at",
            ]
        ]
        .rename(
            columns={
                "operator_nm": "fee_operator_nm",
                "fee_type": "fee_type_sample",
                "capacity_class": "capacity_class_sample",
                "member_won_per_kwh": "member_won_sample",
                "nonmember_won_per_kwh": "nonmember_won_sample",
                "updated_at": "fee_updated_at_sample",
            }
        )
    )
    mapped = stations.merge(rep, on="fee_operator_nm", how="left")
    map_path = OUT / "daegu_station_operator_fee_hint.csv"
    mapped.to_csv(map_path, index=False, encoding="utf-8-sig")

    matched = int((mapped["fee_match_level"] == "OPERATOR_TYPE").sum())
    total = int(len(mapped))
    by_busi = (
        mapped.groupby(["busiId", "busiNm", "fee_operator_nm", "fee_match_level"], dropna=False)
        .size()
        .reset_index(name="stations")
        .sort_values("stations", ascending=False)
    )
    by_busi.to_csv(OUT / "busi_fee_match_summary.csv", index=False, encoding="utf-8-sig")

    summary = {
        "source_xls": str(dest_xls.relative_to(REPO)).replace("\\", "/"),
        "ref_csv": str(ref_csv.relative_to(REPO)).replace("\\", "/"),
        "fee_rows": int(len(fee)),
        "fee_operators": int(fee["operator_nm"].nunique()),
        "info_file": str(info_path.relative_to(REPO)).replace("\\", "/"),
        "daegu_stations": total,
        "matched_stations": matched,
        "match_rate": round(matched / total, 4) if total else 0,
        "unmatched_stations": total - matched,
        "top_unmatched_busiNm": (
            mapped.loc[mapped["fee_match_level"] == "NONE", "busiNm"]
            .value_counts()
            .head(15)
            .to_dict()
        ),
        "top_matched_fee_operator": (
            mapped.loc[mapped["fee_match_level"] == "OPERATOR_TYPE", "fee_operator_nm"]
            .value_counts()
            .head(15)
            .to_dict()
        ),
        "contract": {
            "match_level": "OPERATOR_TYPE (busiNm/bnm → operator fee table)",
            "not_station_exact": True,
            "owner": "backend request-time display",
            "score": "do not use in ranking until agreed",
        },
        "artifacts": {
            "station_hint": str(map_path.relative_to(REPO)).replace("\\", "/"),
            "busi_summary": str((OUT / "busi_fee_match_summary.csv").relative_to(REPO)).replace(
                "\\", "/"
            ),
        },
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# ev.or.kr 운영사 요금 프로브 (2026-07-31)",
                "",
                f"- 요금 행: **{len(fee)}** · 운영사 **{fee['operator_nm'].nunique()}**",
                f"- 대구 충전소 매칭(운영사명): **{matched}/{total}** ({summary['match_rate']:.1%})",
                f"- 정본 CSV: `{ref_csv.relative_to(REPO).as_posix()}`",
                f"- 소별 힌트: `{map_path.relative_to(REPO).as_posix()}`",
                "",
                "**주의:** `statId` 정확 요금이 아니라 **운영사×용량구분** 단가 힌트.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # BE share copies
    shutil.copy2(ref_csv, SHARE / ref_csv.name)
    shutil.copy2(map_path, SHARE / "daegu_station_operator_fee_hint.csv")
    (SHARE / "README_operator_fee.md").write_text(
        "\n".join(
            [
                "# 운영사 요금표 (ev.or.kr) — BE용",
                "",
                f"- 원천: `{dest_xls.name}`",
                f"- 정규화: `{ref_csv.name}`",
                f"- 대구 소→운영사 힌트: `daegu_station_operator_fee_hint.csv` ({matched}/{total})",
                "",
                "match_level=`OPERATOR_TYPE` 만 사용. 매칭 실패는 null.",
                "회원가/비회원가·용량구분(완속/급속)을 요청 시 선택.",
                "추천 점수 반영 금지.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

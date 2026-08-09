"""Build parking-fee related views from local sources (no new API keys).

Two different concepts (do not mix):
  A) charger `parkingFree` Y/N  (~25k charger rows) — EvCharger info
  B) Team5 lot fee fields (~1.7k lots) — amounts / 유료·무료

Writes under docs/data/analysis/parking_fee_YYYYMMDD/ and docs/팀공유/.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_INFO, EXTRACTED_PARKING

KST = ZoneInfo("Asia/Seoul")

RAW_FEE_KEYS = [
    "crgLevySeNm",
    "crgLevlSeNm",
    "gnrlFrstCrgLevyHr",
    "gnrlFrstCrg",
    "gnrlAddCrgLevyHr",
    "gnrlMntbyAddCrg",
    "gnrlOneHrCrg",
    "gnrlOneDayCrg",
    "gnrlCmmtktCrg",
    "residntWikCrg",
    "residntNghtCrg",
    "residntPrvdyCrg",
    "residntFteCrg",
    "stlmMthd",
    "rmrk",
]


def _latest_info() -> Path:
    rolling = EXTRACTED_CHARGER_INFO / "daegu_charger_info_latest.csv"
    if rolling.exists():
        return rolling
    cands = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    if not cands:
        raise FileNotFoundError("no charger info CSV")
    return cands[-1]


def _latest_lot_snapshot() -> Path:
    snaps = sorted(EXTRACTED_PARKING.glob("team5_full_snapshot_*/parking_lot_info.csv"))
    if not snaps:
        raise FileNotFoundError("no team5_full_snapshot parking_lot_info.csv")
    return snaps[-1]


def _parse_raw_fees(raw: object) -> dict[str, object]:
    out: dict[str, object] = {k: None for k in RAW_FEE_KEYS}
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return out
    try:
        obj = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return out
    oper = obj.get("prkOperInfo") if isinstance(obj, dict) else None
    if not isinstance(oper, dict):
        # sometimes raw_item is already oper-ish
        if isinstance(obj, dict):
            oper = obj
        else:
            return out
    for k in RAW_FEE_KEYS:
        if k in oper and oper[k] not in ("", None):
            out[k] = oper[k]
    return out


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs/data/analysis" / f"parking_fee_{stamp}"
    share = REPO / "docs" / "팀공유" / f"주차장요금_추출_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    share.mkdir(parents=True, exist_ok=True)

    # --- A) charger parkingFree ---
    info_path = _latest_info()
    info = pd.read_csv(info_path, dtype=str, low_memory=False)
    keep = [
        c
        for c in (
            "statId",
            "chgerId",
            "statNm",
            "addr",
            "lat",
            "lng",
            "busiNm",
            "parkingFree",
            "limitYn",
            "delYn",
            "fetchedAt",
        )
        if c in info.columns
    ]
    a = info[keep].copy()
    a_path = out / "charger_parkingFree_flags.csv"
    a.to_csv(a_path, index=False, encoding="utf-8-sig")
    a_station = (
        a.groupby("statId", as_index=False)
        .agg(
            statNm=("statNm", "first"),
            addr=("addr", "first"),
            lat=("lat", "first"),
            lng=("lng", "first"),
            chargers=("chgerId", "count"),
            parkingFree_Y=("parkingFree", lambda s: int((s == "Y").sum())),
            parkingFree_N=("parkingFree", lambda s: int((s == "N").sum())),
            parkingFree_mode=(
                "parkingFree",
                lambda s: s.mode().iloc[0] if len(s.mode()) else "",
            ),
        )
    )
    a_station_path = out / "charger_parkingFree_by_station.csv"
    a_station.to_csv(a_station_path, index=False, encoding="utf-8-sig")

    # --- B) Team5 lot fees ---
    lot_path = _latest_lot_snapshot()
    lots = pd.read_csv(lot_path, dtype=str, low_memory=False)
    prefer_cols = [
        "pklt_id",
        "pklt_nm",
        "lat",
        "lot",
        "road_nm_addr",
        "lotno_addr",
        "crg_levy_se_nm",
        "crg_levl_se_nm",
        "gnrl_one_hr_crg",
        "gnrl_one_day_crg",
        "gnrl_frst_crg_levy_hr",
        "gnrl_frst_crg",
        "gnrl_add_crg_levy_hr",
        "gnrl_mntby_add_crg",
        "gnrl_cmmtkt_crg",
        "residnt_wik_crg",
        "residnt_nght_crg",
        "residnt_prvdy_crg",
        "residnt_fte_crg",
        "stlm_mthd",
        "rmrk",
        "collected_at",
        "raw_item",
    ]
    flat_cols = [c for c in prefer_cols if c in lots.columns]
    b = lots[flat_cols].copy()
    if "raw_item" in b.columns:
        parsed = b["raw_item"].map(_parse_raw_fees).apply(pd.Series)
        # keep DB flat cols; add raw_* only where DB empty
        for col in parsed.columns:
            if col not in b.columns:
                b[col] = parsed[col]
        b = b.drop(columns=["raw_item"])
    b_path = out / "team5_parking_lot_fees.csv"
    b.to_csv(b_path, index=False, encoding="utf-8-sig")

    # coverage summary
    def _nn(col: str) -> int:
        return int(b[col].notna().sum()) if col in b.columns else 0

    summary = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "note": "A=~25k charger parkingFree flags; B=~1.7k Team5 lot fee fields. Not the same thing.",
        "A_charger_parkingFree": {
            "source": str(info_path.relative_to(REPO)).replace("\\", "/"),
            "charger_rows": int(len(a)),
            "stations": int(a["statId"].nunique()) if "statId" in a.columns else None,
            "parkingFree_counts": a["parkingFree"].value_counts(dropna=False).to_dict()
            if "parkingFree" in a.columns
            else {},
            "files": {
                "charger_level": str(a_path.relative_to(REPO)).replace("\\", "/"),
                "station_level": str(a_station_path.relative_to(REPO)).replace("\\", "/"),
            },
        },
        "B_team5_lot_fees": {
            "source": str(lot_path.relative_to(REPO)).replace("\\", "/"),
            "lot_rows": int(len(b)),
            "nonnull": {
                "crg_levy_se_nm": _nn("crg_levy_se_nm"),
                "gnrl_one_hr_crg": _nn("gnrl_one_hr_crg"),
                "gnrl_one_day_crg": _nn("gnrl_one_day_crg"),
                "gnrl_frst_crg": _nn("gnrl_frst_crg"),
                "gnrl_cmmtkt_crg": _nn("gnrl_cmmtkt_crg"),
                "residnt_wik_crg": _nn("residnt_wik_crg"),
                "stlm_mthd": _nn("stlm_mthd"),
            },
            "crg_levy_se_nm_counts": (
                b["crg_levy_se_nm"].value_counts(dropna=False).head(10).to_dict()
                if "crg_levy_se_nm" in b.columns
                else {}
            ),
            "file": str(b_path.relative_to(REPO)).replace("\\", "/"),
        },
        "not_fees": [
            "parking realtime history (~20k) is occupancy ticks, not fee amounts",
            "EV charger kWh tariffs under docs/data/extracted/fee/ are charging fees, not parking",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# 주차장·주차요금 관련 데이터 추출 ({stamp})

| 항목 | 내용 |
|---|---|
| **작성** | AI·데이터 ① |
| **한 줄** | “약 2만 건”은 **충전기 parkingFree(Y/N) ~2.5만**에 가깝고, **주차장 요금 금액**은 Team5 **~1.7천 곳**이다. |

---

## A. 충전기 주차 무료 여부 (`parkingFree`) — ~25,433행

| 항목 | 값 |
|---|---:|
| 충전기 행 | **{len(a):,}** |
| parkingFree=Y | **{int((a['parkingFree']=='Y').sum()) if 'parkingFree' in a.columns else 0:,}** |
| parkingFree=N | **{int((a['parkingFree']=='N').sum()) if 'parkingFree' in a.columns else 0:,}** |
| 충전소 수 | **{a['statId'].nunique() if 'statId' in a.columns else 0:,}** |

- 원천: EvCharger `getChargerInfo` · `{info_path.relative_to(REPO).as_posix()}`
- 파일: `charger_parkingFree_flags.csv` · `charger_parkingFree_by_station.csv`
- **금액(원) 없음** — 무료/유료 플래그만

---

## B. Team5 주차장 요금 필드 — ~{len(b):,}곳

| 필드 | non-null |
|---|---:|
| 유료/무료 (`crg_levy_se_nm`) | {_nn('crg_levy_se_nm')} |
| 일반 1시간 (`gnrl_one_hr_crg`) | {_nn('gnrl_one_hr_crg')} |
| 일반 1일 (`gnrl_one_day_crg`) | {_nn('gnrl_one_day_crg')} |
| 최초요금 (`gnrl_frst_crg`) | {_nn('gnrl_frst_crg')} |
| 결제수단 (`stlm_mthd`) | {_nn('stlm_mthd')} |

- 원천: `{lot_path.relative_to(REPO).as_posix()}`
- 파일: `team5_parking_lot_fees.csv` (flat + `raw_item.prkOperInfo` 펼침)
- 1시간 요금이 채워진 곳은 **소수** — 유료/무료 구분 위주

---

## 헷갈리기 쉬운 것

| 데이터 | 행수 | 요금? |
|---|---:|---|
| charger `parkingFree` | ~25k | 플래그만 |
| Team5 lot fees | ~1.7k | 금액·유무료 (부분) |
| realtime history | ~20k | **아님** (점유 이력) |
| extracted/fee (한전 등) | 소량 | **충전 요금** (주차 아님) |

상세: `{out.relative_to(REPO).as_posix()}`

```
DA① | parking fee extract | {stamp}
```
"""
    (out / "README.md").write_text(md, encoding="utf-8")
    (share / "README.md").write_text(md, encoding="utf-8")
    for p in (a_path, a_station_path, b_path, out / "summary.json"):
        (share / p.name).write_bytes(p.read_bytes())

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print("OUT", out)
    print("SHARE", share)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Profile CHA ON fee + KEPCO TOU unit-price CSVs for fee-mapping handoff."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
FEE = REPO / "docs/data/extracted/fee"
OUT = REPO / "docs/data/analysis/fee_mapping_probe_20260730"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cha_path = FEE / "kepco_kdn_cha_on_charging_fee_20251015.csv"
    kepco_path = FEE / "kepco_ev_tou_unit_price_20251031.csv"
    OUT.mkdir(parents=True, exist_ok=True)

    cha = pd.read_csv(cha_path, dtype=str, encoding="utf-8-sig")
    # normalize column aliases
    rename_cha = {
        "충전소ID(cs_id)": "cs_id",
        "충전소명(cs_name)": "cs_name",
        "우편번호(zcode)": "zcode",
        "충전기명(cp_name)": "cp_name",
        "커넥터 ID(connector_id)": "connector_id",
        "충전시작일시(start_timestamp)": "start_ts",
        "충전종료일시(stop_timestamp)": "stop_ts",
        "충전시간(charging_time)": "charging_time",
        "충전요금(합계) (charging_fee)": "charging_fee_won",
    }
    cha = cha.rename(columns={k: v for k, v in rename_cha.items() if k in cha.columns})
    cha["charging_fee_won"] = pd.to_numeric(cha.get("charging_fee_won"), errors="coerce")
    cha["is_fast"] = cha["cp_name"].astype(str).str.contains("급속", na=False)
    cha["is_slow"] = cha["cp_name"].astype(str).str.contains("완속", na=False)

    kepco = pd.read_csv(kepco_path, dtype=str, encoding="cp949")
    kepco = kepco.rename(
        columns={
            "구분": "ym",
            "충전요금": "tariff_name",
            "판매량(경부하)": "sales_offpeak",
            "사용량단가(경부하)": "unit_won_per_kwh_offpeak",
            "판매량(중부하)": "sales_mid",
            "사용량단가(중부하)": "unit_won_per_kwh_mid",
            "판매량(최대부하)": "sales_peak",
            "사용량단가(최대부하)": "unit_won_per_kwh_peak",
            "판매량": "sales_total",
        }
    )
    for c in [
        "unit_won_per_kwh_offpeak",
        "unit_won_per_kwh_mid",
        "unit_won_per_kwh_peak",
    ]:
        kepco[c] = pd.to_numeric(kepco[c], errors="coerce")

    latest = str(kepco["ym"].max())
    kepco_latest = kepco.loc[kepco["ym"] == latest].copy()
    ref = kepco_latest[
        [
            "ym",
            "tariff_name",
            "unit_won_per_kwh_offpeak",
            "unit_won_per_kwh_mid",
            "unit_won_per_kwh_peak",
        ]
    ].drop_duplicates("tariff_name")
    ref_path = FEE / "fee_tariff_ref_kepco_latest.csv"
    ref.to_csv(ref_path, index=False, encoding="utf-8-sig")

    # loose busiId hint map (NOT production join — documentation only)
    busi_hint = [
        {"busiId": "KP", "bnm": "한국전력공사", "suggested_tariff": "한전B2C공용요금제", "match_level": "KEPCO_TOU_HINT"},
        {"busiId": "ME", "bnm": "기후에너지환경부", "suggested_tariff": "한전B2B요금제(환경부)", "match_level": "KEPCO_TOU_HINT"},
        {"busiId": "*", "bnm": "(기타 민간 CPO)", "suggested_tariff": None, "match_level": "NONE"},
    ]
    pd.DataFrame(busi_hint).to_csv(
        OUT / "busi_tariff_hint_draft.csv", index=False, encoding="utf-8-sig"
    )

    summary = {
        "cha_on": {
            "file": str(cha_path.relative_to(REPO)).replace("\\", "/"),
            "rows": int(len(cha)),
            "unique_cs_id": int(cha["cs_id"].nunique()),
            "stations": cha["cs_name"].dropna().unique().tolist(),
            "fee_won_mean": round(float(cha["charging_fee_won"].mean()), 1),
            "fee_won_median": round(float(cha["charging_fee_won"].median()), 1),
            "join_to_daegu_stations": False,
            "reason": "cs_id=000001 only (한전KDN 본사). Not a national station fee table.",
            "use": "SESSION example / UX mock for one site — not D1 fee map",
        },
        "kepco_tou": {
            "file": str(kepco_path.relative_to(REPO)).replace("\\", "/"),
            "rows": int(len(kepco)),
            "ym_range": [str(kepco["ym"].min()), str(kepco["ym"].max())],
            "latest_ym": latest,
            "tariff_names": ref["tariff_name"].tolist(),
            "latest_unit_prices": ref.set_index("tariff_name")[
                [
                    "unit_won_per_kwh_offpeak",
                    "unit_won_per_kwh_mid",
                    "unit_won_per_kwh_peak",
                ]
            ]
            .round(2)
            .to_dict(orient="index"),
            "join_to_daegu_stations": "partial_hint_only",
            "reason": "No statId. Join only via operator/tariff class (busiId KP/ME hints).",
            "use": "fee_tariff_ref for BE request-time TOU lookup",
            "ref_csv": str(ref_path.relative_to(REPO)).replace("\\", "/"),
        },
        "contract": {
            "owner_primary": "backend (request-time display/filter)",
            "da1": "tariff ref + nullable fee_* hints, no fake fill, no score until gate",
            "da2": "score weight only after team agreement",
        },
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# 요금 원천 프로브 (2026-07-30)",
                "",
                "## 결론",
                "- **CHA ON 요금 CSV**: 충전소 **1곳**(한전KDN 본사) 세션 요금 → 대구 D1 매핑 **불가**",
                "- **한전 계시별 단가**: 요금제별 kWh 단가 표 → **백엔드 단가 레퍼런스**로 적합 (statId 직접 조인 아님)",
                "",
                f"- 최신 단가표: `{ref_path.relative_to(REPO).as_posix()}`",
                f"- 요약: `{ (OUT / 'summary.json').relative_to(REPO).as_posix() }`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

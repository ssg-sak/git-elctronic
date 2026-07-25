"""Extract Team5 parking lots that may contain an EV charging station.

This is stricter than the 1 km "nearby parking" join. It creates evidence
grades, not a legal/operational guarantee that a charger is inside a lot.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/extract_parking_with_ev_candidates.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_INFO, EXTRACTED_PARKING  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
JOIN = REPO / "docs/data/spatial_join/join_parking_team5_1000m.csv"
CHARGER = EXTRACTED_CHARGER_INFO / "daegu_charger_info_service_latest.csv"
PARKING = EXTRACTED_PARKING / "daegu_parking_info_team5_latest.csv"
plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def name_key(value: object) -> str:
    cleaned = re.sub(r"[^0-9a-z가-힣]", "", text(value).lower())
    for word in ("전기차", "충전소", "충전기", "주차장", "지상", "지하"):
        cleaned = cleaned.replace(word, "")
    return cleaned


def lot_numbers(value: object) -> set[str]:
    return set(re.findall(r"\d+(?:-\d+)?", text(value)))


def name_match(charger_name: object, parking_name: object) -> bool:
    left, right = name_key(charger_name), name_key(parking_name)
    return bool(min(len(left), len(right)) >= 4 and (left in right or right in left))


def address_number_match(charger_addr: object, parking_addr: object) -> bool:
    left, right = lot_numbers(charger_addr), lot_numbers(parking_addr)
    return bool(left and right and left.intersection(right))


def grade(row: pd.Series) -> str:
    if row["distance_m"] <= 20 and (row["name_match"] or row["address_number_match"]):
        return "STRONG"
    if row["distance_m"] <= 50 or (
        row["distance_m"] <= 100 and (row["name_match"] or row["address_number_match"])
    ):
        return "LIKELY"
    return "NEARBY_ONLY"


def evidence(row: pd.Series) -> str:
    signals = [f"좌표 거리 {row['distance_m']:.1f}m"]
    if row["name_match"]:
        signals.append("충전소명·주차장명 유사")
    if row["address_number_match"]:
        signals.append("주소 번지 숫자 일치")
    if row["distance_m"] > 50:
        signals.append("거리만 가까움: 현장/주소 검토 필요")
    return " · ".join(signals)


def plot_grade_counts(lots: pd.DataFrame, fig_dir: Path) -> Path:
    order = ["STRONG", "LIKELY", "NEARBY_ONLY"]
    values = [int((lots["best_grade"] == item).sum()) for item in order]
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor="#f7f8fa")
    ax.set_facecolor("#fff")
    ax.spines[["top", "right"]].set_visible(False)
    bars = ax.bar(order, values, color=["#18794e", "#f58518", "#9aa5b1"])
    ax.set_title("Team5 주차장 ↔ EV 충전소 공존 후보", loc="left", fontweight="bold")
    ax.set_ylabel("주차장 수")
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(values, default=1) * 0.02, str(value), ha="center")
    out = fig_dir / "01_colocation_grade_counts.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_distance_by_grade(lots: pd.DataFrame, fig_dir: Path) -> Path:
    order = ["STRONG", "LIKELY", "NEARBY_ONLY"]
    values = [
        lots.loc[lots["best_grade"].eq(grade_name), "best_distance_m"].dropna()
        for grade_name in order
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor="#f7f8fa")
    ax.set_facecolor("#fff")
    ax.spines[["top", "right"]].set_visible(False)
    box = ax.boxplot(values, tick_labels=order, patch_artist=True, showfliers=False)
    for patch, color in zip(box["boxes"], ["#18794e", "#f58518", "#9aa5b1"], strict=True):
        patch.set_facecolor(color)
    ax.set_title("등급별 최단 충전소 거리 분포", loc="left", fontweight="bold")
    ax.set_ylabel("거리 (m)")
    out = fig_dir / "02_distance_by_grade.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_parking_type(lots: pd.DataFrame, fig_dir: Path) -> Path:
    order = ["STRONG", "LIKELY", "NEARBY_ONLY"]
    table = pd.crosstab(lots["parking_type"].fillna("미상"), lots["best_grade"])
    table = table.reindex(columns=order, fill_value=0)
    table = table.loc[table.sum(axis=1).sort_values(ascending=False).head(6).index]
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor="#f7f8fa")
    ax.set_facecolor("#fff")
    ax.spines[["top", "right"]].set_visible(False)
    bottom = pd.Series(0, index=table.index)
    colors = {"STRONG": "#18794e", "LIKELY": "#f58518", "NEARBY_ONLY": "#9aa5b1"}
    for grade_name in order:
        ax.bar(table.index, table[grade_name], bottom=bottom, label=grade_name, color=colors[grade_name])
        bottom += table[grade_name]
    ax.set_title("주차장 유형별 EV 공존 후보", loc="left", fontweight="bold")
    ax.set_ylabel("주차장 수")
    ax.legend(frameon=False)
    ax.tick_params(axis="x", labelrotation=15)
    out = fig_dir / "03_parking_type_by_grade.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_spaces_distance(lots: pd.DataFrame, fig_dir: Path) -> Path:
    colors = {"STRONG": "#18794e", "LIKELY": "#f58518", "NEARBY_ONLY": "#9aa5b1"}
    fig, ax = plt.subplots(figsize=(8, 5), facecolor="#f7f8fa")
    ax.set_facecolor("#fff")
    ax.spines[["top", "right"]].set_visible(False)
    for grade_name, color in colors.items():
        subset = lots[lots["best_grade"].eq(grade_name)]
        ax.scatter(
            subset["best_distance_m"],
            subset["parking_spaces_num"],
            s=18,
            alpha=0.65,
            label=grade_name,
            color=color,
        )
    ax.set_title("주차장 규모와 충전소 거리", loc="left", fontweight="bold")
    ax.set_xlabel("최단 충전소 거리 (m)")
    ax.set_ylabel("주차면 수")
    ax.legend(frameon=False)
    out = fig_dir / "04_spaces_vs_distance.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    join = pd.read_csv(JOIN, dtype=str)
    join["matched"] = join["matched"].str.lower().eq("true")
    join["distance_m"] = pd.to_numeric(join["distance_m"], errors="coerce")
    close = join[join["matched"] & join["distance_m"].le(100)].copy()

    charger = pd.read_csv(CHARGER, dtype=str, low_memory=False)
    charger = charger.drop_duplicates("statId")[
        ["statId", "statNm", "addr", "limitYn", "coordinate_quality_flag"]
    ].rename(columns={"statNm": "charger_name", "addr": "charger_addr"})
    parking = pd.read_csv(PARKING, dtype=str, low_memory=False)[
        ["pkltId", "pkltNm", "addr", "roadNmAddr", "lotnoAddr", "prkNocmprt", "pkltSeCd"]
    ].rename(
        columns={
            "pkltId": "matched_id",
            "pkltNm": "parking_name",
            "addr": "parking_addr",
            "prkNocmprt": "parking_spaces",
            "pkltSeCd": "parking_type",
        }
    )
    pairs = close.merge(charger, on="statId", how="left").merge(
        parking, on="matched_id", how="left"
    )
    pairs["name_match"] = pairs.apply(
        lambda row: name_match(row["charger_name"], row["parking_name"]), axis=1
    )
    pairs["address_number_match"] = pairs.apply(
        lambda row: address_number_match(row["charger_addr"], row["parking_addr"]), axis=1
    )
    pairs["evidence_grade"] = pairs.apply(grade, axis=1)
    pairs["evidence"] = pairs.apply(evidence, axis=1)
    pairs = pairs.sort_values(["evidence_grade", "distance_m", "statId"])

    rank = {"STRONG": 0, "LIKELY": 1, "NEARBY_ONLY": 2}
    pairs["_grade_rank"] = pairs["evidence_grade"].map(rank)
    lots = (
        pairs.sort_values(["matched_id", "_grade_rank", "distance_m"])
        .groupby("matched_id", as_index=False)
        .first()
        .rename(columns={"statId": "best_statId", "charger_name": "best_charger_name"})
    )
    counts = pairs.groupby("matched_id").size().rename("ev_station_count").reset_index()
    lots = lots.merge(counts, on="matched_id", how="left").rename(
        columns={"evidence_grade": "best_grade", "distance_m": "best_distance_m"}
    )
    lots = lots.sort_values(["_grade_rank", "best_distance_m", "ev_station_count"]).drop(
        columns="_grade_rank"
    )
    lots["parking_spaces_num"] = pd.to_numeric(lots["parking_spaces"], errors="coerce")

    now = datetime.now(KST)
    out = REPO / "docs/data/analysis" / f"parking_ev_colocation_{now:%Y%m%d}"
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    pair_cols = [
        "matched_id", "parking_name", "parking_addr", "parking_type", "parking_spaces",
        "statId", "charger_name", "charger_addr", "limitYn", "distance_m",
        "name_match", "address_number_match", "evidence_grade", "evidence",
    ]
    lot_cols = [
        "matched_id", "parking_name", "parking_addr", "parking_type", "parking_spaces",
        "best_grade", "best_distance_m", "ev_station_count", "best_statId",
        "best_charger_name", "evidence",
    ]
    pairs[pair_cols].to_csv(out / "charger_parking_pairs_within_100m.csv", index=False, encoding="utf-8-sig")
    lots[lot_cols].to_csv(out / "parking_lots_with_ev_candidates.csv", index=False, encoding="utf-8-sig")
    lots[lots["best_grade"] == "STRONG"][lot_cols].to_csv(
        out / "parking_lots_with_ev_strong.csv", index=False, encoding="utf-8-sig"
    )
    figures = [
        plot_grade_counts(lots, fig_dir),
        plot_distance_by_grade(lots, fig_dir),
        plot_parking_type(lots, fig_dir),
        plot_spaces_distance(lots, fig_dir),
    ]
    grade_counts = {
        grade_name: int((lots["best_grade"] == grade_name).sum())
        for grade_name in ("STRONG", "LIKELY", "NEARBY_ONLY")
    }
    distance_summary = (
        lots.groupby("best_grade")["best_distance_m"]
        .agg(["count", "min", "median", "mean", "max"])
        .reindex(["STRONG", "LIKELY", "NEARBY_ONLY"])
        .reset_index()
    )
    type_summary = (
        pd.crosstab(lots["parking_type"].fillna("미상"), lots["best_grade"])
        .reindex(columns=["STRONG", "LIKELY", "NEARBY_ONLY"], fill_value=0)
        .reset_index()
    )
    distance_summary.to_csv(out / "distance_summary_by_grade.csv", index=False, encoding="utf-8-sig")
    type_summary.to_csv(out / "parking_type_by_grade.csv", index=False, encoding="utf-8-sig")
    summary = {
        "generated_at_kst": now.isoformat(timespec="seconds"),
        "parking_master_rows": int(len(parking)),
        "charger_stations_within_100m": int(len(pairs)),
        "parking_lots_with_ev_candidates": int(len(lots)),
        "grade_counts": grade_counts,
        "policy": {
            "STRONG": "≤20m and a name or address-number signal",
            "LIKELY": "≤50m, or ≤100m with a name/address signal",
            "NEARBY_ONLY": ">50m to ≤100m without a corroborating name/address signal",
        },
        "figures": [str(path.relative_to(out)).replace("\\", "/") for path in figures],
        "not_a_guarantee": "Coordinate/name/address evidence only; validate STRONG samples before product claims.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    distance_lines = "\n".join(
        f"| {row.best_grade} | {int(row.count):,} | {row.median:.1f}m | {row.mean:.1f}m | {row.max:.1f}m |"
        for row in distance_summary.itertuples()
    )
    type_lines = "\n".join(
        f"| {row.parking_type} | {int(row.STRONG):,} | {int(row.LIKELY):,} | {int(row.NEARBY_ONLY):,} |"
        for row in type_summary.sort_values(["STRONG", "LIKELY"], ascending=False).head(8).itertuples()
    )
    report = f"""# Team5 주차장 중 EV 충전소 공존 후보 — EDA 보고서

## 결론

Team5 주차장 {len(parking):,}개 중 **{len(lots):,}개**가 충전소와 100m 이내로 연결됐다.
다만 1km 조인과 달리, 이 결과는 “주차장 안/바로 옆일 가능성”을 보려는 후보 추출이다.
**STRONG만도 현장·주소 표본 검증 전에는 확정값으로 표시하지 않는다.**

| 등급 | 주차장 수 | 의미 |
|---|---:|---|
| STRONG | {grade_counts["STRONG"]:,} | 20m 이내 + 이름 또는 주소 숫자 근거 |
| LIKELY | {grade_counts["LIKELY"]:,} | 50m 이내 또는 100m 이내 추가 근거 |
| NEARBY_ONLY | {grade_counts["NEARBY_ONLY"]:,} | 50~100m 근처일 뿐, 주차장 내부 주장 금지 |

![등급별 후보 수](figures/{figures[0].name})

## 1. 거리 분포

| 등급 | 주차장 수 | 중앙 거리 | 평균 거리 | 최대 거리 |
|---|---:|---:|---:|---:|
{distance_lines}

![등급별 거리](figures/{figures[1].name})

**관찰:** STRONG은 이름/주소 증거까지 있는 20m 이내 보수적 후보이고, LIKELY·NEARBY_ONLY는
거리만으로 같은 주차 구획이라고 단정할 수 없다.

## 2. 주차장 유형

| 주차장 유형 | STRONG | LIKELY | NEARBY_ONLY |
|---|---:|---:|---:|
{type_lines}

![유형별 후보](figures/{figures[2].name})

![주차면 수와 거리](figures/{figures[3].name})

## 3. 지금 활용 가능한 범위

- `parking_lots_with_ev_strong.csv`: 우선 검토·현장 검증 목록
- `parking_lots_with_ev_candidates.csv`: 주차장 단위 요약 목록
- `charger_parking_pairs_within_100m.csv`: 충전소↔주차장 개별 증거

### 권장 제품 규칙

| 등급 | 화면/피처 사용 |
|---|---|
| STRONG | “충전소가 있는 주차장 후보” 필터·주차 realtime 보조 정보 후보 |
| LIKELY | “인근 주차장 정보”로만 표시 |
| NEARBY_ONLY | 거리 정보만; 주차 점유율을 충전소 상태 근거로 사용 금지 |

## 4. 다음에 할 일 (우선순위)

1. **STRONG 55개 표본 검증** — 상위 10~20개를 지도·주소·시설 페이지로 확인해 false positive 비율 기록  
2. **검증 통과 기준 합의** — STRONG 중 이름·주소·좌표가 모두 맞는 대상을 `CONFIRMED`로 승격  
3. **D1에는 등급만 우선 결합** — `parking_ev_colocation_grade`, `parking_ev_spaces`를 보조 피처로 추가하고 점수 반영은 ②와 합의  
4. **2주 누적 후 관계 분석** — CONFIRMED/STRONG에서 `주차 점유율 ↔ 충전 가용률`을 시간 순서로 분석  

## 5. 주의

Team5 주차장은 공영·노상 등도 포함한다. 좌표가 가깝다는 것만으로 충전기가 같은 주차 구획에
있다고 확정할 수 없다. 이 파일은 **주차장 EV 충전소 후보군**이며, 서비스에서 “주차장 내 충전소”
배지를 표시하려면 STRONG 표본을 주소/현장 정보로 재검토해야 한다.

```text
DA① | Team5 parking EV co-location candidates | {now:%Y%m%d}
```
"""
    (out / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

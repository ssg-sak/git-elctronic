"""Build one final EDA pack: docs/팀공유/EDA_최종_20260808/

Pulls E1–E5 from evaluation/results/eda (0808 refresh) + key figures.
Also injects into 최종본_통합_20260808/07_EDA/ when that exists.
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
KST = ZoneInfo("Asia/Seoul")
STAMP = datetime.now(KST).strftime("%Y%m%d")
OUT = REPO / "docs" / "팀공유" / f"EDA_최종_{STAMP}"
EDA = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "eda"
SHARE = REPO / "docs" / "팀공유"
BUNDLE = REPO / "최종본_20260809"


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _read_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _copy_fig(src: Path, dest_name: str, figures: Path) -> str | None:
    if not src.exists():
        return None
    dest = figures / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest_name


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    data = OUT / "data"
    figures = OUT / "figures"
    data.mkdir(parents=True)
    figures.mkdir(parents=True)

    # copy eda artifacts
    for p in sorted(EDA.glob("e*.csv")) + sorted(EDA.glob("e*.json")):
        shutil.copy2(p, data / p.name)

    e1 = _load_json(EDA / "e1_availability_by_hour_meta.json")
    e2 = _load_json(EDA / "e2_availability_by_dow_meta.json")
    e3 = _load_json(EDA / "e3_availability_by_charger_count_meta.json")
    e4 = _load_json(EDA / "e4_availability_by_freshness_meta.json")
    e5 = _load_json(EDA / "e5_panel_quality.json")
    e3_rows = _read_csv(EDA / "e3_availability_by_charger_count.csv")
    e4_rows = _read_csv(EDA / "e4_availability_by_freshness.csv")

    def _latest_share(prefix: str) -> Path | None:
        cands = sorted(
            [p for p in SHARE.glob(f"{prefix}*") if p.is_dir()],
            key=lambda p: p.name,
        )
        return cands[-1] if cands else None

    avail = _latest_share("시간대_가용률_")
    panel = _latest_share("상태수집_패널차트_")
    cong = _latest_share("도시혼잡_시계열_")
    park = _latest_share("주차_혼잡_EDA_")
    fig_map = [
        ((avail / "figures/08_hourly_union_profile.png") if avail else None, "01_시간대_가용률_프로필.png"),
        ((avail / "figures/04_hourly_heatmap.png") if avail else None, "02_시간대_히트맵.png"),
        ((panel / "figures/chart_hourly_availability.png") if panel else None, "03_시간대_가용_패널.png"),
        ((panel / "figures/chart_reliability.png") if panel else None, "04_신뢰도_등급.png"),
        ((panel / "figures/chart_collection_volume.png") if panel else None, "05_수집_볼륨.png"),
        ((cong / "figures/03_hourly_vs_availability.png") if cong else None, "06_혼잡_vs_가용.png"),
        ((cong / "figures/02_hourly_congestion_profile.png") if cong else None, "07_혼잡_시간대.png"),
        ((park / "figures/02_hourly_occupancy.png") if park else None, "08_주차_점유_시간대.png"),
    ]
    figs_ok = []
    for src, name in fig_map:
        if src is not None and _copy_fig(src, name, figures):
            figs_ok.append(name)

    stations = e3.get("stations_total", e4.get("stations"))
    high, normal, check, unobs = (
        e4["high_count"],
        e4["normal_count"],
        e4["check_count"],
        e4["unobserved_count"],
    )

    e3_lines = []
    for r in e3_rows:
        e3_lines.append(
            f"| {r['bucket']} | {r['stations']} | {float(r['d1_avail_mean_observed']):.2f} | {float(r['d2_avail_mean']):.2f} |"
        )

    e4_lines = []
    for r in e4_rows:
        avail = r.get("avail_mean") or "—"
        if avail not in ("", "—"):
            try:
                avail = f"{float(avail):.2f}"
            except ValueError:
                pass
        e4_lines.append(
            f"| {r['age_bucket']} | {r['stations']} | {r['share_pct']}% | {avail} |"
        )

    summary = {
        "stamp": "20260808",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "panel_ts_min": e1.get("panel_ts_min"),
        "panel_ts_max": e1.get("panel_ts_max"),
        "d1_as_of": e4.get("d1_as_of"),
        "e1": {
            "peak_hour": e1["peak_avail_hour"],
            "trough_hour": e1["trough_avail_hour"],
            "morning_8_11": e1["avail_mean_morning_8_11"],
            "evening_18_21": e1["avail_mean_evening_18_21"],
        },
        "e2": {
            "provisional": e2.get("provisional", True),
            "weekday": e2["avail_mean_weekday_pooled"],
            "weekend": e2["avail_mean_weekend_pooled"],
            "calendar_dates_n": len(e2.get("calendar_dates") or []),
        },
        "e3": {"stations_total": stations, "buckets": e3_rows},
        "e4": {
            "high": high,
            "normal": normal,
            "check": check,
            "unobserved": unobs,
        },
        "e5": {
            "total_rows": e5["total_rows"],
            "total_stations": e5["total_stations"],
            "panel_start": e5["panel_start"],
            "panel_end": e5["panel_end"],
            "gaps_gt_25m": e5["total_gaps_gt_25m"],
        },
        "figures": figs_ok,
    }
    (data / "eda_final_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# EDA 최종본 — 2026-08-08

| 항목 | 내용 |
|---|---|
| **작성** | AI·데이터 ① |
| **시간표(패널)** | {e5['total_rows']:,}행 · 충전소 {e5['total_stations']:,} · {e5['panel_start']} ~ {e5['panel_end']} |
| **현재표 as_of** | {e4.get('d1_as_of')} |
| **원천 숫자** | `data/` (E1~E5 CSV·JSON) |
| **그림** | `figures/` |
| **점수** | 없음 → ② |

> 예전 0731 EDA 쉬운보고를 **0808 시간표 재생성·E1~E5 재실행** 기준으로 갈아엎은 **최종 1본**.

---

## 한 줄

**낮(특히 11시 근처)에 더 비고, 밤(22시 근처)에 더 찬다.**  
요일 차이는 보이지만 **아직 잠정**. 신선도는 CHECK가 많아 보이지만 EvCharger 갱신이 느린 소가 많은 것(파이프라인 고장 아님).

---

## E1 — 몇 시에 비나 (시간대)

| 항목 | 값 |
|---|---|
| 가용률 가장 높은 시 | **{e1['peak_avail_hour']}시** |
| 가장 낮은 시 | **{e1['trough_avail_hour']}시** |
| 오전(8~11) 평균 | **{e1['avail_mean_morning_8_11']:.2f}** |
| 저녁(18~21) 평균 | **{e1['avail_mean_evening_18_21']:.2f}** |

쉬운 말: **출근·낮이 저녁·밤보다 여유**.  
그림: `figures/01_시간대_가용률_프로필.png` · `02_시간대_히트맵.png`

---

## E2 — 요일 (잠정)

| 항목 | 값 |
|---|---|
| 평일 평균 가용 | **{e2['avail_mean_weekday_pooled']:.2f}** |
| 주말 평균 가용 | **{e2['avail_mean_weekend_pooled']:.2f}** |
| 달력 일수 | {len(e2.get('calendar_dates') or [])}일 (07-17~08-08) |
| 판정 | **provisional (잠정)** — 요일당 3~4일 수준 |

쉬운 말: 평일이 주말보다 살짝 여유. **규칙으로 못 박지 않음.**

---

## E3 — 충전기 대수

| 버킷 | 충전소 수 | 현재표 관측 가용 | 시간표 평균 가용 |
|---|---:|---:|---:|
{chr(10).join(e3_lines)}

쉬운 말: **대수가 많을수록 시간표 평균 가용은 조금 낮아지는 경향**(바쁜 대형 사이트).  
확정률(confirmed)은 대수↑와 함께 올라감.

---

## E4 — 신선도 (현재표 as_of 기준)

| age 버킷 | 소 수 | 비율 | 가용 평균 |
|---|---:|---:|---:|
{chr(10).join(e4_lines)}

| 요약 | 수 |
|---|---:|
| HIGH (≤5분) | {high} |
| NORMAL (5~15분) | {normal} |
| CHECK (>15분) | {check} |
| 미관측 | {unobs} |

쉬운 말: **CHECK 많음 = 파이프라인 고장이 아님.** 상태 API 갱신이 느린 충전기가 많음. 5/15분 기준 완화하지 않음.  
그림: `figures/04_신뢰도_등급.png`

---

## E5 — 시간표(패널) 품질

| 항목 | 값 |
|---|---:|
| 행 | **{e5['total_rows']:,}** |
| 충전소 | {e5['total_stations']:,} |
| 기간 | {e5['panel_start']} ~ {e5['panel_end']} |
| 25분 초과 gap 구간 | {e5['total_gaps_gt_25m']:,} |
| gap 중앙값(분) | {e5['gap_duration_median_min']:.1f} |

쉬운 말: 시간표는 **약 867만 행**까지 쌓임. gap은 과거 PC 공백·소별 단절 포함 — 학습 시 세그먼트·커버리지로 걸러 씀.  
그림: `figures/05_수집_볼륨.png`

---

## 보조 그림 (혼잡·주차)

| 파일 | 뜻 |
|---|---|
| `06_혼잡_vs_가용.png` | 도시 혼잡 ↔ 가용 |
| `07_혼잡_시간대.png` | 혼잡 시간대 프로필 |
| `08_주차_점유_시간대.png` | 주차 EDA(0731, 참고) — 주차 **점수 금지** |

주차는 EDA 참고만. 추천 점수로 쓰지 않음 (`주차_realtime_428_한계`).

---

## 파일 위치

```
EDA_최종_{STAMP}/
  README.md                 ← 이 문서
  data/                     ← E1~E5 CSV·JSON + eda_final_summary.json
  figures/                  ← 핵심 그림
```

재생성:
```
# E1~E5 재실행 후
python apps/data-pipeline/processing/tools/share/pack_eda_final_20260808.py
```

```
DA① | EDA final | {STAMP}
```
"""
    (OUT / "README.md").write_text(md, encoding="utf-8")

    # inject into repo-root final pack when present
    if BUNDLE.exists():
        dest = BUNDLE / "02_EDA_KPI" / f"EDA_최종_{STAMP}"
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(OUT, dest)
        readme = BUNDLE / "README.md"
        if readme.exists():
            text = readme.read_text(encoding="utf-8")
            if "07_EDA" not in text:
                text = text.replace(
                    "| `06_시각화팩/` | 통합 시각화 팩 복사본 |",
                    "| `06_시각화팩/` | 통합 시각화 팩 복사본 |\n"
                    "| `07_EDA/` | **EDA 최종본** (E1~E5·그림) |",
                )
                readme.write_text(text, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "out": str(OUT),
                "figures": len(figs_ok),
                "panel_rows": e5["total_rows"],
                "in_bundle": (BUNDLE / "07_EDA" / "EDA_최종_20260808").exists(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

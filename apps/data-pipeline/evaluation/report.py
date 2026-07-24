"""실험 결과 JSON/Markdown 리포트 생성."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def to_markdown(result: dict[str, Any]) -> str:
    inp = result["input_counts"]
    proc = result["processing_results"]
    rel = proc["reliability_grade_distribution"]
    avail = proc["availability"]
    src = result["data_sources"]

    lines = [
        "# EV SafeCharge 데이터 가공 실험 결과",
        "",
        f"- **실험 ID**: `{result['experiment_id']}`",
        f"- **실행 시각**: {result['run_at']}",
        "",
        "## 1. 입력 데이터",
        "",
        "| 항목 | 건수 |",
        "|---|---:|",
        f"| 충전소 info (충전기 row) | {inp['info_rows']:,} |",
        f"| 충전기 status | {inp['status_rows']:,} |",
        f"| 충전소 (고유) | {inp['stations_raw']:,} |",
        f"| 주차 기본정보 (mock) | {inp['parking_info_rows']:,} |",
        f"| 주차 실시간 (mock) | {inp['parking_realtime_rows']:,} |",
        f"| TourAPI | {inp['tour_rows']:,} |",
        f"| 기상 실황 | {inp['weather_ncst_rows']:,} |",
        f"| 기상 예보 | {inp['weather_fcst_rows']:,} |",
        "",
        "## 2. 가공 결과",
        "",
        f"- 정제 후 충전소: **{proc['stations_after_cleansing']:,}** "
        f"(제거 {proc['stations_dropped_by_cleansing']:,})",
        f"- 정제 후 충전기: **{proc['chargers_after_cleansing']:,}**",
        f"- 평균 사용 가능 비율: **{avail['avg_availability_rate']:.1%}**",
        f"- 사용 가능 0대 충전소: **{avail['zero_available_stations']:,}**",
        "",
        "### 신뢰도 등급 분포",
        "",
        "| 등급 | 충전소 수 |",
        "|---|---:|",
    ]
    for grade in ["HIGH", "NORMAL", "CHECK_REQUIRED"]:
        lines.append(f"| {grade} | {rel.get(grade, 0):,} |")

    lines.extend([
        "",
        "### 충전기 상태 분포 (정제 후)",
        "",
        "| 상태 | 건수 |",
        "|---|---:|",
    ])
    for stat, cnt in proc["charger_stat_distribution"].items():
        lines.append(f"| {stat} | {cnt:,} |")

    lines.extend([
        "",
        "## 3. 데이터 소스",
        "",
        f"- extracted: `{src['extracted_dir']}`",
        f"- info: `{src['charger_info']}`",
        f"- status: `{src['charger_status']}`",
        "",
        "## 4. 샘플 (상위 10개 충전소)",
        "",
        "| stat_id | stat_nm | total | available | reliability |",
        "|---|---|---:|---:|---|",
    ])
    for row in result["sample_processed_stations"]:
        lines.append(
            f"| {row['stat_id']} | {row['stat_nm']} | {row['total_chargers']} | "
            f"{row['available_chargers']} | {row['reliability_grade']} |"
        )

    return "\n".join(lines) + "\n"


def save_report(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    exp_id = result["experiment_id"]
    json_path = output_dir / f"experiment_{exp_id}.json"
    md_path = output_dir / f"experiment_{exp_id}.md"

    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(result), encoding="utf-8")
    return json_path, md_path

"""추출 CSV 기반 가공 실험 실행 및 지표 산출."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

EVAL_DIR = Path(__file__).resolve().parent
PROCESSING_DIR = EVAL_DIR.parent / "processing"
sys.path.insert(0, str(PROCESSING_DIR))

import aggregation  # noqa: E402
import cleansing  # noqa: E402
import reliability  # noqa: E402
from csv_loader import DEFAULT_EXTRACTED_DIR, load_extracted_dataset  # noqa: E402


def _grade_distribution(series: pd.Series) -> dict[str, int]:
    return {str(k): int(v) for k, v in series.value_counts().to_dict().items()}


def _availability_summary(df_stations: pd.DataFrame) -> dict[str, float]:
    if df_stations.empty:
        return {"avg_availability_rate": 0.0, "zero_available_stations": 0}
    rates = df_stations["available_chargers"] / df_stations["total_chargers"].clip(lower=1)
    return {
        "avg_availability_rate": round(float(rates.mean()), 4),
        "zero_available_stations": int((df_stations["available_chargers"] == 0).sum()),
    }


def run_experiment(extracted_dir: Path | None = None, base_time: datetime | None = None) -> dict[str, Any]:
    """추출 데이터로 정제/집계/신뢰도 실험 후 결과 dict 반환."""
    now = base_time or datetime.now().astimezone()
    data_dir = extracted_dir or DEFAULT_EXTRACTED_DIR
    loaded = load_extracted_dataset(data_dir)

    if "stations_raw" not in loaded or "chargers_raw" not in loaded:
        raise FileNotFoundError(
            f"충전소 info/status CSV가 필요합니다. 경로 확인: {data_dir}"
        )

    df_stations_raw: pd.DataFrame = loaded["stations_raw"]  # type: ignore[assignment]
    df_chargers_raw: pd.DataFrame = loaded["chargers_raw"]  # type: ignore[assignment]

    df_stations_clean = cleansing.clean_stations(df_stations_raw)
    df_chargers_clean = cleansing.clean_chargers(df_chargers_raw)
    df_agg = aggregation.aggregate_chargers(df_chargers_clean)
    df_rel = reliability.calculate_reliability(df_chargers_clean, now)

    df_processed = df_stations_clean[["stat_id", "stat_nm", "addr", "lat", "lng"]].merge(
        df_agg, on="stat_id", how="left"
    ).merge(df_rel, on="stat_id", how="left")
    df_processed["total_chargers"] = df_processed["total_chargers"].fillna(0).astype(int)
    df_processed["available_chargers"] = df_processed["available_chargers"].fillna(0).astype(int)
    df_processed["reliability_grade"] = df_processed["reliability_grade"].fillna("CHECK_REQUIRED")

    stat_distribution = df_chargers_clean["stat"].value_counts().to_dict()
    chger_type_distribution = df_chargers_clean["chger_type"].value_counts().to_dict()

    experiment: dict[str, Any] = {
        "experiment_id": now.strftime("%Y%m%d_%H%M%S"),
        "run_at": now.isoformat(timespec="seconds"),
        "data_sources": {
            "extracted_dir": str(data_dir.resolve()),
            "charger_info": str(loaded.get("info_path", "")),
            "charger_status": str(loaded.get("status_path", "")),
            "parking_info": str(loaded.get("parking_info_path") or ""),
            "parking_realtime": str(loaded.get("parking_rt_path") or ""),
            "tour": str(loaded.get("tour_path") or ""),
            "weather_ncst": str(loaded.get("weather_ncst_path") or ""),
            "weather_fcst": str(loaded.get("weather_fcst_path") or ""),
        },
        "input_counts": {
            "info_rows": int(len(loaded.get("info", []))),
            "status_rows": int(len(loaded.get("status", []))),
            "stations_raw": int(len(df_stations_raw)),
            "chargers_raw": int(len(df_chargers_raw)),
            "parking_info_rows": int(len(loaded["parking_info"])) if "parking_info" in loaded else 0,
            "parking_realtime_rows": int(len(loaded["parking_rt"])) if "parking_rt" in loaded else 0,
            "tour_rows": int(len(loaded["tour"])) if "tour" in loaded else 0,
            "weather_ncst_rows": int(len(loaded["weather_ncst"])) if "weather_ncst" in loaded else 0,
            "weather_fcst_rows": int(len(loaded["weather_fcst"])) if "weather_fcst" in loaded else 0,
        },
        "processing_results": {
            "stations_after_cleansing": int(len(df_stations_clean)),
            "chargers_after_cleansing": int(len(df_chargers_clean)),
            "stations_dropped_by_cleansing": int(len(df_stations_raw) - len(df_stations_clean)),
            "reliability_grade_distribution": _grade_distribution(df_processed["reliability_grade"]),
            "charger_stat_distribution": {str(k): int(v) for k, v in stat_distribution.items()},
            "charger_type_top5": {
                str(k): int(v)
                for k, v in list(chger_type_distribution.items())[:5]
            },
            "availability": _availability_summary(df_processed),
        },
        "sample_processed_stations": df_processed.head(10).to_dict(orient="records"),
    }
    return experiment

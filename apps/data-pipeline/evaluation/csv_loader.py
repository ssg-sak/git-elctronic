"""추출 CSV(docs/data/extracted) -> 가공 파이프라인 입력 DataFrame 변환."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parents[2]
DEFAULT_EXTRACTED_DIR = REPO_ROOT / "docs" / "data" / "extracted"


def _latest_csv(directory: Path, prefix: str) -> Path | None:
    matches = sorted(
        directory.rglob(f"{prefix}*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def load_charger_info_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    rename = {
        "statId": "stat_id",
        "statNm": "stat_nm",
        "addr": "addr",
        "lat": "lat",
        "lng": "lng",
        "chgerId": "chger_id",
        "chgerType": "chger_type",
        "output": "output",
        "useTime": "use_time",
        "busiNm": "busi_nm",
        "parkingFree": "parking_free",
        "delYn": "del_yn",
        "fetchedAt": "fetched_at",
    }
    return df.rename(columns=rename)


def load_charger_status_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    rename = {
        "statId": "stat_id",
        "statNm": "stat_nm",
        "chgerId": "chger_id",
        "stat": "stat",
        "statUpdDt": "stat_updated_at",
        "fetchedAt": "fetched_at",
    }
    return df.rename(columns=rename)


def info_to_stations(df_info: pd.DataFrame) -> pd.DataFrame:
    """충전소 정보 CSV(충전기 단위 row) -> charging_stations 스키마."""
    cols = ["stat_id", "stat_nm", "addr", "lat", "lng", "busi_nm", "use_time", "parking_free", "del_yn"]
    grouped = (
        df_info.sort_values(["stat_id", "chger_id"])
        .groupby("stat_id", as_index=False)
        .first()[cols]
    )
    grouped["busi_call"] = ""
    return grouped


def merge_chargers(df_info: pd.DataFrame, df_status: pd.DataFrame) -> pd.DataFrame:
    """정보 CSV + 상태 CSV -> chargers 스키마."""
    info_cols = ["stat_id", "chger_id", "chger_type", "output"]
    base = df_info[info_cols].drop_duplicates(subset=["stat_id", "chger_id"])
    status_cols = ["stat_id", "chger_id", "stat", "stat_updated_at", "fetched_at"]
    status = df_status[status_cols].drop_duplicates(subset=["stat_id", "chger_id"])
    merged = base.merge(status, on=["stat_id", "chger_id"], how="left")
    merged["stat_nm"] = ""
    merged["method"] = ""
    merged["stat"] = merged["stat"].fillna("")
    merged["stat_updated_at"] = merged["stat_updated_at"].fillna("")
    merged["fetched_at"] = merged["fetched_at"].fillna("")
    return merged


def load_extracted_dataset(extracted_dir: Path | None = None) -> dict[str, pd.DataFrame | Path | None]:
    """docs/data/extracted 최신 CSV 묶음 로드."""
    directory = extracted_dir or DEFAULT_EXTRACTED_DIR
    info_path = _latest_csv(directory, "daegu_charger_info_")
    status_path = _latest_csv(directory, "daegu_charger_status_")
    parking_info_path = directory / "parking" / "daegu_parking_info_team5_latest.csv"
    parking_rt_path = directory / "parking" / "daegu_parking_realtime_team5_latest.csv"
    tour_path = _latest_csv(directory, "daegu_tour_attractions_")
    weather_ncst_path = _latest_csv(directory, "daegu_weather_ultra_ncst_")
    weather_fcst_path = _latest_csv(directory, "daegu_weather_ultra_fcst_")

    result: dict[str, pd.DataFrame | Path | None] = {
        "info_path": info_path,
        "status_path": status_path,
        "parking_info_path": parking_info_path if parking_info_path.exists() else None,
        "parking_rt_path": parking_rt_path if parking_rt_path.exists() else None,
        "tour_path": tour_path,
        "weather_ncst_path": weather_ncst_path,
        "weather_fcst_path": weather_fcst_path,
    }

    if info_path:
        df_info = load_charger_info_csv(info_path)
        result["info"] = df_info
        result["stations_raw"] = info_to_stations(df_info)
    if status_path:
        df_status = load_charger_status_csv(status_path)
        result["status"] = df_status
    if info_path and status_path:
        result["chargers_raw"] = merge_chargers(result["info"], result["status"])  # type: ignore[arg-type]

    for key, path in [
        ("parking_info", parking_info_path),
        ("parking_rt", parking_rt_path),
        ("tour", tour_path),
        ("weather_ncst", weather_ncst_path),
        ("weather_fcst", weather_fcst_path),
    ]:
        if path and path.exists():
            result[key] = pd.read_csv(path, dtype=str)

    return result

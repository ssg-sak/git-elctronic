"""Weather long-format cleaning + wide forecast table."""
from __future__ import annotations

import re

import pandas as pd

from .utils import parse_kst_datetime


def _combine_dt(date_s: pd.Series, time_s: pd.Series) -> pd.Series:
    d = date_s.astype("string").str.zfill(8)
    t = time_s.astype("string").str.zfill(4)
    raw = d + t
    return pd.to_datetime(raw, format="%Y%m%d%H%M", errors="coerce")


def parse_precip_value(raw) -> tuple[object, object, bool]:
    """Return (value_numeric, value_raw, parse_error)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return pd.NA, pd.NA, False
    s = str(raw).strip()
    if s in ("강수없음", "적설없음"):
        return 0.0, s, False
    if "미만" in s:
        m = re.search(r"([0-9.]+)", s)
        return (float(m.group(1)) if m else pd.NA), s, m is None
    m = re.search(r"([0-9.]+)\s*mm", s, re.I)
    if m:
        return float(m.group(1)), s, False
    try:
        return float(s), s, False
    except ValueError:
        return pd.NA, s, True


NUMERIC_CATS = {"TMP", "T1H", "REH", "WSD", "UUU", "VVV", "VEC", "POP", "WAV"}
CODE_CATS = {"SKY", "PTY"}
PRECIP_CATS = {"PCP", "RN1", "SNO"}


def _parse_values(category: pd.Series, values: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    nums, raws, errs = [], [], []
    for cat, val in zip(category.tolist(), values.tolist()):
        c = str(cat) if pd.notna(cat) else ""
        raws.append(val)
        if c in PRECIP_CATS:
            n, r, e = parse_precip_value(val)
            nums.append(n)
            errs.append(e)
        elif c in NUMERIC_CATS:
            try:
                nums.append(float(val))
                errs.append(False)
            except (TypeError, ValueError):
                nums.append(pd.NA)
                errs.append(True)
        elif c in CODE_CATS:
            nums.append(pd.NA)
            errs.append(False)
        else:
            try:
                nums.append(float(val))
                errs.append(False)
            except (TypeError, ValueError):
                nums.append(pd.NA)
                errs.append(pd.notna(val))
    return (
        pd.Series(nums, index=category.index),
        pd.Series(raws, index=category.index, dtype="string"),
        pd.Series(errs, index=category.index),
    )


def clean_weather_forecast(df: pd.DataFrame, kind: str) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"kind": kind, "steps": []}
    out = df.copy()
    for c in ("baseDate", "baseTime", "fcstDate", "fcstTime", "category", "nx", "ny"):
        if c in out.columns:
            out[c] = out[c].astype("string")
    value_col = "fcstValue" if "fcstValue" in out.columns else "obsrValue"
    out["base_datetime"] = _combine_dt(out["baseDate"], out["baseTime"])
    if "fcstDate" in out.columns:
        out["forecast_datetime"] = _combine_dt(out["fcstDate"], out["fcstTime"])
    else:
        out["forecast_datetime"] = out["base_datetime"]
    out["fetched_datetime"], out["fetched_parse_failed"] = parse_kst_datetime(out["fetchedAt"])

    n, r, e = _parse_values(out["category"], out[value_col])
    out["value_raw"] = r
    out["value_numeric"] = n
    out["weather_parse_error"] = e

    if kind == "ncst":
        pk = ["baseDate", "baseTime", "category", "nx", "ny"]
    else:
        pk = ["baseDate", "baseTime", "fcstDate", "fcstTime", "category", "nx", "ny"]
    meta["pk_duplicates"] = int(out.duplicated(subset=[c for c in pk if c in out.columns]).sum())
    meta["unique_grids"] = sorted(set(zip(out["nx"].tolist(), out["ny"].tolist())))
    meta["single_grid_only"] = len(meta["unique_grids"]) == 1
    if meta["single_grid_only"]:
        meta["steps"].append("ONLY nx=89,ny=90 — do not treat as city-wide spatial weather")
    return out, meta


def weather_to_wide(fcst: pd.DataFrame) -> pd.DataFrame:
    """Wide by forecast_datetime + nx/ny using value_numeric (and raw for codes)."""
    tmp = fcst.copy()
    # prefer numeric; for SKY/PTY use raw
    tmp["cell"] = tmp["value_numeric"]
    code_mask = tmp["category"].isin(list(CODE_CATS))
    tmp.loc[code_mask, "cell"] = tmp.loc[code_mask, "value_raw"]
    wide = tmp.pivot_table(
        index=["forecast_datetime", "nx", "ny"],
        columns="category",
        values="cell",
        aggfunc="first",
    ).reset_index()
    wide.columns = [str(c) for c in wide.columns]
    return wide

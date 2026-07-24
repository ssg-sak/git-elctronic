"""Common string/datetime helpers for preprocessing."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

NULL_TOKENS = {"", "null", "none", "nan", "-", "na", "n/a"}


def normalize_str_series(s: pd.Series) -> pd.Series:
    out = s.astype("string")
    out = out.str.replace("\t", " ", regex=False)
    out = out.str.replace("\r", " ", regex=False)
    out = out.str.replace("\n", " ", regex=False)
    out = out.str.replace(r"\s+", " ", regex=True)
    out = out.str.strip()
    mask = out.str.lower().isin(NULL_TOKENS)
    out = out.mask(mask, pd.NA)
    return out


def normalize_dataframe_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]) or str(out[col].dtype) == "string":
            out[col] = normalize_str_series(out[col])
    return out


def parse_kst_datetime(series: pd.Series, fmt: str | None = None) -> tuple[pd.Series, pd.Series]:
    """Return (datetime_series, parse_failed_bool)."""
    raw = normalize_str_series(series.astype("string"))
    if fmt:
        dt = pd.to_datetime(raw, format=fmt, errors="coerce")
    else:
        dt = pd.to_datetime(raw, errors="coerce")
    failed = raw.notna() & dt.isna()
    return dt, failed


def try_repair_mojibake(text: Any) -> tuple[Any, bool]:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return text, False
    if not isinstance(text, str):
        return text, False
    # Heuristic: common mojibake patterns
    if not any(ch in text for ch in ("Ã", "Â", "ì", "ë", "ê", "å", "ã", "Ð", "Ñ")):
        # also check if looks like broken korean via replacement chars
        if "\ufffd" not in text and not re.search(r"[À-ÿ]{2,}", text):
            return text, False
    try:
        repaired = text.encode("latin1").decode("utf-8")
        if repaired != text and ("\ufffd" not in repaired):
            return repaired, True
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return text, False


def repair_mojibake_column(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    repaired_flags = []
    values = []
    for v in s.tolist():
        nv, flag = try_repair_mojibake(v if pd.notna(v) else None)
        values.append(nv if nv is not None else pd.NA)
        repaired_flags.append(flag)
    return pd.Series(values, index=s.index, dtype="string"), pd.Series(repaired_flags, index=s.index)


def normalize_busi_name(name: Any) -> Any:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return pd.NA
    s = str(name)
    s = re.sub(r"\s+", " ", s).strip()
    # light normalization only
    s = s.replace("(주)", "㈜").replace("㈜ ", "㈜")
    return s


def save_table(df: pd.DataFrame, path_stem: Path) -> None:
    path_stem.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path_stem.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(path_stem.with_suffix(".parquet"), index=False)
    except Exception:
        # parquet optional if engine missing
        pass


def load_stat_code_map(config_path: Path) -> dict[str, str]:
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(k): str(v) for k, v in data.get("stat_code_map", {}).items()}


def missing_report(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(df)
    for col in df.columns:
        miss = int(df[col].isna().sum()) if n else 0
        rows.append({"column": col, "missing": miss, "missing_rate": (miss / n) if n else 0.0})
    return pd.DataFrame(rows)

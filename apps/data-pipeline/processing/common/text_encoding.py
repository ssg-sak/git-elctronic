"""UTF-8 mojibake repair helpers (latin1 misread as UTF-8)."""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

NULL_TOKENS = {"", "null", "none", "nan", "-", "na", "n/a"}


def try_repair_mojibake(text: Any) -> tuple[Any, bool]:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return text, False
    if not isinstance(text, str):
        return text, False
    if not any(ch in text for ch in ("Ã", "Â", "ì", "ë", "ê", "å", "ã", "Ð", "Ñ")):
        if "\ufffd" not in text and not re.search(r"[À-ÿ]{2,}", text):
            return text, False
    try:
        repaired = text.encode("latin1").decode("utf-8")
        if repaired != text and "\ufffd" not in repaired:
            return repaired, True
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return text, False


def repair_mojibake_column(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    repaired_flags: list[bool] = []
    values: list[Any] = []
    for v in s.tolist():
        nv, flag = try_repair_mojibake(v if pd.notna(v) else None)
        values.append(nv if nv is not None else pd.NA)
        repaired_flags.append(flag)
    return (
        pd.Series(values, index=s.index, dtype="string"),
        pd.Series(repaired_flags, index=s.index),
    )


def _text_columns(df: pd.DataFrame, columns: list[str] | None) -> list[str]:
    if columns:
        return [c for c in columns if c in df.columns]
    out: list[str] = []
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or str(df[col].dtype) == "string":
            out.append(col)
    return out


def repair_dataframe_strings(
    df: pd.DataFrame,
    columns: list[str] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Repair mojibake in object/string columns. Returns (df, repaired_cell_count)."""
    out = df.copy()
    cols = _text_columns(out, columns)
    repaired_total = 0
    for col in cols:
        repaired, flags = repair_mojibake_column(out[col].astype("string"))
        out[col] = repaired
        repaired_total += int(flags.sum())
    return out, repaired_total

"""Load CSVs with explicit string dtypes. Never modify source files."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import paths
from .utils import normalize_dataframe_strings


def _dtype_map(columns: list[str]) -> dict[str, str]:
    return {c: "string" for c in columns if c in paths.STRING_ID_COLS or True}


def read_csv_safe(path: Path) -> pd.DataFrame:
    if any(tok in path.name for tok in paths.EXCLUDE_NAME_SUBSTRINGS):
        raise ValueError(f"Excluded duplicate file: {path.name}")
    # Read all as string first to preserve leading zeros
    df = pd.read_csv(path, dtype="string", keep_default_na=False, na_filter=False)
    df = normalize_dataframe_strings(df)
    return df


def load_all() -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    manifest = []
    for key, fname in paths.FILES.items():
        if any(tok in fname for tok in paths.EXCLUDE_NAME_SUBSTRINGS):
            continue
        path = paths.EXTRACTED_DIR / fname
        if not path.exists():
            raise FileNotFoundError(path)
        df = read_csv_safe(path)
        out[key] = df
        manifest.append({
            "key": key,
            "file": fname,
            "rows": len(df),
            "cols": len(df.columns),
            "columns": list(df.columns),
            "source_path": str(path),
            "read_only": True,
        })
    paths.RAW_DIR.mkdir(parents=True, exist_ok=True)
    (paths.RAW_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (paths.RAW_DIR / "README.md").write_text(
        "# raw\n\n원본 CSV는 `docs/data/extracted/` 에 있으며 **읽기 전용**이다.\n"
        "이 폴더에는 `manifest.json` 만 둔다. 원본을 복사·수정하지 않는다.\n"
        "`*(1).csv` 중복본은 로드하지 않는다.\n",
        encoding="utf-8",
    )
    return out

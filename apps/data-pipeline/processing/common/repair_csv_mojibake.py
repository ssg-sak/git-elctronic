"""Repair UTF-8 mojibake in CSV string columns (latin1 misread).

Usage:
  python repair_csv_mojibake.py path/to/file.csv --in-place
  python repair_csv_mojibake.py path/to/file.csv -o fixed.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from common.text_encoding import repair_dataframe_strings

from _bootstrap import ensure_paths

REPO = ensure_paths()


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair mojibake in CSV text columns")
    parser.add_argument("csv", type=Path, help="Input CSV path")
    parser.add_argument("-o", "--output", type=Path, help="Output path (default: stdout preview only)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input file")
    parser.add_argument(
        "--columns",
        nargs="*",
        help="Columns to repair (default: all object columns)",
    )
    args = parser.parse_args()

    path = args.csv if args.csv.is_absolute() else REPO / args.csv
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    df = pd.read_csv(path, dtype="string", keep_default_na=False)
    repaired_df, count = repair_dataframe_strings(df, args.columns)

    if args.in_place:
        out_path = path
    elif args.output:
        out_path = args.output if args.output.is_absolute() else REPO / args.output
    else:
        print(f"Would repair {count} cells in {path.name}")
        print(repaired_df.head(3).to_string())
        print("Use --in-place or -o to save.", file=sys.stderr)
        return 0

    repaired_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Repaired {count} cells -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

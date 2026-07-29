"""Build an auditable sample of raw rows before/after snapshot dedupe."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
DEFAULT_OUT = REPO / "docs" / "data" / "quality"
KEYS = ["snapshotId", "statId", "chgerId"]


def load_raw() -> pd.DataFrame:
    from loop_paths import LOOP1_SNAPSHOTS, iter_status_csvs

    frames = []
    for path in iter_status_csvs(LOOP1_SNAPSHOTS):
        frame = pd.read_csv(path, dtype="string")
        frame["source_file"] = str(path.relative_to(REPO)).replace("\\", "/")
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("no loop1 status CSV files found")
    data = pd.concat(frames, ignore_index=True)
    data["__row_order"] = range(len(data))
    data["__stat_updated"] = pd.to_datetime(
        data["statUpdDt"].astype("string").str.replace(r"\.0$", "", regex=True),
        format="%Y%m%d%H%M%S",
        errors="coerce",
    )
    data["__page_no"] = pd.to_numeric(data.get("pageNo"), errors="coerce").fillna(-1)
    return data


def build_sample(data: pd.DataFrame, sample_groups: int, seed: int) -> tuple[pd.DataFrame, dict]:
    duplicate_mask = data.duplicated(KEYS, keep=False)
    duplicate = data.loc[duplicate_mask].copy()
    grouped = duplicate.groupby(KEYS, dropna=False, sort=False)
    group_rows = []
    for key, group in grouped:
        ordered = group.sort_values(
            ["__stat_updated", "__page_no", "__row_order"],
            na_position="first",
        )
        selected_index = ordered.index[-1]
        status_conflict = group["stat"].nunique(dropna=True) > 1
        group_rows.append(
            {
                "key": key,
                "group": group,
                "selected_index": selected_index,
                "status_conflict": status_conflict,
            }
        )

    conflict = [item for item in group_rows if item["status_conflict"]]
    same_status = [item for item in group_rows if not item["status_conflict"]]
    rng = pd.Series(range(len(same_status))).sample(
        n=min(sample_groups, len(same_status)), random_state=seed
    )
    selected_same_status = {same_status[int(i)]["key"] for i in rng.tolist()}
    included = conflict + [item for item in same_status if item["key"] in selected_same_status]

    rows = []
    for item in included:
        group = item["group"].sort_values(
            ["__stat_updated", "__page_no", "__row_order"],
            na_position="first",
        )
        for rank, (index, row) in enumerate(group.iterrows(), start=1):
            output = {
                "sample_group": "status_conflict" if item["status_conflict"] else "same_status_duplicate",
                "selection": "selected" if index == item["selected_index"] else "removed",
                "selection_rank": rank,
                "selection_rule": "latest statUpdDt, then pageNo, then raw row order",
                "snapshotId": row.get("snapshotId"),
                "statId": row.get("statId"),
                "chgerId": row.get("chgerId"),
                "stat": row.get("stat"),
                "statUpdDt": row.get("statUpdDt"),
                "fetchedAt": row.get("fetchedAt"),
                "pageNo": row.get("pageNo"),
                "source_file": row.get("source_file"),
                "raw_row_order": int(row["__row_order"]),
            }
            rows.append(output)

    sample = pd.DataFrame(rows)
    summary = {
        "sampled_at_kst": pd.Timestamp.now(tz=KST).isoformat(timespec="seconds"),
        "raw_rows": int(len(data)),
        "raw_duplicate_groups": int(len(group_rows)),
        "raw_duplicate_extra_rows": int(duplicate.duplicated(KEYS).sum()),
        "status_conflict_groups": int(len(conflict)),
        "same_status_groups_sampled": int(len(selected_same_status)),
        "sample_rows": int(len(sample)),
        "selected_rows": int((sample["selection"] == "selected").sum()) if len(sample) else 0,
        "removed_rows": int((sample["selection"] == "removed").sum()) if len(sample) else 0,
        "selection_rule": "latest statUpdDt, then pageNo, then raw row order",
    }
    return sample, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-groups", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    data = load_raw()
    sample, summary = build_sample(data, args.sample_groups, args.seed)
    out = args.output_dir if args.output_dir.is_absolute() else REPO / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "dedupe_selection_sample_20260729.csv"
    json_path = out / "dedupe_selection_sample_20260729_summary.json"
    sample.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {csv_path.relative_to(REPO)}")
    print(f"OUT {json_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

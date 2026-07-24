"""Run mock pipeline end-to-end (DATA_PART_WORK_GUIDE §4.3–4.6)."""
from __future__ import annotations

import json
from pathlib import Path

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()

from common.mock_loader import load_charger_history
from features.feature_builder import add_station_features
from features.gap_safe_panel import build_gap_safe_panel
from features.history_validate import save_quality_report, validate_history

OUT_DIR = REPO / "docs" / "data" / "quality"


def main() -> int:
    history = load_charger_history()
    report = validate_history(history)
    save_quality_report(report, OUT_DIR / "mock_history_report.json")

    panel = build_gap_safe_panel(history, max_gap_minutes=25)
    features = add_station_features(panel)

    panel_path = OUT_DIR / "mock_panel_sample.csv"
    feat_path = OUT_DIR / "mock_station_features_sample.csv"
    panel.head(50).to_csv(panel_path, index=False, encoding="utf-8-sig")
    features.to_csv(feat_path, index=False, encoding="utf-8-sig")

    summary = {
        "history_rows": report["rows"],
        "panel_rows": int(len(panel)),
        "feature_rows": int(len(features)),
        "outputs": {
            "quality_json": str((OUT_DIR / "mock_history_report.json").relative_to(REPO)),
            "panel_sample": str(panel_path.relative_to(REPO)),
            "features_sample": str(feat_path.relative_to(REPO)),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

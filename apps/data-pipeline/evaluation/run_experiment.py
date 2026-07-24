"""팀 실험 보고용 — 추출 CSV 가공 실험 실행.

사용법 (git-elctronic 루트 또는 evaluation 폴더에서):
  pip install -r apps/data-pipeline/evaluation/requirements.txt
  python apps/data-pipeline/evaluation/run_experiment.py

결과:
  apps/data-pipeline/evaluation/results/experiment_YYYYMMDD_HHMMSS.json
  apps/data-pipeline/evaluation/results/experiment_YYYYMMDD_HHMMSS.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from csv_loader import DEFAULT_EXTRACTED_DIR  # noqa: E402
from experiment import run_experiment  # noqa: E402
from report import save_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="EV SafeCharge CSV 가공 실험")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_EXTRACTED_DIR,
        help="추출 CSV 디렉터리 (기본: docs/data/extracted)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EVAL_DIR / "results",
        help="실험 결과 저장 디렉터리",
    )
    args = parser.parse_args()

    try:
        result = run_experiment(extracted_dir=args.data_dir)
        json_path, md_path = save_report(result, args.output_dir)
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    proc = result["processing_results"]
    print(f"[OK] experiment_id={result['experiment_id']}")
    print(f"     stations={proc['stations_after_cleansing']} chargers={proc['chargers_after_cleansing']}")
    print(f"     JSON: {json_path}")
    print(f"     MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

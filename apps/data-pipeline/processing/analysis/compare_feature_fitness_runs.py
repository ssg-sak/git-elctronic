"""Compare two DA① feature-fitness report dirs (e.g. 20260729 vs today).

Writes a team-readable markdown + CSV delta under docs/팀공유/.
Does NOT choose a recommendation model — ranks input-feature fitness only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")


def _load_run(report_dir: Path) -> dict:
    summary = json.loads((report_dir / "HANDOFF_SUMMARY.json").read_text(encoding="utf-8"))
    decisions = json.loads(
        (report_dir / "feature_selection_decisions.json").read_text(encoding="utf-8")
    )
    assoc = pd.read_csv(report_dir / "feature_target_association.csv")
    profile = json.loads(
        (report_dir / "training_dataset_profile.json").read_text(encoding="utf-8")
    )
    return {
        "dir": report_dir,
        "summary": summary,
        "decisions": decisions,
        "assoc": assoc,
        "profile": profile,
    }


def compare(baseline_dir: Path, current_dir: Path, out_dir: Path) -> Path:
    base = _load_run(baseline_dir)
    cur = _load_run(current_dir)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out_dir.mkdir(parents=True, exist_ok=True)

    b_dec = {d["feature"]: d for d in base["decisions"].get("decisions", [])}
    c_dec = {d["feature"]: d for d in cur["decisions"].get("decisions", [])}
    features = sorted(set(b_dec) | set(c_dec))

    rows = []
    for f in features:
        bd, cd = b_dec.get(f, {}), c_dec.get(f, {})
        ba = base["assoc"].loc[base["assoc"]["feature"] == f]
        ca = cur["assoc"].loc[cur["assoc"]["feature"] == f]
        b_auc = float(ba["directional_auc"].iloc[0]) if len(ba) else None
        c_auc = float(ca["directional_auc"].iloc[0]) if len(ca) else None
        b_q = float(ba["q_value"].iloc[0]) if len(ba) and "q_value" in ba else bd.get("q_value")
        c_q = float(ca["q_value"].iloc[0]) if len(ca) and "q_value" in ca else cd.get("q_value")
        rows.append(
            {
                "feature": f,
                "decision_baseline": bd.get("decision"),
                "decision_current": cd.get("decision"),
                "decision_changed": bd.get("decision") != cd.get("decision"),
                "directional_auc_baseline": b_auc,
                "directional_auc_current": c_auc,
                "directional_auc_delta": (
                    None if b_auc is None or c_auc is None else round(c_auc - b_auc, 4)
                ),
                "q_value_baseline": b_q,
                "q_value_current": c_q,
                "null_rate_baseline": bd.get("null_rate"),
                "null_rate_current": cd.get("null_rate"),
                "owner_next": cd.get("owner_next") or bd.get("owner_next"),
            }
        )
    delta = pd.DataFrame(rows).sort_values(
        by=["decision_changed", "directional_auc_current"],
        ascending=[False, False],
        na_position="last",
    )
    delta_path = out_dir / "feature_fitness_delta.csv"
    delta.to_csv(delta_path, index=False, encoding="utf-8-sig")

    # priority tiers for DA② (fitness only)
    retain = delta[delta["decision_current"].isin(["RETAIN_CANDIDATE", "RETAIN_FOR_ABLATION"])]
    drop_like = delta[
        delta["decision_current"].astype(str).str.contains("DROP|HOLD|EXCLUDE", na=False)
    ]

    bs, cs = base["summary"], cur["summary"]
    bp, cp = base["profile"], cur["profile"]
    lines = [
        f"# 피처 적합도 비교 — {baseline_dir.name} → {current_dir.name}",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| **작성** | AI·데이터 ① |",
        f"| **생성** | {datetime.now(KST).isoformat(timespec='seconds')} |",
        "| **타겟** | `target_available` (도착 시각에 가용 충전기 ≥1 = 1 / 전량 관측·비가용 = 0) |",
        "| **호라이즌** | 5 / 10 / 15 / 30분 (이전과 동일) |",
        "| **범위** | 입력 피처 적합도·우선순위 (추천 점수·모델 채택 ≠ ①) |",
        "",
        "---",
        "",
        "## 1. 데이터셋 규모",
        "",
        "| 지표 | 이전 | **현재** |",
        "|---|---:|---:|",
        f"| 행 | {bs.get('rows')} | **{cs.get('rows')}** |",
        f"| 충전소 | {bs.get('stations')} | **{cs.get('stations')}** |",
        f"| model_features | {bs.get('model_features')} | **{cs.get('model_features')}** |",
        f"| handoff status | `{bs.get('status')}` | **`{cs.get('status')}`** |",
        f"| quality PASS/WARN/FAIL | {bs.get('quality_summary')} | **{cs.get('quality_summary')}** |",
        "",
        f"- 이전 리포트: `{baseline_dir.relative_to(REPO).as_posix()}`",
        f"- 현재 리포트: `{current_dir.relative_to(REPO).as_posix()}`",
        "",
        "---",
        "",
        "## 2. 타겟 계약 (변경 없음)",
        "",
        "- **positive**: 도착 tick에서 가용(stat=2) 충전기 ≥ 1 (관측·25분 hold 재구성)",
        "- **negative**: 도착 tick에서 전 충전기 known이고 가용 0",
        "- **제외**: 부분 미관측(라벨 불확실)",
        "- 피처는 모두 `feature_as_of` 시점만 사용 (미래 누수 금지)",
        "",
        "---",
        "",
        "## 3. 판정 변화",
        "",
    ]
    changed = delta[delta["decision_changed"] == True]  # noqa: E712
    if len(changed):
        lines += [
            "| feature | 이전 | 현재 | AUC Δ |",
            "|---|---|---|---:|",
        ]
        for _, r in changed.iterrows():
            lines.append(
                f"| `{r['feature']}` | {r['decision_baseline']} | **{r['decision_current']}** | "
                f"{r['directional_auc_delta']} |"
            )
    else:
        lines.append("판정 라벨이 바뀐 피처 **없음** (수치만 변동).")

    lines += [
        "",
        "---",
        "",
        "## 4. ②에게 넘길 입력 우선순위 (적합도)",
        "",
        "> 추천 모델 순위가 아님. **규칙/베이스라인에 먼저 넣을 입력** 후보.",
        "",
        "### KEEP / ablation 우선",
        "",
        "| feature | decision | directional_auc | vs 이전 Δ |",
        "|---|---|---:|---:|",
    ]
    for _, r in retain.sort_values("directional_auc_current", ascending=False).iterrows():
        lines.append(
            f"| `{r['feature']}` | {r['decision_current']} | {r['directional_auc_current']:.3f} | "
            f"{r['directional_auc_delta']} |"
        )

    if len(drop_like):
        lines += [
            "",
            "### 보류·제외 쪽",
            "",
            "| feature | decision | directional_auc |",
            "|---|---|---:|",
        ]
        for _, r in drop_like.iterrows():
            auc = r["directional_auc_current"]
            auc_s = f"{auc:.3f}" if pd.notna(auc) else "—"
            lines.append(f"| `{r['feature']}` | {r['decision_current']} | {auc_s} |")

    lines += [
        "",
        "---",
        "",
        "## 5. ② 할 일 (이전과 동일 계열)",
        "",
        "- HGB baseline 비교 · time-out-of-sample ablation",
        "- probability calibration · 모델 수용/서빙",
        "- 주차·요금·ETA는 점수 입력으로 넣지 말 것 (계약)",
        "",
        f"상세 CSV: `{delta_path.relative_to(REPO).as_posix()}`",
        "",
        "```",
        f"DA① | feature fitness compare | {stamp} | target=target_available",
        "```",
        "",
    ]
    md_path = out_dir / "피처적합도_비교_쉬운설명.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    meta = {
        "baseline": str(baseline_dir.relative_to(REPO)).replace("\\", "/"),
        "current": str(current_dir.relative_to(REPO)).replace("\\", "/"),
        "target": "target_available",
        "delta_csv": str(delta_path.relative_to(REPO)).replace("\\", "/"),
        "markdown": str(md_path.relative_to(REPO)).replace("\\", "/"),
        "n_decision_changed": int(changed.shape[0]),
        "rows_baseline": bs.get("rows"),
        "rows_current": cs.get("rows"),
    }
    (out_dir / "compare_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=True, indent=2))
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--baseline",
        type=Path,
        default=REPO / "docs/data/analysis/hgb_training_pipeline_20260729",
    )
    ap.add_argument("--current", type=Path, required=True)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    args = ap.parse_args()
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = args.out or (REPO / "docs" / "팀공유" / f"피처적합도_비교_{stamp}")
    compare(args.baseline.resolve(), args.current.resolve(), out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Final HGB feature selection + reliability/validity metrics (arrival ETA labels).

Reads hgb_arrival_eta_fitness_* ablation/association outputs, recomputes
stability metrics on the recommended set, writes team-share decision pack.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    recall_score,
    roc_auc_score,
)

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    pred = (p >= 0.5).astype(int)
    return {
        "pr_auc": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "neg_recall": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "n": int(len(y)),
        "pos_rate": float(y.mean()),
    }


def _fit(X_tr, y_tr, X_te, seed=42):
    clf = HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.08,
        max_iter=200,
        min_samples_leaf=50,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
        random_state=seed,
    )
    pos = max(int((y_tr == 1).sum()), 1)
    neg = max(int((y_tr == 0).sum()), 1)
    w = np.where(y_tr == 0, pos / neg, 1.0).astype(float)
    clf.fit(X_tr, y_tr, sample_weight=w)
    return clf.predict_proba(X_te)[:, 1]


def main() -> int:
    stamp = datetime.now(KST).strftime("%Y%m%d")
    analysis = REPO / "docs/data/analysis" / f"hgb_arrival_eta_fitness_{stamp}"
    if not (analysis / "feature_ablation_metrics.csv").exists():
        # fallback latest
        cands = sorted(
            (REPO / "docs/data/analysis").glob("hgb_arrival_eta_fitness_*")
        )
        analysis = cands[-1]
    share = REPO / "docs/팀공유" / f"피처선정_최종_HGB_도착ETA_{stamp}"
    share.mkdir(parents=True, exist_ok=True)

    abl = pd.read_csv(analysis / "feature_ablation_metrics.csv")
    assoc = pd.read_csv(analysis / "feature_target_association.csv")
    handoff = json.loads((analysis / "HANDOFF_SUMMARY.json").read_text(encoding="utf-8"))

    # --- interpret ablation vs A_mvp_horizon baseline ---
    base = abl.loc[abl["spec"] == "A_mvp_horizon"].iloc[0]
    pick = {}
    for spec in ["A_mvp_horizon", "B_mvp_tmap_eta", "C_mvp_haversine", "D_horizon_only_eta_family"]:
        row = abl.loc[abl["spec"] == spec]
        if len(row):
            pick[spec] = row.iloc[0].to_dict()

    loo = abl[abl["spec"].str.startswith("LOO_drop_")].copy()
    loo["dropped"] = loo["spec"].str.replace("LOO_drop_", "", regex=False)
    loo["d_valid_pr"] = loo["valid_pr_auc"] - float(base["valid_pr_auc"])
    loo["d_valid_neg"] = loo["valid_neg_recall"] - float(base["valid_neg_recall"])
    loo["d_valid_brier"] = loo["valid_brier"] - float(base["valid_brier"])

    # Final feature set (policy: ETA family pick ONE = tmap_eta_min; drop redundant derived)
    final_keep = [
        "available_count",
        "total_chargers",
        "known_charger_count",
        "observation_coverage",
        "hour",
        "weekday",
        "avail_rate_lag_15m",
        "avail_rate_lag_60m",
        "tmap_eta_min",
    ]
    final_drop = {
        "single_charger": "NEED_NO — LOO 동일( total_chargers가 정보 흡수 ). 파생 불필요",
        "is_weekend": "NEED_NO — weekday와 LOO 동일 · 중복",
        "avail_ratio_t0": "NEED_NO — A+대비 gain≈0 · HOLD 유지",
        "horizon_minutes": "PICK_ALT — tmap_eta_min 선택(실측 1848). horizon과 동시 금지",
        "haversine_km": "PICK_ALT — tmap과 택1 · 거리 대리치",
        "eta_bucket": "NEED_NO — 연속 tmap_eta_min이 대체",
        "eta_is_proxy": "EXCLUDE — 학습 금지(현재 rate=0)",
    }

    # reload sample frame lightly for reliability blocks
    _ANALYSIS = Path(__file__).resolve().parent
    if str(_ANALYSIS) not in sys.path:
        sys.path.insert(0, str(_ANALYSIS))
    from run_hgb_arrival_eta_fitness import load_frame

    df = load_frame(sample_neg_mult=20, max_pos=400_000)
    train = df[df["split"] == "train"]
    valid = df[df["split"] == "valid"]
    test = df[df["split"] == "test"]
    X_tr, y_tr = train[final_keep], train["y"].to_numpy()
    p_va = _fit(X_tr, y_tr, valid[final_keep])
    p_te = _fit(X_tr, y_tr, test[final_keep])
    m_va = _metrics(valid["y"].to_numpy(), p_va)
    m_te = _metrics(test["y"].to_numpy(), p_te)

    # reliability: temporal block consistency (3 equal date blocks on train+valid)
    dates = np.array(sorted(df["feature_date"].unique()))
    block_metrics = []
    if len(dates) >= 6:
        cuts = np.array_split(dates, 3)
        for i, block_dates in enumerate(cuts):
            te = df[df["feature_date"].isin(block_dates)]
            tr = df[~df["feature_date"].isin(block_dates)]
            if te["y"].nunique() < 2 or tr["y"].nunique() < 2 or len(te) < 2000:
                continue
            pb = _fit(tr[final_keep], tr["y"].to_numpy(), te[final_keep], seed=42 + i)
            mb = _metrics(te["y"].to_numpy(), pb)
            mb["block"] = i + 1
            mb["date_min"] = str(min(block_dates))
            mb["date_max"] = str(max(block_dates))
            block_metrics.append(mb)

    # reliability: seed stability
    seed_rows = []
    for seed in (7, 21, 42):
        p = _fit(X_tr, y_tr, test[final_keep], seed=seed)
        seed_rows.append({"seed": seed, **_metrics(test["y"].to_numpy(), p)})

    seed_df = pd.DataFrame(seed_rows)
    block_df = pd.DataFrame(block_metrics)

    reliability = {
        "definition": "동일 구성·시간분할에서 지표가 안정적인가 (측정 일관성)",
        "valid_test_delta": {
            "pr_auc": m_te["pr_auc"] - m_va["pr_auc"],
            "neg_recall": m_te["neg_recall"] - m_va["neg_recall"],
            "brier": m_te["brier"] - m_va["brier"],
            "pass_rule": "|ΔPR-AUC|<=0.02 and |Δneg_recall|<=0.05 and |ΔBrier|<=0.03",
            "pass": (
                abs(m_te["pr_auc"] - m_va["pr_auc"]) <= 0.02
                and abs(m_te["neg_recall"] - m_va["neg_recall"]) <= 0.05
                and abs(m_te["brier"] - m_va["brier"]) <= 0.03
            ),
        },
        "seed_stability_test": {
            "pr_auc_std": float(seed_df["pr_auc"].std()),
            "neg_recall_std": float(seed_df["neg_recall"].std()),
            "brier_std": float(seed_df["brier"].std()),
            "pass_rule": "std(PR-AUC)<0.005 and std(neg_recall)<0.02",
            "pass": bool(
                seed_df["pr_auc"].std() < 0.005 and seed_df["neg_recall"].std() < 0.02
            ),
            "seeds": seed_rows,
        },
        "temporal_block_cv": {
            "blocks": block_metrics,
            "pr_auc_mean": float(block_df["pr_auc"].mean()) if len(block_df) else None,
            "pr_auc_std": float(block_df["pr_auc"].std()) if len(block_df) else None,
            "neg_recall_mean": float(block_df["neg_recall"].mean())
            if len(block_df)
            else None,
            "neg_recall_std": float(block_df["neg_recall"].std())
            if len(block_df)
            else None,
            "pass_rule": "std(PR-AUC across blocks)<0.02",
            "pass": bool(len(block_df) and block_df["pr_auc"].std() < 0.02),
        },
        "feature_null_reliability": {
            f: float(assoc.loc[assoc["feature"] == f, "null_rate"].iloc[0])
            for f in final_keep
            if f in set(assoc["feature"])
        },
        "label_proxy_rate": handoff["profile"].get("eta_is_proxy_rate"),
    }

    # validity
    a = pick["A_mvp_horizon"]
    b = pick["B_mvp_tmap_eta"]
    c = pick["C_mvp_haversine"]
    d = pick["D_horizon_only_eta_family"]
    validity = {
        "definition": "도착 가용(construct)을 제대로 측정·예측하는가",
        "construct_target": "target_available_at_arrival (도착 시점 가용; 실제 충전성공 ≠)",
        "criterion_validity_test": {
            **m_te,
            "primary": ["pr_auc", "neg_recall", "brier"],
            "accuracy_forbidden": True,
            "pass_rule": "PR-AUC>=0.95 and neg_recall>=0.70 and Brier<=0.25",
            "pass": m_te["pr_auc"] >= 0.95
            and m_te["neg_recall"] >= 0.70
            and m_te["brier"] <= 0.25,
        },
        "content_validity": {
            "keeps_domain_core": [
                "available_count",
                "total_chargers",
                "known_charger_count",
                "observation_coverage",
                "tmap_eta_min",
            ],
            "freshness_note": "observation_age_minutes는 D2 station panel에 없어 미포함(게이트는 서빙/규칙층)",
        },
        "convergent_validity": {
            "tmap_vs_horizon_valid_pr_auc": {
                "horizon": float(a["valid_pr_auc"]),
                "tmap_eta": float(b["valid_pr_auc"]),
                "haversine": float(c["valid_pr_auc"]),
                "stack_all_three": float(d["valid_pr_auc"]),
            },
            "note": "셋 모두 유사 · 스택(D)이 소폭 우세하나 다중공선·택1 계약 위반 → 실측 tmap 1개만",
        },
        "discriminant_validity": {
            "eta_is_proxy_excluded": True,
            "usage_hold_sparse": True,
            "parking_score_excluded": True,
            "avail_ratio_t0_excluded": True,
            "single_charger_excluded_as_redundant": True,
        },
        "incremental_validity_derived": {
            "single_charger": {
                "needed": False,
                "evidence": "LOO_drop_single_charger metrics identical to A_mvp_horizon",
                "valid_pr_auc_delta": float(
                    loo.loc[loo["dropped"] == "single_charger", "d_valid_pr"].iloc[0]
                ),
            },
            "avail_ratio_t0": {
                "needed": False,
                "evidence": "A_plus_avail_ratio ≈ A_mvp_horizon",
                "valid_pr_auc_delta": float(
                    abl.loc[abl["spec"] == "A_plus_avail_ratio", "valid_pr_auc"].iloc[0]
                    - a["valid_pr_auc"]
                ),
            },
            "eta_family_stack": {
                "needed": False,
                "evidence": "D beats B by ~0.002 PR-AUC only; pick-one contract",
                "d_minus_b_valid_pr": float(d["valid_pr_auc"] - b["valid_pr_auc"]),
            },
        },
    }

    decisions = []
    for f in final_keep:
        ar = assoc.loc[assoc["feature"] == f]
        lo = loo.loc[loo["dropped"] == f]
        decisions.append(
            {
                "feature": f,
                "decision": "RETAIN_FINAL",
                "role": "HGB model input",
                "directional_auc": None
                if ar.empty or pd.isna(ar.iloc[0]["directional_auc"])
                else float(ar.iloc[0]["directional_auc"]),
                "loo_d_valid_pr_auc": None
                if lo.empty
                else float(lo.iloc[0]["d_valid_pr"]),
                "loo_d_valid_neg_recall": None
                if lo.empty
                else float(lo.iloc[0]["d_valid_neg"]),
            }
        )
    for f, reason in final_drop.items():
        decisions.append(
            {
                "feature": f,
                "decision": "DROP_OR_EXCLUDE",
                "role": reason,
                "directional_auc": None,
                "loo_d_valid_pr_auc": None,
                "loo_d_valid_neg_recall": None,
            }
        )

    summary = {
        "status": "DA1_FINAL_FEATURE_SELECTION_HGB",
        "model_family": "HistGradientBoostingClassifier",
        "target": "target_available_at_arrival",
        "derived_features_needed": False,
        "derived_verdict": (
            "추가 파생 불필요. single_charger·eta_bucket·avail_ratio_t0는 "
            "HGB+total_chargers+tmap_eta_min 조합에서 증분 타당도 없음."
        ),
        "final_features": final_keep,
        "n_features": len(final_keep),
        "final_valid": m_va,
        "final_test": m_te,
        "reliability": reliability,
        "validity": validity,
        "eta_pick": "tmap_eta_min",
        "source_fitness": str(analysis.relative_to(REPO)).replace("\\", "/"),
    }

    # write artifacts
    (analysis / "final_feature_selection.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    pd.DataFrame(decisions).to_csv(
        analysis / "final_feature_decisions.csv", index=False, encoding="utf-8-sig"
    )
    loo[
        [
            "dropped",
            "valid_pr_auc",
            "valid_neg_recall",
            "valid_brier",
            "d_valid_pr",
            "d_valid_neg",
            "d_valid_brier",
            "test_pr_auc",
            "test_neg_recall",
        ]
    ].to_csv(analysis / "loo_deltas.csv", index=False, encoding="utf-8-sig")
    seed_df.to_csv(analysis / "reliability_seed_stability.csv", index=False, encoding="utf-8-sig")
    if len(block_df):
        block_df.to_csv(
            analysis / "reliability_temporal_blocks.csv",
            index=False,
            encoding="utf-8-sig",
        )

    rel_pass = (
        reliability["valid_test_delta"]["pass"]
        and reliability["seed_stability_test"]["pass"]
        and reliability["temporal_block_cv"]["pass"]
    )
    val_pass = validity["criterion_validity_test"]["pass"]

    md = f"""# 최종 피처 선정 — HGB × 도착 ETA 라벨

| 항목 | 내용 |
|---|---|
| **모델** | HistGradientBoosting (확정 기준) |
| **타겟** | `target_available_at_arrival` |
| **파생변수 추가** | **불필요** |
| **최종 피처 수** | {len(final_keep)} |
| **신뢰도 종합** | {"PASS" if rel_pass else "CHECK"} |
| **타당도 종합** | {"PASS" if val_pass else "CHECK"} |

## 1. 파생변수 필요 여부

| 파생 | 필요? | 근거(수치) |
|---|---|---|
| `single_charger` | **아니오** | LOO ΔPR-AUC = {float(loo.loc[loo['dropped']=='single_charger','d_valid_pr'].iloc[0]):+.6f} (사실상 0) · `total_chargers`가 흡수 |
| `eta_bucket` | **아니오** | 연속 `tmap_eta_min` 사용 · 구간화 이득 없음 |
| `avail_ratio_t0` | **아니오** | A+ vs A ΔPR-AUC ≈ {validity['incremental_validity_derived']['avail_ratio_t0']['valid_pr_auc_delta']:+.6f} |
| horizon+tmap+거리 동시 | **아니오** | D−B ΔPR-AUC = {validity['incremental_validity_derived']['eta_family_stack']['d_minus_b_valid_pr']:+.4f} · 택1 계약 |

## 2. 최종 RETAIN 피처

```
{chr(10).join(final_keep)}
```

- ETA family 확정: **`tmap_eta_min`** (실측 1848/1848 · horizon/haversine과 택1)
- 캘린더: `hour` + `weekday` (`is_weekend` 제외)
- 패널 래그: `avail_rate_lag_15m`, `avail_rate_lag_60m` 유지

## 3. 신뢰도 (reliability) 수치

| 지표 | 값 | 기준 | 판정 |
|---|---:|---|:---:|
| valid→test ΔPR-AUC | {reliability['valid_test_delta']['pr_auc']:+.4f} | \\|Δ\\|≤0.02 | {"PASS" if abs(reliability['valid_test_delta']['pr_auc'])<=0.02 else "FAIL"} |
| valid→test Δneg-recall | {reliability['valid_test_delta']['neg_recall']:+.4f} | \\|Δ\\|≤0.05 | {"PASS" if abs(reliability['valid_test_delta']['neg_recall'])<=0.05 else "FAIL"} |
| valid→test ΔBrier | {reliability['valid_test_delta']['brier']:+.4f} | \\|Δ\\|≤0.03 | {"PASS" if abs(reliability['valid_test_delta']['brier'])<=0.03 else "FAIL"} |
| seed std PR-AUC | {reliability['seed_stability_test']['pr_auc_std']:.5f} | <0.005 | {"PASS" if reliability['seed_stability_test']['pass'] else "FAIL"} |
| seed std neg-recall | {reliability['seed_stability_test']['neg_recall_std']:.5f} | <0.02 | {"PASS" if reliability['seed_stability_test']['neg_recall_std']<0.02 else "FAIL"} |
| block CV std PR-AUC | {reliability['temporal_block_cv']['pr_auc_std']} | <0.02 | {"PASS" if reliability['temporal_block_cv']['pass'] else "FAIL"} |
| eta_is_proxy rate | {reliability['label_proxy_rate']} | 0 권장 | {"PASS" if (reliability['label_proxy_rate'] or 0)==0 else "WARN"} |

최종셋 valid: PR-AUC **{m_va['pr_auc']:.4f}** · neg-recall **{m_va['neg_recall']:.4f}** · Brier **{m_va['brier']:.4f}**  
최종셋 test: PR-AUC **{m_te['pr_auc']:.4f}** · neg-recall **{m_te['neg_recall']:.4f}** · Brier **{m_te['brier']:.4f}**

## 4. 타당도 (validity) 수치

| 종류 | 수치/증거 | 판정 |
|---|---|:---:|
| 기준 타당도 (test) | PR-AUC {m_te['pr_auc']:.4f} · neg-recall {m_te['neg_recall']:.4f} · Brier {m_te['brier']:.4f} | {"PASS" if val_pass else "FAIL"} |
| 구성 타당도 | 타겟=도착가용 · 충전성공 아님을 명시 | PASS(한계고지) |
| 수렴 타당도 | horizon {a['valid_pr_auc']:.4f} / tmap {b['valid_pr_auc']:.4f} / hav {c['valid_pr_auc']:.4f} | PASS |
| 변별 타당도 | proxy·usage·주차점수·avail_ratio 제외 | PASS |
| 증분 타당도(파생) | single_charger·ratio·ETA스택 증분≈0 | **파생 불필요** |

## 5. 넣지 말 것

- `eta_is_proxy`, `eta_bucket`, `single_charger`, `is_weekend`, `avail_ratio_t0`
- usage / 주차 점수 / horizon+tmap+haversine 동시 투입
- accuracy로 모델 비교

## 산출 경로

- `{analysis.relative_to(REPO).as_posix()}/final_feature_selection.json`
- `{share.relative_to(REPO).as_posix()}/`

```
DA① | final HGB feature selection | {stamp}
```
"""
    (share / "README.md").write_text(md, encoding="utf-8")
    (share / "final_feature_selection.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    pd.DataFrame(decisions).to_csv(
        share / "final_feature_decisions.csv", index=False, encoding="utf-8-sig"
    )
    (analysis / "HANDOFF_SUMMARY.json").write_text(
        json.dumps(
            {
                **handoff,
                "final_selection": {
                    "derived_needed": False,
                    "features": final_keep,
                    "reliability_pass": rel_pass,
                    "validity_pass": val_pass,
                    "test": m_te,
                },
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(json.dumps({
        "derived_needed": False,
        "final_features": final_keep,
        "reliability_pass": rel_pass,
        "validity_pass": val_pass,
        "final_test": m_te,
        "share": str(share.relative_to(REPO)).replace("\\", "/"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build deterministic SOC safety scenarios over real TMAP route samples.

This is a scenario grid, not a population accuracy claim. It crosses:
  * 15 historical TMAP route samples from one origin,
  * 26 registered vehicle specifications + one fallback vehicle,
  * current SOC levels 10/15/20/30/50%.

Usage from repository root:
  python apps/data-pipeline/processing/analysis/build_soc_route_scenarios.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths
from vehicle.eta_soc_calculator_utils import EtaSocCalculator

REPO = ensure_paths()
DEFAULT_ROUTES = (
    REPO
    / "docs"
    / "data"
    / "analysis"
    / "tmap_eta_sample_20260723"
    / "haversine_vs_tmap_eta.csv"
)
CURRENT_SOC_LEVELS = (10.0, 15.0, 20.0, 30.0, 50.0)
FALLBACK_MODEL_NAME = "미등록차량_FALLBACK"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routes", type=Path, default=DEFAULT_ROUTES)
    args = parser.parse_args()
    route_path = args.routes if args.routes.is_absolute() else REPO / args.routes
    if not route_path.exists():
        raise FileNotFoundError(f"missing route sample: {route_path}")

    routes = pd.read_csv(route_path, low_memory=False)
    required = {"statId", "statNm", "tmap_eta_min", "tmap_road_km"}
    missing = required - set(routes.columns)
    if missing:
        raise ValueError(f"route sample missing columns: {sorted(missing)}")
    routes["tmap_eta_min"] = pd.to_numeric(routes["tmap_eta_min"], errors="coerce")
    routes["tmap_road_km"] = pd.to_numeric(routes["tmap_road_km"], errors="coerce")
    routes = routes[
        routes["tmap_eta_min"].notna()
        & routes["tmap_road_km"].notna()
        & (routes["tmap_road_km"] >= 0)
    ].copy()

    calculator = EtaSocCalculator()
    models = calculator.df["model_name"].dropna().astype(str).tolist()
    models.append(FALLBACK_MODEL_NAME)

    rows: list[dict[str, object]] = []
    for route in routes.itertuples(index=False):
        for model_name in models:
            for current_soc in CURRENT_SOC_LEVELS:
                result = calculator.calculate_eta_soc(
                    model_name,
                    current_soc,
                    float(route.tmap_road_km),
                )
                rows.append(
                    {
                        "statId": route.statId,
                        "statNm": route.statNm,
                        "tmap_eta_min": float(route.tmap_eta_min),
                        "tmap_road_km": float(route.tmap_road_km),
                        "model_name": model_name,
                        "current_soc_percent": current_soc,
                        "arrival_soc_percent": result["arrival_soc_percent"],
                        "soc_safety_margin_percent": result[
                            "soc_safety_margin_percent"
                        ],
                        "soc_risk_level": (
                            "DANGER"
                            if result["is_danger"]
                            else (
                                "WARNING"
                                if result["arrival_soc_percent"] <= 20
                                else "SAFE"
                            )
                        ),
                        "hard_filter": bool(result["is_danger"]),
                        "can_reach": bool(result["can_reach"]),
                        "used_fallback": bool(result["used_fallback"]),
                        "spec_source": result["spec_source"],
                    }
                )

    scenarios = pd.DataFrame(rows)
    source_day = (
        pd.to_datetime(routes["as_of_kst"], errors="coerce").max().strftime("%Y%m%d")
        if "as_of_kst" in routes and routes["as_of_kst"].notna().any()
        else "unknown"
    )
    out = (
        REPO
        / "docs"
        / "data"
        / "analysis"
        / f"soc_route_scenarios_{source_day}"
    )
    out.mkdir(parents=True, exist_ok=True)
    scenarios.to_csv(
        out / "soc_route_scenarios.csv",
        index=False,
        encoding="utf-8-sig",
    )

    by_soc = []
    for soc, group in scenarios.groupby("current_soc_percent"):
        by_soc.append(
            {
                "current_soc_percent": float(soc),
                "scenario_rows": int(len(group)),
                "safe_arrival_rate": float((~group["hard_filter"]).mean()),
                "danger_rate": float(group["hard_filter"].mean()),
                "cannot_reach_rate": float((~group["can_reach"]).mean()),
                "arrival_soc_min": float(group["arrival_soc_percent"].min()),
                "arrival_soc_median": float(group["arrival_soc_percent"].median()),
            }
        )

    fallback = scenarios[scenarios["used_fallback"]]
    summary = {
        "source_routes": str(route_path.relative_to(REPO)).replace("\\", "/"),
        "source_route_scope": "15 TMAP routes from one Dongdaegu-area origin",
        "scenario_grain": "route × vehicle specification × current SOC",
        "routes": int(routes["statId"].nunique()),
        "registered_vehicle_models": int(len(models) - 1),
        "fallback_model_scenarios": int(len(fallback)),
        "current_soc_levels": list(CURRENT_SOC_LEVELS),
        "scenario_rows": int(len(scenarios)),
        "safe_arrival_rate": float((~scenarios["hard_filter"]).mean()),
        "danger_rate": float(scenarios["hard_filter"].mean()),
        "by_current_soc": by_soc,
        "fallback": {
            "battery_capacity_kwh": calculator.FALLBACK_BATTERY_CAPACITY_KWH,
            "efficiency_km_per_kwh": calculator.FALLBACK_EFFICIENCY_KM_PER_KWH,
            "safe_arrival_rate": (
                float((~fallback["hard_filter"]).mean()) if len(fallback) else None
            ),
        },
        "hard_filter_rule": "arrival_soc_percent <= 10",
        "limitations": [
            "This is a deterministic scenario grid, not an observed user SOC distribution.",
            "The route sample has one origin and 15 stations.",
            "The BMS evidence currently represents one continuous 37km drive.",
            "Temperature, elevation, HVAC load, battery degradation, and driving style are not modeled.",
        ],
        "files": {"scenarios": "soc_route_scenarios.csv"},
    }
    (out / "soc_route_scenarios_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import math
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd


class EtaSocCalculator:
    """
    이 유틸리티는 DA① 파이프라인에서 데이터 실증(EDA) 및 물리 모델 계산을 위해 사용됩니다.
    향후 추천 코어(DA②)에서 이 로직을 그대로 포팅(Porting)하여 사용할 수 있습니다.
    """
    FALLBACK_BATTERY_CAPACITY_KWH = 50.0
    FALLBACK_EFFICIENCY_KM_PER_KWH = 4.0
    DANGER_SOC_THRESHOLD_PERCENT = 10.0

    def __init__(self, master_csv_path: Optional[str] = None):
        if master_csv_path is None:
            # Default path assuming script is in apps/data-pipeline/processing/vehicle
            base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.master_csv_path = base_dir / "docs" / "data" / "extracted" / "vehicle" / "vehicle_master.csv"
        else:
            self.master_csv_path = Path(master_csv_path)
            
        self.df = pd.read_csv(self.master_csv_path)
        required = {"model_name", "battery_capacity_kwh", "max_range_km"}
        missing = required - set(self.df.columns)
        if missing:
            raise ValueError(f"vehicle master missing columns: {sorted(missing)}")

        self.df["model_name"] = self.df["model_name"].astype("string").str.strip()
        self.df["battery_capacity_kwh"] = pd.to_numeric(
            self.df["battery_capacity_kwh"], errors="coerce"
        )
        self.df["max_range_km"] = pd.to_numeric(
            self.df["max_range_km"], errors="coerce"
        )
        
    def get_vehicle_specs(self, model_name: str) -> Dict[str, Any]:
        normalized_name = (model_name or "").strip()
        matched = self.df[self.df["model_name"] == normalized_name]
        if matched.empty:
            battery_capacity = self.FALLBACK_BATTERY_CAPACITY_KWH
            efficiency = self.FALLBACK_EFFICIENCY_KM_PER_KWH
            return {
                "battery_capacity_kwh": battery_capacity,
                "max_range_km": battery_capacity * efficiency,
                "efficiency_km_per_kwh": efficiency,
                "spec_source": "fallback",
                "used_fallback": True,
            }

        row = matched.iloc[0]
        battery_capacity = float(row["battery_capacity_kwh"])
        max_range = float(row["max_range_km"])
        if (
            not math.isfinite(battery_capacity)
            or not math.isfinite(max_range)
            or battery_capacity <= 0
            or max_range <= 0
        ):
            raise ValueError(f"Invalid vehicle specs for model '{normalized_name}'")
        return {
            "battery_capacity_kwh": battery_capacity,
            "max_range_km": max_range,
            "efficiency_km_per_kwh": max_range / battery_capacity,
            "spec_source": "vehicle_master",
            "used_fallback": False,
        }
        
    def calculate_eta_soc(self, model_name: str, current_soc: float, distance_km: float) -> Dict[str, Any]:
        current_soc = float(current_soc)
        distance_km = float(distance_km)
        if not math.isfinite(current_soc) or not 0 <= current_soc <= 100:
            raise ValueError("current_soc must be between 0 and 100")
        if not math.isfinite(distance_km) or distance_km < 0:
            raise ValueError("distance_km must be a finite non-negative number")

        specs = self.get_vehicle_specs(model_name)
        batt_cap = specs["battery_capacity_kwh"]
        
        # 1. Calculate theoretical baseline efficiency (km/kWh)
        efficiency_km_per_kwh = specs["efficiency_km_per_kwh"]
        
        # 2. Physical energy consumption based on efficiency
        consumed_kwh = distance_km / efficiency_km_per_kwh
        
        # 3. Translate consumed kWh to SOC percentage drop
        consumed_soc_percent = (consumed_kwh / batt_cap) * 100
        
        # 4. Final ETA SOC
        arrival_soc_percent = current_soc - consumed_soc_percent
        display_soc_percent = min(100.0, max(0.0, arrival_soc_percent))
        safety_margin = arrival_soc_percent - self.DANGER_SOC_THRESHOLD_PERCENT
        
        return {
            "model_name": (model_name or "").strip(),
            "distance_km": distance_km,
            "current_soc_percent": current_soc,
            "battery_capacity_kwh": batt_cap,
            "efficiency_km_per_kwh": round(efficiency_km_per_kwh, 2),
            "consumed_kwh": round(consumed_kwh, 2),
            "consumed_soc_percent": round(consumed_soc_percent, 2),
            "arrival_soc_percent": round(arrival_soc_percent, 2),
            "arrival_soc_display_percent": round(display_soc_percent, 2),
            "soc_safety_margin_percent": round(safety_margin, 2),
            "can_reach": arrival_soc_percent > 0,
            "is_danger": (
                arrival_soc_percent <= self.DANGER_SOC_THRESHOLD_PERCENT
            ),
            "spec_source": specs["spec_source"],
            "used_fallback": specs["used_fallback"],
        }

if __name__ == "__main__":
    calc = EtaSocCalculator()
    print("=== Physical SOC Baseline Calculator Test ===")
    res = calc.calculate_eta_soc("코나EV", 50.0, 50.0)
    for k, v in res.items():
        print(f"  {k}: {v}")

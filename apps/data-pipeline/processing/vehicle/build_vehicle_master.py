import os
import pandas as pd
from pathlib import Path

# Official correction map (Battery Capacity kWh, Max Range km, Fast Charge, Slow Charge)
CORRECTIONS = {
    "17년도 아이오닉": (28.0, 191.0, "DC차데모", "AC완속"),
    "피스": (10.4, 78.0, "지원안함", "AC완속"),
    "쏘나타 PHEV": (9.8, 44.0, "지원안함", "AC완속"),
    "코나EV": (64.0, 406.0, "DC콤보", "AC완속"),
    "18년도 아이오닉 PHEV": (8.9, 46.0, "지원안함", "AC완속"),
    "레이": (16.4, 91.0, "DC차데모", "AC완속"),
    "쏘울": (27.0, 148.0, "DC차데모", "AC완속"),  # Assuming 1st gen Soul EV based on original row
    "니로_EV": (64.0, 385.0, "DC콤보", "AC완속"),
    "SM3": (35.9, 213.0, "AC3상", "AC완속"),
    "조에": (54.5, 309.0, "DC콤보", "AC완속"),
    "스파크": (21.4, 128.0, "DC콤보", "AC완속"),
    "볼트_EV": (66.0, 414.0, "DC콤보", "AC완속"),
    "볼트_PHEV": (18.4, 89.0, "지원안함", "AC완속"),
    "i3": (37.9, 248.0, "DC콤보", "AC완속"),
    "BMW 7 PHEV": (12.0, 26.0, "지원안함", "AC완속"),
    "BMW 530e PHEV": (12.0, 39.0, "지원안함", "AC완속"),
    "BMW X3 xDRIVE30e": (12.0, 31.0, "지원안함", "AC완속"),
    "LEAF": (40.0, 231.0, "DC차데모", "AC완속"),
    "테슬라 모델 S": (100.0, 480.0, "DC콤보/테슬라", "AC완속/테슬라"),
    "GLC 350e PHEV": (8.7, 15.0, "지원안함", "AC완속"),
    "벤츠 EQC400": (80.0, 309.0, "DC콤보", "AC완속"),
    "벤츠 s560e": (13.5, 31.0, "지원안함", "AC완속"),
    "벤테이가 PHEV": (17.3, 39.0, "지원안함", "AC완속"),
    "E6": (71.8, 300.0, "AC3상", "AC완속"),
    "VOLVO S90 T8": (11.6, 34.0, "지원안함", "AC완속"),
    "포드 익스플로러(PHEV)": (13.6, 30.0, "지원안함", "AC완속"),
}

def main():
    repo_root = Path(r"C:\Users\PC\Desktop\electronic-aimodel\git-elctronic")
    input_path = Path(r"C:\Users\PC\Downloads\KEPCO_EV_models_20230718_UTF8 (1).csv")
    out_dir = repo_root / "docs" / "data" / "extracted" / "vehicle"
    os.makedirs(out_dir, exist_ok=True)
    out_csv = out_dir / "vehicle_master.csv"
    
    print(f"Loading raw KEPCO data from {input_path}")
    df = pd.read_csv(input_path)
    
    # Clean up names and prepare columns
    df = df.rename(columns={
        "제조사": "manufacturer",
        "모델명": "model_name",
        "배터리용량": "battery_capacity_kwh_original",
        "최대거리": "max_range_km_original"
    })
    
    df["battery_capacity_kwh"] = df["battery_capacity_kwh_original"]
    df["max_range_km"] = df["max_range_km_original"]
    df["fast_charge_type"] = "알수없음"
    df["slow_charge_type"] = "AC완속"
    
    corrections_applied = 0
    
    for idx, row in df.iterrows():
        model = str(row["model_name"]).strip()
        df.at[idx, "model_name"] = model
        
        if model in CORRECTIONS:
            batt, dist, fast, slow = CORRECTIONS[model]
            df.at[idx, "battery_capacity_kwh"] = batt
            df.at[idx, "max_range_km"] = dist
            df.at[idx, "fast_charge_type"] = fast
            df.at[idx, "slow_charge_type"] = slow
            corrections_applied += 1
            
    # Select final columns
    final_cols = [
        "manufacturer", "model_name", "battery_capacity_kwh", "max_range_km",
        "fast_charge_type", "slow_charge_type"
    ]
    df_final = df[final_cols]
    
    df_final.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"Applied {corrections_applied} corrections.")
    print(f"Saved vehicle_master to {out_csv}")
    print("\nSample of corrected data:")
    print(df_final.head(10).to_string())

if __name__ == "__main__":
    main()

import os
import pandas as pd
import json
from pathlib import Path

def clean_name(s):
    return str(s).replace(' ', '').replace('(', '').replace(')', '').replace('_', '').lower()

def main():
    repo_root = Path(r"C:\Users\PC\Desktop\electronic-aimodel\git-elctronic")
    history_path = repo_root / "docs" / "팀공유" / "충전이력_대구_20260724" / "daegu_me_history_all.csv"
    info_path = repo_root / "docs" / "data" / "extracted" / "charger" / "info" / "daegu_charger_info_service_latest.csv"
    
    out_dir = repo_root / "docs" / "data" / "analysis" / "me_history_hourly_profile"
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Loading ME history from {history_path}")
    hist = pd.read_csv(history_path, low_memory=False)
    
    print(f"Loading Charger info from {info_path}")
    info = pd.read_csv(info_path, low_memory=False)
    
    hist['clean_name'] = hist['충전소명'].apply(clean_name)
    
    # info might have multiple chargers per statId. We just need unique statId-statNm mapping
    info_unique = info[['statId', 'statNm']].drop_duplicates()
    info_unique['clean_name'] = info_unique['statNm'].apply(clean_name)
    
    # To handle duplicates in clean_name in info (if any), drop duplicates on clean_name keeping the first
    info_unique = info_unique.drop_duplicates(subset=['clean_name'])
    
    print("Mapping history stations to statId...")
    hist = hist.merge(info_unique[['clean_name', 'statId']], on='clean_name', how='inner')
    
    # Calculate duration
    hist['start_ts'] = pd.to_datetime(hist['start_ts'], errors='coerce')
    # Some end_ts formats are YYYYMMDDHHMMSS, try parsing
    hist['end_ts'] = pd.to_datetime(hist['충전종료일시'], format='%Y%m%d%H%M%S', errors='coerce')
    missing_end = hist['end_ts'].isna()
    hist.loc[missing_end, 'end_ts'] = pd.to_datetime(hist.loc[missing_end, '충전종료일시'], errors='coerce')
    
    hist['duration_min'] = (hist['end_ts'] - hist['start_ts']).dt.total_seconds() / 60.0
    hist['duration_min'] = hist['duration_min'].fillna(0).clip(lower=0, upper=720) # cap at 12 hours
    hist['충전량_num'] = hist['충전량_num'].fillna(0).clip(lower=0)
    
    print("Aggregating by statId, dow, hour...")
    # Using 'dow' (0=Mon, 6=Sun) and 'hour' (0-23)
    grouped = hist.groupby(['statId', 'dow', 'hour']).agg(
        session_count=('start_ts', 'size'),
        total_kwh=('충전량_num', 'sum'),
        avg_kwh=('충전량_num', 'mean'),
        total_duration_min=('duration_min', 'sum'),
        avg_duration_min=('duration_min', 'mean')
    ).reset_index()
    
    # Fill any remaining NaNs
    grouped = grouped.fillna(0)
    
    print("Calculating demand score...")
    # demand_score: Min-max scaling of total_duration_min across the dataset
    max_dur = grouped['total_duration_min'].max()
    min_dur = grouped['total_duration_min'].min()
    if max_dur > min_dur:
        grouped['demand_score'] = (grouped['total_duration_min'] - min_dur) / (max_dur - min_dur)
    else:
        grouped['demand_score'] = 0.0
        
    # Scale demand score to a more readable format, like 0-100 instead of 0-1
    grouped['demand_score'] = (grouped['demand_score'] * 100).round(2)
        
    out_csv = out_dir / "station_hourly_profile.csv"
    grouped.to_csv(out_csv, index=False)
    print(f"Saved profile to {out_csv}")
    
    # Stats
    stats = {
        "total_historical_sessions": len(hist),
        "unique_statIds_mapped": int(grouped['statId'].nunique()),
        "total_profile_rows": len(grouped),
        "max_session_count_in_an_hour": int(grouped['session_count'].max()),
        "max_demand_score": float(grouped['demand_score'].max()),
        "mean_demand_score": float(grouped['demand_score'].mean())
    }
    
    with open(out_dir / "profile_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
        
    print(json.dumps(stats, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

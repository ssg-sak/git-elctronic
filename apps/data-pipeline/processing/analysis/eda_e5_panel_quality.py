import os
import pandas as pd
import numpy as np
import json
from datetime import datetime

def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    datasets = os.path.join(root, "apps", "data-pipeline", "evaluation", "results", "datasets")
    out_dir = os.path.join(root, "apps", "data-pipeline", "evaluation", "results", "eda")
    os.makedirs(out_dir, exist_ok=True)

    parquet = os.path.join(datasets, "station_feature_panel_latest.parquet")
    csv = os.path.join(datasets, "station_feature_panel_latest.csv")
    panel_path = parquet if os.path.exists(parquet) else csv

    print(f"Loading {panel_path}...")
    if panel_path.endswith(".parquet"):
        df = pd.read_parquet(panel_path)
    else:
        df = pd.read_csv(panel_path)
    df['panel_ts'] = pd.to_datetime(df['panel_ts'])
    
    # Sort just in case
    df = df.sort_values(['statId', 'panel_ts'])
    
    # Segment stats
    # A segment is uniquely identified by (statId, segment_id)
    segments = df.groupby(['statId', 'segment_id']).agg(
        start_ts=('panel_ts', 'min'),
        end_ts=('panel_ts', 'max'),
        ticks=('panel_ts', 'count')
    ).reset_index()
    
    segments['duration_minutes'] = (segments['end_ts'] - segments['start_ts']).dt.total_seconds() / 60.0
    
    # Gap stats
    # We find gaps by looking at the time difference between the start of a segment and the end of the previous segment for the same statId
    segments = segments.sort_values(['statId', 'start_ts'])
    segments['prev_end_ts'] = segments.groupby('statId')['end_ts'].shift(1)
    segments['gap_minutes'] = (segments['start_ts'] - segments['prev_end_ts']).dt.total_seconds() / 60.0
    
    valid_gaps = segments['gap_minutes'].dropna()
    
    stats = {
        "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rows": len(df),
        "total_stations": df['statId'].nunique(),
        "total_segments": len(segments),
        "segment_duration_mean_min": float(segments['duration_minutes'].mean()),
        "segment_duration_median_min": float(segments['duration_minutes'].median()),
        "segment_duration_max_min": float(segments['duration_minutes'].max()),
        "ticks_per_segment_mean": float(segments['ticks'].mean()),
        "total_gaps_gt_25m": len(valid_gaps),
        "gap_duration_mean_min": float(valid_gaps.mean()) if len(valid_gaps) > 0 else 0.0,
        "gap_duration_median_min": float(valid_gaps.median()) if len(valid_gaps) > 0 else 0.0,
        "gap_duration_max_min": float(valid_gaps.max()) if len(valid_gaps) > 0 else 0.0,
        "panel_start": str(df['panel_ts'].min()),
        "panel_end": str(df['panel_ts'].max())
    }
    
    out_json = os.path.join(out_dir, "e5_panel_quality.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
        
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Saved stats to {out_json}")

if __name__ == "__main__":
    main()

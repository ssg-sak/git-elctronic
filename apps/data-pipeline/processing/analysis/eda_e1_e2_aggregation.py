import os
import pandas as pd
import json

def main():
    panel_path = r"apps\data-pipeline\evaluation\results\datasets\station_feature_panel_latest.csv"
    out_dir = r"apps\data-pipeline\evaluation\results\eda"
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Loading {panel_path}...")
    df = pd.read_csv(panel_path)
    df['panel_ts'] = pd.to_datetime(df['panel_ts'])
    
    # E1: Time of Day (0-23 hours)
    df['hour'] = df['panel_ts'].dt.hour
    e1_stats = df.groupby('hour')['availability_ratio_observed'].mean().reset_index()
    e1_stats.to_csv(os.path.join(out_dir, "e1_time_of_day.csv"), index=False)
    
    # E2: Day of Week (Monday to Sunday)
    df['day_of_week'] = df['panel_ts'].dt.day_name()
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    df['day_of_week'] = pd.Categorical(df['day_of_week'], categories=days_order, ordered=True)
    # observed_ticks count per day to see if we have enough data
    e2_stats = df.groupby('day_of_week').agg(
        availability_ratio_observed=('availability_ratio_observed', 'mean'),
        tick_count=('availability_ratio_observed', 'count')
    ).reset_index()
    e2_stats.to_csv(os.path.join(out_dir, "e2_day_of_week.csv"), index=False)
    
    # Save a quick JSON summary to print
    summary = {
        "E1_Peak_Hour": int(e1_stats.loc[e1_stats['availability_ratio_observed'].idxmax()]['hour']),
        "E1_Peak_Rate": float(e1_stats['availability_ratio_observed'].max()),
        "E1_Low_Hour": int(e1_stats.loc[e1_stats['availability_ratio_observed'].idxmin()]['hour']),
        "E1_Low_Rate": float(e1_stats['availability_ratio_observed'].min()),
        "E2_Day_Stats": e2_stats.set_index('day_of_week')['availability_ratio_observed'].fillna(0).to_dict(),
        "E2_Day_Ticks": e2_stats.set_index('day_of_week')['tick_count'].to_dict()
    }
    
    print(json.dumps(summary, indent=2))
    
    with open(os.path.join(out_dir, "e1_e2_summary.json"), 'w') as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()

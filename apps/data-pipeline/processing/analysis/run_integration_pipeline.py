"""Integration test for Feature Builder (DA1)."""
import pandas as pd
import glob
from pathlib import Path
import sys

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths
REPO = ensure_paths()

from features.gap_safe_panel import build_gap_safe_panel, aggregate_station_features

def load_all_status_history():
    files = glob.glob(str(REPO / "docs/data/**/daegu_charger_status_*.csv"), recursive=True)
    if not files:
        raise FileNotFoundError("No daegu_charger_status_*.csv found.")
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding='utf-8')
            dfs.append(df)
        except Exception:
            try:
                df = pd.read_csv(f, encoding='cp949')
                dfs.append(df)
            except:
                pass
    return pd.concat(dfs, ignore_index=True)

def load_charger_info_counts():
    """INFO 원본에서 충전소별 실제 충전기 대수를 가져온다."""
    info_path = REPO / "docs/data/extracted/charger/info/daegu_charger_info_flagged_latest.csv"
    if not info_path.exists():
        # fallback: 다른 info 파일 시도
        candidates = sorted(glob.glob(str(REPO / "docs/data/extracted/charger/info/daegu_charger_info_*.csv")))
        if not candidates:
            return pd.DataFrame(columns=['statId', 'info_total_chargers'])
        info_path = Path(candidates[-1])
    
    info = pd.read_csv(info_path, encoding='utf-8', low_memory=False)
    # chgerId 기준으로 충전소별 실제 충전기 대수 집계
    counts = info.groupby('statId')['chgerId'].nunique().reset_index()
    counts.columns = ['statId', 'info_total_chargers']
    print(f"   INFO 원본 충전소: {len(counts)}개, 평균 충전기: {counts['info_total_chargers'].mean():.1f}대")
    return counts

def load_spatial_counts(filepath, count_col_name):
    try:
        df = pd.read_csv(filepath, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(filepath, encoding='cp949')
    except FileNotFoundError:
        return pd.DataFrame(columns=['statId', count_col_name])
        
    if df.empty:
        return pd.DataFrame(columns=['statId', count_col_name])
        
    # Filter only matched and count per statId
    df['matched'] = df['matched'].astype(str).str.lower() == 'true'
    counts = df[df['matched'] == True].groupby('statId').size().reset_index(name=count_col_name)
    return counts

def main():
    print("1. Loading raw status history...")
    history = load_all_status_history()
    print(f"   Total rows loaded: {len(history)}")
    
    print("2. Building gap-safe panel...")
    panel = build_gap_safe_panel(history, max_gap_minutes=25)
    print(f"   Panel shape: {panel.shape}")
    
    print("3. Aggregating station features...")
    features = aggregate_station_features(panel)
    print(f"   Features shape: {features.shape}")
    
    # ============================================================
    # [BUG FIX] INFO 원본 기준 total_chargers 보정
    # gap_safe_panel의 aggregate_station_features는 스냅샷 응답에
    # 포함된 충전기만 세기 때문에, API가 변경된 충전기만 반환하면
    # total_chargers가 실제보다 훨씬 적게(대부분 1로) 잡힘.
    # → INFO 원본의 실제 충전기 대수로 교체하고 ratio 재계산.
    # ============================================================
    print("3-1. Correcting total_chargers from INFO master data...")
    info_counts = load_charger_info_counts()
    
    if not info_counts.empty:
        features = features.rename(columns={"stationId": "statId"})
        features = features.merge(info_counts, on='statId', how='left')
        
        # INFO에 있는 충전소는 INFO 기준으로 교체, 없으면 기존 값 유지
        has_info = features['info_total_chargers'].notna()
        before_1pct = (features['total_chargers'] == 1).sum() / len(features) * 100
        
        features.loc[has_info, 'total_chargers'] = features.loc[has_info, 'info_total_chargers']
        features.drop(columns=['info_total_chargers'], inplace=True)
        
        # ratio 재계산 (total_chargers가 바뀌었으므로)
        tc = features['total_chargers'].clip(lower=1)
        features['available_ratio'] = features['available_count'] / tc
        features['charging_ratio'] = features['charging_count'] / tc
        features['out_of_service_ratio'] = features['out_of_service_count'] / tc
        
        after_1pct = (features['total_chargers'] == 1).sum() / len(features) * 100
        print(f"   1대짜리 비율: {before_1pct:.1f}% → {after_1pct:.1f}% (보정 완료)")
        
        features = features.rename(columns={"statId": "stationId"})
    
    print("4. Creating Target Variables (T+5m, T+10m, T+15m)...")
    features = features.sort_values(['stationId', 'panel_ts'])
    
    # 5-minute intervals assumed.
    # shift(-1) = 5m, shift(-2) = 10m, shift(-3) = 15m
    grouped = features.groupby('stationId')['available_ratio']
    
    features['target_available_ratio_5m'] = grouped.shift(-1)
    features['target_is_available_5m'] = (features['target_available_ratio_5m'] > 0).astype(float)
    
    features['target_available_ratio_10m'] = grouped.shift(-2)
    features['target_is_available_10m'] = (features['target_available_ratio_10m'] > 0).astype(float)
    
    features['target_available_ratio_15m'] = grouped.shift(-3)
    features['target_is_available_15m'] = (features['target_available_ratio_15m'] > 0).astype(float)
    
    # Drop rows where 15m target is NaN (the last few timestamps per station)
    features = features.dropna(subset=['target_available_ratio_15m'])
    
    print("5. Merging Spatial Join Features...")
    spatial_dir = REPO / "docs/data/spatial_join"
    
    # Tour
    tour = load_spatial_counts(spatial_dir / "join_city_tour_geocoded_1000m.csv", "tourist_spots_1km")
    # Traffic
    traffic = load_spatial_counts(spatial_dir / "join_traffic_incident_utic_1000m.csv", "traffic_incidents_1km")
    # Parking (team5 only — mock join removed)
    parking = load_spatial_counts(spatial_dir / "join_parking_team5_1000m.csv", "parking_spots_1km")

    # Merge
    master = features.rename(columns={"stationId": "statId"})
    master = master.merge(tour, on='statId', how='left').fillna({'tourist_spots_1km': 0})
    master = master.merge(traffic, on='statId', how='left').fillna({'traffic_incidents_1km': 0})
    master = master.merge(parking, on='statId', how='left').fillna({'parking_spots_1km': 0})
    
    out_dir = REPO / "docs/data/quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "master_training_dataset.csv"
    
    master.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f"\nDone! Master dataset saved to: {out_path.relative_to(REPO)}")
    print(f"Total shape: {master.shape}")
    print("Columns:", list(master.columns))
    
    # 보정 후 검증 출력
    station_sizes = master.groupby('statId')['total_chargers'].first()
    dist = station_sizes.value_counts().sort_index()
    print("\n[Corrected] Charger count distribution:")
    for cnt, num in dist.head(10).items():
        print(f"  {int(cnt)}대: {num}개소 ({num/len(station_sizes)*100:.1f}%)")
    
    print("\n[WARNING] Data spans very short time period. Severe overfitting risk if used for production training.")

if __name__ == "__main__":
    main()


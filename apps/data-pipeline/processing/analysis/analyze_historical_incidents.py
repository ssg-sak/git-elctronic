import os
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import json

# Set up matplotlib for Korean font (Malgun Gothic for Windows)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0  # meters
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    delta_phi = np.radians(lat2 - lat1)
    delta_lambda = np.radians(lon2 - lon1)
    
    a = np.sin(delta_phi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2.0) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

def classify_incident(desc):
    desc = str(desc).strip()
    if '사고' in desc: return '사고'
    if '공사' in desc: return '공사'
    if '행사' in desc: return '행사'
    if '통제' in desc: return '통제'
    return '기타'

def main():
    today_str = datetime.now().strftime("%Y%m%d")
    out_dir = rf"docs\data\analysis\historical_incidents_{today_str}"
    os.makedirs(out_dir, exist_ok=True)
    
    csv_path = r"C:\Users\PC\Downloads\대구광역시_교통 돌발상황정보_20250430 (1).csv"
    print(f"Loading {csv_path}...")
    
    try:
        df = pd.read_csv(csv_path, encoding='cp949', names=['date', 'start_time', 'end_time', 'description', 'longitude', 'latitude'], header=0)
    except Exception as e:
        df = pd.read_csv(csv_path, encoding='euc-kr', names=['date', 'start_time', 'end_time', 'description', 'longitude', 'latitude'], header=0)
        
    print(f"Loaded {len(df)} rows.")
    
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df = df.dropna(subset=['longitude', 'latitude'])
    print(f"Valid coordinates: {len(df)} rows.")
    
    df['type'] = df['description'].apply(classify_incident)
    
    # Save standardized historical incidents
    std_out = os.path.join(out_dir, "historical_incidents_standardized.csv")
    df.to_csv(std_out, index=False, encoding='utf-8-sig')
    
    # Analyze by type
    type_counts = df['type'].value_counts()
    plt.figure(figsize=(8,6))
    type_counts.plot(kind='bar', color='skyblue')
    plt.title("과거 돌발유형 분포 (2025)")
    plt.xlabel("유형")
    plt.ylabel("건수")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "incident_types.png"))
    plt.close()
    
    # Spatial join with station master
    d1_path = r"apps\data-pipeline\evaluation\results\datasets\station_feature_snapshot_latest.csv"
    if not os.path.exists(d1_path):
        print(f"D1 {d1_path} not found. Ensure D1 is built.")
        return
        
    d1 = pd.read_csv(d1_path)
    if 'statId' not in d1.columns or 'lat' not in d1.columns or 'lng' not in d1.columns:
        print("D1 missing required columns (statId, lat, lng).")
        return
        
    print(f"Loaded {len(d1)} stations from D1.")
    
    # We want to count how many historical incidents happened within 1km of each station
    # This is O(N*M) but N=4000, M=1200, so it's ~4.8 million distance calcs, perfectly fine in python with numpy
    
    inc_lats = df['latitude'].values
    inc_lons = df['longitude'].values
    
    exposure_counts = []
    
    for idx, row in d1.iterrows():
        slat = row['lat']
        slon = row['lng']
        if pd.isna(slat) or pd.isna(slon):
            exposure_counts.append(0)
            continue
            
        dists = haversine(slat, slon, inc_lats, inc_lons)
        within_1km = np.sum(dists <= 1000)
        exposure_counts.append(within_1km)
        
    exposure_df = pd.DataFrame({
        'statId': d1['statId'],
        'historical_incident_exposure_1km': exposure_counts
    })
    
    exposure_out = os.path.join(out_dir, "historical_incident_exposure.csv")
    exposure_df.to_csv(exposure_out, index=False, encoding='utf-8-sig')
    
    # Exposure distribution plot
    plt.figure(figsize=(8,6))
    plt.hist(exposure_counts, bins=20, color='lightcoral', edgecolor='black')
    plt.title("충전소별 1km 내 과거 돌발 노출 횟수 분포")
    plt.xlabel("노출 횟수")
    plt.ylabel("충전소 수")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "exposure_distribution.png"))
    plt.close()
    
    # Save summary
    summary = {
        "source_file": csv_path,
        "total_incidents_raw": len(df) + sum(df['latitude'].isna()),
        "valid_incidents": len(df),
        "total_stations_evaluated": len(d1),
        "stations_with_exposure": int(np.sum(np.array(exposure_counts) > 0)),
        "max_exposure_count": int(np.max(exposure_counts)),
        "types": type_counts.to_dict()
    }
    
    with open(os.path.join(out_dir, "summary.json"), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    readme_content = f"""# 과거 돌발 이력 분석 ({today_str})

이 폴더는 공공데이터포털에서 다운로드한 2025년 대구 과거 교통 돌발상황정보의 분석 결과입니다.
원본 CSV: `C:/Users/PC/Downloads/대구광역시_교통 돌발상황정보_20250430 (1).csv`

- **표준화**: CP949 인코딩 해결 및 좌표 정상 건 필터링 (`historical_incidents_standardized.csv`)
- **유형 분류**: 사고, 공사, 행사, 통제, 기타로 분류 (`incident_types.png`)
- **공간 결합**: D1 충전소 목록 기준 반경 1km 이내에 발생했던 과거 돌발 횟수 집계 (`historical_incident_exposure.csv`)

> **주의**: 이 파일의 `historical_incident_exposure_1km` 값은 모델링/탐색용 보조 데이터이며, 실시간 추천의 `nearest_incident_m`를 절대 덮어쓰지 않습니다.

## 요약

```json
{json.dumps(summary, ensure_ascii=False, indent=2)}
```
"""
    with open(os.path.join(out_dir, "README.md"), 'w', encoding='utf-8') as f:
        f.write(readme_content)

    print("Historical incident analysis complete.")

if __name__ == "__main__":
    main()

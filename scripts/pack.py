import os
import shutil
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

repo = r"C:\Users\PC\Desktop\electronic-aimodel\git-elctronic"
share_folder = r"C:\Users\PC\Desktop\팀공유_피처빌더결과"
master_csv = os.path.join(repo, r"docs\data\quality\master_training_dataset.csv")

# Ensure dirs
code_dir = os.path.join(share_folder, "관련_코드_Scripts")
os.makedirs(code_dir, exist_ok=True)

# Copy related code
for f in [
    r"apps\data-pipeline\processing\analysis\run_integration_pipeline.py",
    r"apps\data-pipeline\processing\features\gap_safe_panel.py",
    r"apps\data-pipeline\processing\features\feature_builder.py",
    r"apps\data-pipeline\processing\features\status_standard.py",
]:
    src = os.path.join(repo, f)
    if os.path.exists(src):
        shutil.copy(src, code_dir)

# Copy the dataset
shutil.copy(master_csv, share_folder)

# Load data
df = pd.read_csv(master_csv, encoding='utf-8-sig')

# ========== Chart 1: 5m vs 10m vs 15m Target Distribution ==========
fig, axes = plt.subplots(1, 3, figsize=(18, 6), sharey=True)
colors = ['#4FC3F7', '#FFB74D', '#E57373']
labels = ['T+5min', 'T+10min', 'T+15min']
cols = ['target_available_ratio_5m', 'target_available_ratio_10m', 'target_available_ratio_15m']

for ax, col, color, label in zip(axes, cols, colors, labels):
    data = df[col].dropna()
    ax.hist(data, bins=30, color=color, edgecolor='black', alpha=0.85)
    ax.set_title(label, fontsize=14, fontweight='bold')
    ax.set_xlabel('Available Ratio (0.0 to 1.0)')
    ax.axvline(data.mean(), color='red', linestyle='--', linewidth=1.5, label=f'Mean={data.mean():.3f}')
    ax.legend(fontsize=10)

axes[0].set_ylabel('Frequency')
fig.suptitle('Target Variable Distribution: 5m vs 10m vs 15m', fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(share_folder, "타겟변수_5_10_15분_비교_분포.png"), dpi=200)
plt.close()

# ========== Chart 2: Feature Correlation Heatmap ==========
feat_cols = ['available_ratio', 'charging_ratio', 'out_of_service_ratio',
             'hour', 'is_weekend', 'tourist_spots_1km', 'traffic_incidents_1km',
             'parking_spots_1km', 'target_available_ratio_15m']
corr = df[feat_cols].corr()

fig, ax = plt.subplots(figsize=(10, 8))
im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
ax.set_xticks(range(len(feat_cols)))
ax.set_yticks(range(len(feat_cols)))
short_labels = ['avail_ratio', 'charge_ratio', 'oos_ratio', 'hour', 'weekend',
                'tourist_1km', 'traffic_1km', 'parking_1km', 'target_15m']
ax.set_xticklabels(short_labels, rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(short_labels, fontsize=9)

for i in range(len(feat_cols)):
    for j in range(len(feat_cols)):
        ax.text(j, i, f'{corr.iloc[i, j]:.2f}', ha='center', va='center', fontsize=8,
                color='white' if abs(corr.iloc[i, j]) > 0.5 else 'black')

plt.colorbar(im, ax=ax, label='Correlation')
ax.set_title('Feature Correlation Heatmap', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(share_folder, "피처_상관관계_히트맵.png"), dpi=200)
plt.close()

# ========== Chart 3: Hourly Available Ratio Pattern ==========
fig, ax = plt.subplots(figsize=(12, 5))
hourly = df.groupby('hour')['available_ratio'].mean()
ax.bar(hourly.index, hourly.values, color='#66BB6A', edgecolor='black', alpha=0.85)
ax.set_xlabel('Hour of Day (0~23)')
ax.set_ylabel('Mean Available Ratio')
ax.set_title('Hourly Charger Availability Pattern (Average)', fontsize=14, fontweight='bold')
ax.set_xticks(range(24))
ax.axhline(hourly.values.mean(), color='red', linestyle='--', label=f'Overall Mean={hourly.values.mean():.3f}')
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(share_folder, "시간대별_충전가능률_패턴.png"), dpi=200)
plt.close()

# ========== Auto-generate EDA Markdown Report ==========
eda_md_path = os.path.join(share_folder, "통합데이터_심층_EDA_보고서.md")
with open(eda_md_path, "w", encoding="utf-8") as f:
    f.write(f"# 📊 통합 훈련 데이터 심층 EDA (탐색적 데이터 분석) 보고서\n\n")
    f.write(f"**대상 데이터**: `master_training_dataset.csv` ({len(df):,}건)\n\n")
    
    f.write("## 1. 타겟 변수 (Target) 심층 분포 분석\n\n")
    f.write("### 연속형(Regression) 타겟 분포\n")
    f.write("| 타겟 종류 | 평균 | 0.0 비율 | 1.0 비율 |\n")
    f.write("|---|---|---|---|\n")
    for col in ['target_available_ratio_5m', 'target_available_ratio_10m', 'target_available_ratio_15m']:
        mean_val = df[col].mean()
        zero_pct = (df[col] == 0).mean() * 100
        one_pct = (df[col] == 1).mean() * 100
        f.write(f"| `{col}` | {mean_val:.4f} | {zero_pct:.1f}% | {one_pct:.1f}% |\n")
    
    f.write("\n### 이진(Binary) 타겟 클래스 불균형\n")
    f.write("| 타겟 종류 | 빈자리 있음(1) | 꽉 참(0) | 불균형 비율 |\n")
    f.write("|---|---|---|---|\n")
    for col in ['target_is_available_5m', 'target_is_available_10m', 'target_is_available_15m']:
        pos_cnt = (df[col] == 1).sum()
        neg_cnt = (df[col] == 0).sum()
        imb = pos_cnt / max(neg_cnt, 1)
        f.write(f"| `{col}` | {pos_cnt:,}건 | {neg_cnt:,}건 | {imb:.2f} : 1 |\n")
        
    f.write("\n## 2. 피처 (Features) 상관관계 (vs `target_available_ratio_15m`)\n")
    corr_series = corr['target_available_ratio_15m'].drop('target_available_ratio_15m').sort_values(ascending=False)
    f.write("| 피처명 | 상관계수(r) |\n")
    f.write("|---|---|\n")
    for feat, val in corr_series.items():
        f.write(f"| `{feat}` | {val:+.4f} |\n")
        
    f.write("\n## 3. 인프라(충전기 규모) 분포\n")
    station_sizes = df.groupby('statId')['total_chargers'].first()
    dist = station_sizes.value_counts().sort_index()
    f.write("| 규모 | 충전소 개수 | 비율 |\n")
    f.write("|---|---|---|\n")
    for cnt, num in dist.head(10).items():
        f.write(f"| {int(cnt)}대 | {num:,}개소 | {num/len(station_sizes)*100:.1f}% |\n")
    f.write(f"| **평균** | **{station_sizes.mean():.1f}대** | - |\n")

print(f"Generated EDA Markdown report at: {eda_md_path}")

# Zip
shutil.make_archive(r"C:\Users\PC\Desktop\팀공유_모델학습데이터_준비", 'zip', share_folder)
print("All done! Charts, EDA report generated and zipped.")

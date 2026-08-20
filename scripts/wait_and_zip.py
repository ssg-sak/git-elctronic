import time
import os
import shutil
import pandas as pd
import matplotlib.pyplot as plt

master_csv = r"C:\Users\PC\Desktop\electronic-aimodel\git-elctronic\docs\data\quality\master_training_dataset.csv"
share_folder = r"C:\Users\PC\Desktop\팀공유_피처빌더결과"

print("Waiting for master_training_dataset.csv to be generated...")
# Wait up to 5 minutes
for _ in range(60):
    if os.path.exists(master_csv):
        break
    time.sleep(5)

if not os.path.exists(master_csv):
    print("Timeout waiting for CSV")
    exit(1)

print("Found CSV. Waiting 5s for write to complete...")
time.sleep(5)

print("Copying to shared folder...")
shutil.copy(master_csv, share_folder)

print("Generating visualization...")
try:
    df = pd.read_csv(master_csv, encoding='utf-8-sig')
    plt.figure(figsize=(10, 6))
    plt.hist(df['target_available_ratio_15m'].dropna(), bins=20, color='skyblue', edgecolor='black')
    plt.title("Distribution of target_available_ratio_15m (15 min future availability)")
    plt.xlabel("Available Ratio (0 to 1)")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(os.path.join(share_folder, "feature_distribution_plot.png"))
    plt.close()
except Exception as e:
    print(f"Error plotting: {e}")

print("Zipping the folder...")
shutil.make_archive(r"C:\Users\PC\Desktop\팀공유_모델학습데이터_준비", 'zip', share_folder)
print("Done! Zip file created at Desktop.")

import pandas as pd
import numpy as np
import glob
import os
from sklearn.preprocessing import RobustScaler
from sklearn_extra.cluster import KMedoids
import matplotlib.pyplot as plt

# ==========================================
# 1. PATH CONFIGURATION
# ==========================================
input_folder = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/"
file_pattern = os.path.join(input_folder, "settlement_prices_*.csv")
output_path = os.path.join(input_folder, "stochastic_price_scenarios.csv")

# ==========================================
# 2. LOAD DATA
# ==========================================
files = glob.glob(file_pattern)

if not files:
    print(f"CRITICAL ERROR: No files found at {file_pattern}")
else:
    print(f"Found {len(files)} files. Loading data...")

df_list = []
for f in files:
    # TenneT files use ';' separator and '.' for decimals
    temp_df = pd.read_csv(f, sep=';', decimal='.')
    df_list.append(temp_df)

df = pd.concat(df_list, ignore_index=True)

# ==========================================
# 3. PREPROCESSING & CLEANING (0-Fill Logic)
# ==========================================
print("Preprocessing data and filling empty cells with 0...")
df['Timeinterval Start Loc'] = pd.to_datetime(df['Timeinterval Start Loc'])
df['Date'] = df['Timeinterval Start Loc'].dt.date

# PER YOUR INSTRUCTION: Treat empty cells as 0
# We fill both the Dispatch prices AND the general Imbalance prices (Shortage/Surplus)
cols_to_fix = ['Price Dispatch Up', 'Price Dispatch Down', 'Price Shortage', 'Price Surplus']
for col in cols_to_fix:
    df[col] = df[col].fillna(0)

# HANDLING DUPLICATES & EXTRA HOURS:
# Group by Date and Isp to average Daylight Savings duplicates
df_clean = df.groupby(['Date', 'Isp'], as_index=False).agg({
    'Price Dispatch Up': 'mean',
    'Price Dispatch Down': 'mean'
})

# ENSURE STANDARD 24-HOUR DAY:
# We only take ISPs 1-96. Because we filled NaNs with 0,
# almost every day will now be "complete".
df_clean = df_clean[df_clean['Isp'] <= 96]

# ==========================================
# 4. RESHAPING TO DAILY PROFILES
# ==========================================
print("Reshaping to 96-quarter profiles...")
pivot_up = df_clean.pivot(index='Date', columns='Isp', values='Price Dispatch Up')
pivot_down = df_clean.pivot(index='Date', columns='Isp', values='Price Dispatch Down')

# Now dropna will only remove days where the entire date was missing from the file
pivot_up = pivot_up.dropna()
pivot_down = pivot_down.dropna()

common_dates = pivot_up.index.intersection(pivot_down.index)
print(f"Total 24h days found for clustering: {len(common_dates)}")

# Create the [Days x 192] Matrix
data_matrix = np.hstack([
    pivot_up.loc[common_dates].values,
    pivot_down.loc[common_dates].values
])

# ==========================================
# 5. SCALING & K-MEDOIDS CLUSTERING
# ==========================================
scaler = RobustScaler()
data_scaled = scaler.fit_transform(data_matrix)

print(f"Clustering {len(common_dates)} days into 10 scenarios...")
n_clusters = 10
kmed = KMedoids(n_clusters=n_clusters, metric='euclidean', init='k-medoids++', random_state=42)
kmed.fit(data_scaled)

# ==========================================
# 6. EXTRACT RESULTS & PROBABILITIES
# ==========================================
labels = kmed.labels_
cluster_counts = np.bincount(labels)
probabilities = cluster_counts / len(labels)

medoid_indices = kmed.medoid_indices_
representative_dates = common_dates[medoid_indices]

# Final DataFrame structure
scenarios = pd.DataFrame(data_matrix[medoid_indices])
up_cols = [f'Up_ISP_{i}' for i in range(1, 97)]
down_cols = [f'Down_ISP_{i}' for i in range(1, 97)]
scenarios.columns = up_cols + down_cols

scenarios.insert(0, 'Probability', probabilities)
scenarios.insert(1, 'Date', representative_dates)

scenarios.to_csv(output_path, index=False)

print("\n" + "=" * 40)
print("SUCCESS: CLUSTERS GENERATED USING 0-DEFAULT LOGIC")
print("=" * 40)
for i, prob in enumerate(probabilities):
    print(f"Scenario {i}: {representative_dates[i]} | Probability: {prob:.2%}")

print(f"\nCSV saved to: {output_path}")

# ==========================================
# 7. VISUALIZATION
# ==========================================
fig, axes = plt.subplots(5, 2, figsize=(15, 12))
axes = axes.flatten()

for i in range(n_clusters):
    ax = axes[i]
    ax.plot(range(1, 97), data_matrix[medoid_indices[i], :96], label='Up', color='green', alpha=0.6)
    ax.plot(range(1, 97), data_matrix[medoid_indices[i], 96:], label='Down', color='red', alpha=0.6)
    ax.set_title(f"Cluster {i}: {representative_dates[i]} ({probabilities[i]:.1%})")
    ax.grid(True, alpha=0.2)
    if i == 0: ax.legend()

plt.tight_layout()
plt.show()

import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
from sklearn_extra.cluster import KMedoids

# =================================================================
# 1. CONFIGURATION
# =================================================================
FILE_PATHS = [
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2016.xls',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2017.xls',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2018.xls',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2019.xls',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2020.xlsx',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2021.xlsx',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2022.xlsx',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2023.xlsx',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2024.xlsx',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/EnergieUebersichtCH-2025.xlsx'
]
N_SCENARIOS = 5
SHEET_NAME = 'Zeitreihen0h15'


def run_stochastic_clustering():
    all_years_raw_data = []
    year_features = []
    valid_file_names = []

    print(f"Starting analysis on {len(FILE_PATHS)} Excel files using K-Medoids...")

    for file in FILE_PATHS:
        try:
            # Handle both old (.xls) and new (.xlsx) formats
            engine = 'xlrd' if file.endswith('.xls') else 'openpyxl'
            df = pd.read_excel(file, sheet_name=SHEET_NAME, skiprows=[1], engine=engine)
            print(f"✅ Successfully loaded: {file.split('/')[-1]}")
        except Exception as e:
            print(f"❌ Could not read file {file}: {e}")
            continue

        time_col = df.columns[0]
        pos_price_col = df.columns[21]
        neg_price_col = df.columns[22]

        # A. Filter Leap Year (Feb 29) to keep years uniform at 35,040 rows
        df[time_col] = pd.to_datetime(df[time_col], dayfirst=True)
        df = df[~((df[time_col].dt.month == 2) & (df[time_col].dt.day == 29))]

        # B. Clean and subset prices (Positive and Negative Secondary Prices)
        price_subset = df[[pos_price_col, neg_price_col]].apply(pd.to_numeric, errors='coerce').ffill().bfill()
        year_values = price_subset.values[:35040, :]

        if len(year_values) < 35040:
            print(f"⚠️ Warning: {file} has insufficient rows. Skipping.")
            continue

        # C. Feature Extraction (Statistical 'Fingerprint' of the year)
        features = []
        for c in [0, 1]:
            series = year_values[:, c]
            features.extend([
                np.mean(series),
                np.std(series),
                np.percentile(series, 95),  # High spikes
                np.percentile(series, 5)  # Deep negative prices
            ])
            # Monthly averages to capture seasonality
            features.extend([np.mean(m) for m in np.array_split(series, 12)])

        all_years_raw_data.append(year_values)
        year_features.append(features)
        valid_file_names.append(file.split('/')[-1])

    if len(all_years_raw_data) < N_SCENARIOS:
        print(f"ERROR: Only {len(all_years_raw_data)} valid years found. Need {N_SCENARIOS}.")
        return None

    # =================================================================
    # 3. ROBUST CLUSTERING (K-Medoids + RobustScaler)
    # =================================================================

    # RobustScaler handles electricity price outliers much better than StandardScaler
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(year_features)

    # KMedoids directly selects the most representative actual years (Medoids)
    kmedoids = KMedoids(n_clusters=N_SCENARIOS, random_state=42, method='pam').fit(X_scaled)

    # Calculate Probabilities based on cluster sizes
    counts = np.bincount(kmedoids.labels_, minlength=N_SCENARIOS)
    probabilities = counts / len(all_years_raw_data)

    # =================================================================
    # 4. RESULTS
    # =================================================================
    print("\n" + "=" * 50)
    print("STOCHASTIC K-MEDOIDS REPRESENTATIVE YEARS")
    print("=" * 50)

    final_output = []
    # kmedoids.medoid_indices_ gives the indices of the chosen representative files
    for i, idx in enumerate(kmedoids.medoid_indices_):
        scenario_file = valid_file_names[idx]
        prob = probabilities[i]
        print(f"SCENARIO {i + 1}: {scenario_file} | Probability: {prob:.2%}")

        final_output.append({
            'probability': prob,
            'file_name': scenario_file,
            'data': all_years_raw_data[idx]  # This is your 35040x2 price matrix
        })

    return final_output


if __name__ == "__main__":
    # 1. Run the clustering
    scenarios = run_stochastic_clustering()

    if scenarios:
        # 2. Prepare the Main Data Sheet
        # Column 1: Quarters 1-35040
        export_data = {
            'Quarter': np.arange(1, 35041)
        }

        # Add Up and Down prices for each of the 5 scenarios
        for i, s in enumerate(scenarios):
            s_id = i + 1
            # Column 2, 4, 6, 8, 10: Up Prices
            export_data[f'S{s_id}_Balancing_Up'] = s['data'][:, 0]
            # Column 3, 5, 7, 9, 11: Down Prices
            export_data[f'S{s_id}_Balancing_Down'] = s['data'][:, 1]

        df_main = pd.DataFrame(export_data)

        # 3. Prepare the Probabilities Sheet
        prob_data = []
        for i, s in enumerate(scenarios):
            prob_data.append({
                'Scenario': f"Scenario {i + 1}",
                'Historical_Source': s['file_name'],
                'Probability': s['probability']
            })
        df_probs = pd.DataFrame(prob_data)

        # 4. Save to a single Excel file with two tabs
        output_file = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/Representative_Price_Scenarios.xlsx"

        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_main.to_excel(writer, sheet_name='Price_Data', index=False)
            df_probs.to_excel(writer, sheet_name='Probabilities', index=False)

        print(f"\n" + "=" * 50)
        print(f"SUCCESS: Result saved to {output_file}")
        print("Sheet 1: 'Price_Data' contains all 11 columns.")
        print("Sheet 2: 'Probabilities' contains the weights for your optimization.")
        print("=" * 50)
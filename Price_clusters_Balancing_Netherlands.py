import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
from sklearn_extra.cluster import KMedoids

# =================================================================
# 1. CONFIGURATION
# =================================================================
FILE_PATHS = [
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_201812312300_201912312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_201912312300_202012312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_202012312300_202112312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_202112312300_202212312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_202212312300_202312312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_202312312300_202412312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/settlement_prices_202412312300_202512312300.csv'
]
N_SCENARIOS = 5

TIME_COL = 'Timeinterval Start Loc'
UP_PRICE_COL = 'Price Dispatch Up'
DOWN_PRICE_COL = 'Price Dispatch Down'


def run_stochastic_clustering_nl():
    all_years_raw_data = []
    year_features = []
    valid_file_names = []

    print(f"Starting analysis on {len(FILE_PATHS)} CSV files using K-Medoids...")

    for file in FILE_PATHS:
        try:
            # Read the csv
            df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8-sig')
            df.columns = df.columns.str.strip()
            TIME_COL = [c for c in df.columns if 'Timeinterval Start Loc' in c][0]
            UP_PRICE_COL = [c for c in df.columns if 'Price Dispatch Up' in c][0]
            DOWN_PRICE_COL = [c for c in df.columns if 'Price Dispatch Down' in c][0]
            print(f"✅ Successfully loaded: {file.split('/')[-1]}")
        except Exception as e:
            print(f"❌ Could not read file {file}: {e}")
            continue

        # A. Filter Leap Year (Feb 29) to keep years uniform at 35,040 rows
        df[TIME_COL] = pd.to_datetime(df[TIME_COL], format='ISO8601')
        df = df[~((df[TIME_COL].dt.month == 2) & (df[TIME_COL].dt.day == 29))]

        # B. Clean and subset prices (Up and Down Columns) - At NaN display zeros
        price_subset = df[[UP_PRICE_COL, DOWN_PRICE_COL]].apply(pd.to_numeric, errors='coerce').fillna(0.0)
        year_values = price_subset.values[:35040, :]

        if len(year_values) < 35040:
            print(f"⚠️ Warning: {file} has insufficient rows ({len(year_values)}). Skipping.")
            continue

        # C. Feature Extraction (Statistical 'Fingerprint' remains identical)
        features = []
        for c in [0, 1]:
            series = year_values[:, c]
            features.extend([
                np.mean(series),
                np.std(series),
                np.percentile(series, 95),
                np.percentile(series, 5)
            ])
            features.extend([np.mean(m) for m in np.array_split(series, 12)])

        all_years_raw_data.append(year_values)
        year_features.append(features)
        valid_file_names.append(file.split('/')[-1])

    if len(all_years_raw_data) < N_SCENARIOS:
        print(f"ERROR: Only {len(all_years_raw_data)} valid years found. Need {N_SCENARIOS}.")
        return None

    # 3. ROBUST CLUSTERING
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(year_features)
    kmedoids = KMedoids(n_clusters=N_SCENARIOS, random_state=42, method='pam').fit(X_scaled)

    probabilities = np.bincount(kmedoids.labels_, minlength=N_SCENARIOS) / len(all_years_raw_data)

    # 4. RESULTS & EXCEL EXPORT
    print("\n" + "=" * 50 + "\nSTOCHASTIC K-MEDOIDS REPRESENTATIVE YEARS (NL)\n" + "=" * 50)

    # Prepare the Main Data Sheet
    export_data = {'Quarter': np.arange(1, 35041)}
    prob_data = []

    for i, idx in enumerate(kmedoids.medoid_indices_):
        s_id = i + 1
        scenario_file = valid_file_names[idx]
        prob = probabilities[i]

        print(f"SCENARIO {s_id}: {scenario_file} | Probability: {prob:.2%}")

        # Add columns using the exact naming convention for compatibility
        export_data[f'S{s_id}_Balancing_Up'] = all_years_raw_data[idx][:, 0]
        export_data[f'S{s_id}_Balancing_Down'] = all_years_raw_data[idx][:, 1]

        # Prepare the Probabilities Sheet data
        prob_data.append({
            'Scenario': f"Scenario {s_id}",
            'Historical_Source': scenario_file,
            'Probability': prob
        })

    # Convert to DataFrames
    df_main = pd.DataFrame(export_data)
    df_probs = pd.DataFrame(prob_data)

    # Define the output path
    output_file = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/Representative_NL_Price_Scenarios.xlsx"

    # Save with the two required sheets: 'Price_Data' and 'Probabilities'
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_main.to_excel(writer, sheet_name='Price_Data', index=False)
            df_probs.to_excel(writer, sheet_name='Probabilities', index=False)

        print(f"\n✅ SUCCESS: Result saved to {output_file}")
    except Exception as e:
        print(f"❌ Error saving Excel file: {e}")
        # Fallback to current directory if the long path is restricted
        df_main.to_excel("Representative_NL_Scenarios_LCL.xlsx", index=False)
        print("Saved a local copy: Representative_NL_Scenarios_LCL.xlsx")

    return True

if __name__ == "__main__":
    run_stochastic_clustering_nl()

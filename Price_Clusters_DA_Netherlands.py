import pandas as pd
import numpy as np
from sklearn.preprocessing import RobustScaler
from sklearn_extra.cluster import KMedoids

# Eventually not relevant since no DA stochasticity was introduced at the end
# =================================================================
# 1. CONFIGURATION
# =================================================================
FILE_PATHS = [
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_201512312300-201612312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_201612312300-201712312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_201712312300-201812312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_201812312300-201912312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_201912312300-202012312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_202012312300-202112312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_202112312300-202212312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_202212312300-202312312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_202312312300-202412312300.csv',
    '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/GUI_ENERGY_PRICES_202412312300-202512312300.csv'
]
N_SCENARIOS = 5

# Strict target for a standard non-leap year at hourly resolution (365 days * 24 hours)
HOURS_PER_YEAR = 8760


def run_stochastic_DAM_clustering_NL():
    all_years_raw_data = []
    year_features = []
    valid_file_names = []

    print(f"Starting analysis on {len(FILE_PATHS)} CSV files using K-Medoids...")

    for file in FILE_PATHS:
        try:
            # Read the CSV
            df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8-sig')
            df.columns = df.columns.str.strip()

            # Dynamically fetch the time and Day-Ahead Price columns
            TIME_COL = [c for c in df.columns if 'MTU' in c][0]
            DA_PRICE_COL = [c for c in df.columns if 'Day-ahead Price' in c][0]
        except Exception as e:
            print(f"❌ Could not read file {file}: {e}")
            continue

        # A. Clean strings and extract dates for leap year filtering
        df['Start_Time_Str'] = df[TIME_COL].str.split('-').str[0].str.strip()
        df['Start_Time_Parsed'] = pd.to_datetime(df['Start_Time_Str'], format='%d/%m/%Y %H:%M:%S', errors='coerce')

        # B. Filter Leap Year (Feb 29) to keep profiles uniform
        # Note: We do NOT sort or drop duplicates anymore to preserve the original 25-hour raw timeline sequence
        df = df[~((df['Start_Time_Parsed'].dt.month == 2) & (df['Start_Time_Parsed'].dt.day == 29))]

        # C. Process prices sequentially
        df[DA_PRICE_COL] = pd.to_numeric(df[DA_PRICE_COL], errors='coerce')
        df[DA_PRICE_COL] = df[DA_PRICE_COL].ffill().fillna(0.0)

        year_values = df[DA_PRICE_COL].values

        # D. Unified Array Management: Ensure the timeline is exactly 8,760 hours
        # This keeps the continuous sequential order from the file intact.
        if len(year_values) < HOURS_PER_YEAR:
            padding_size = HOURS_PER_YEAR - len(year_values)
            last_val = year_values[-1] if len(year_values) > 0 else 0.0
            year_values = np.concatenate([year_values, np.full(padding_size, last_val)])
        elif len(year_values) > HOURS_PER_YEAR:
            year_values = year_values[:HOURS_PER_YEAR]

        print(f"✅ Successfully processed: {file.split('/')[-1]} ({len(year_values)} hours sequentially)")

        # E. Feature Extraction
        features = [
            np.mean(year_values),
            np.std(year_values),
            np.percentile(year_values, 95),
            np.percentile(year_values, 5)
        ]
        features.extend([np.mean(m) for m in np.array_split(year_values, 12)])

        all_years_raw_data.append(year_values)
        year_features.append(features)
        valid_file_names.append(file.split('/')[-1])

    if len(all_years_raw_data) < N_SCENARIOS:
        print(f"\nERROR: Only {len(all_years_raw_data)} valid years found. Need {N_SCENARIOS}.")
        return None

    # 3. ROBUST CLUSTERING
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(year_features)
    kmedoids = KMedoids(n_clusters=N_SCENARIOS, random_state=42, method='pam').fit(X_scaled)

    probabilities = np.bincount(kmedoids.labels_, minlength=N_SCENARIOS) / len(all_years_raw_data)

    # 4. RESULTS & EXCEL EXPORT
    print("\n" + "=" * 50 + "\nSTOCHASTIC K-MEDOIDS REPRESENTATIVE YEARS (DAM)\n" + "=" * 50)

    export_data = {'Hour': np.arange(1, HOURS_PER_YEAR + 1)}
    prob_data = []

    for i, idx in enumerate(kmedoids.medoid_indices_):
        s_id = i + 1
        scenario_file = valid_file_names[idx]
        prob = probabilities[i]

        print(f"SCENARIO {s_id}: {scenario_file} | Probability: {prob:.2%}")

        export_data[f'S{s_id}_DayAhead_Price'] = all_years_raw_data[idx]

        prob_data.append({
            'Scenario': f"Scenario {s_id}",
            'Historical_Source': scenario_file,
            'Probability': prob
        })

    df_main = pd.DataFrame(export_data)
    df_probs = pd.DataFrame(prob_data)

    output_file = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/Representative_DAM_Price_Scenarios_NL.xlsx"

    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_main.to_excel(writer, sheet_name='Price_Data', index=False)
            df_probs.to_excel(writer, sheet_name='Probabilities', index=False)
        print(f"\n✅ SUCCESS: Result saved to {output_file}")
    except Exception as e:
        print(f"❌ Error saving Excel file: {e}")
        df_main.to_excel("Representative_DAM_Scenarios_LCL.xlsx", index=False)
        print("Saved a local copy: Representative_DAM_Scenarios_LCL.xlsx")

    return True


if __name__ == "__main__":
    run_stochastic_DAM_clustering_NL()
import os
import pandas as pd
import numpy as np

# Eventually not relevant since no DA stochasticity was introduced at the end
def expand_dam_scenarios_with_tariff_CH():
    # --- PATH CONFIGURATION ---
    input_file = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Zurich/Representative_DAM_Price_Scenarios_CH.xlsx'
    output_file = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Zurich/Representative_DAM_Price_Scenarios_CH_Expanded.xlsx'

    grid_tariff_CH = 49.0  # EUR/MWh Swiss grid tariff
    quarters_per_year = 35040

    if not os.path.exists(input_file):
        print(f"❌ Error: {input_file} not found in the current directory.")
        return

    print(f"Reading {input_file}...")

    # 1. Read both existing sheets
    df_price = pd.read_excel(input_file, sheet_name='Price_Data')
    df_probs = pd.read_excel(input_file, sheet_name='Probabilities')

    # 2. Build the high-resolution dictionary structure
    expanded_data = {
        'Quarter': np.arange(1, quarters_per_year + 1)
    }

    # 3. Process every scenario column dynamically
    scenario_cols = [c for c in df_price.columns if c.startswith('S') and 'Price' in c]

    for col in scenario_cols:
        # A. Add the grid tariff to the 8760 hourly values
        tariff_adjusted_hourly = df_price[col].values + grid_tariff_CH

        # B. Repeat each hour 4 times sequentially for 15-minute intervals
        expanded_data[col] = np.repeat(tariff_adjusted_hourly, 4)

    # 4. Reassemble into a clean DataFrame
    df_expanded_price = pd.DataFrame(expanded_data)
    print(f"✅ Data successfully transformed to {df_expanded_price.shape[0]} quarter-hour timesteps.")

    # 5. Save back to a multi-sheet Excel workbook
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_expanded_price.to_excel(writer, sheet_name='Price_Data', index=False)
            df_probs.to_excel(writer, sheet_name='Probabilities', index=False)
        print(f"✅ SUCCESS: Consolidated and expanded output saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving Excel file: {e}")


def expand_dam_scenarios_with_tariff_NL():
    # --- PATH CONFIGURATION ---
    input_file = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/Representative_DAM_Price_Scenarios_NL.xlsx'
    output_file = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/Representative_DAM_Price_Scenarios_NL_Expanded.xlsx'

    grid_tariff_NL = 30.0  # EUR/MWh Swiss grid tariff
    quarters_per_year = 35040

    if not os.path.exists(input_file):
        print(f"❌ Error: {input_file} not found in the current directory.")
        return

    print(f"Reading {input_file}...")

    # 1. Read both existing sheets
    df_price = pd.read_excel(input_file, sheet_name='Price_Data')
    df_probs = pd.read_excel(input_file, sheet_name='Probabilities')

    # 2. Build the high-resolution dictionary structure
    expanded_data = {
        'Quarter': np.arange(1, quarters_per_year + 1)
    }

    # 3. Process every scenario column dynamically
    scenario_cols = [c for c in df_price.columns if c.startswith('S') and 'Price' in c]

    for col in scenario_cols:
        # A. Add the grid tariff to the 8760 hourly values
        tariff_adjusted_hourly = df_price[col].values + grid_tariff_NL

        # B. Repeat each hour 4 times sequentially for 15-minute intervals
        expanded_data[col] = np.repeat(tariff_adjusted_hourly, 4)

    # 4. Reassemble into a clean DataFrame
    df_expanded_price = pd.DataFrame(expanded_data)
    print(f"✅ Data successfully transformed to {df_expanded_price.shape[0]} quarter-hour timesteps.")

    # 5. Save back to a multi-sheet Excel workbook
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df_expanded_price.to_excel(writer, sheet_name='Price_Data', index=False)
            df_probs.to_excel(writer, sheet_name='Probabilities', index=False)
        print(f"✅ SUCCESS: Consolidated and expanded output saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving Excel file: {e}")

if __name__ == "__main__":
    expand_dam_scenarios_with_tariff_CH()
    expand_dam_scenarios_with_tariff_NL()
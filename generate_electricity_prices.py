import pandas as pd
import numpy as np
import os

# --- PATH CONFIGURATION ---
base_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/'
ch_filename = 'GUI_ENERGY_PRICES_202412312300-202512312300_Switzerland.csv'  # Ensure these match your filenames
nl_filename = 'GUI_ENERGY_PRICES_202412312300-202512312300_Netherlands.csv'
output_filename = 'DAM_Prices_2025_Consolidated.xlsx'


def generate_consolidated_excel(base_path, ch_file, nl_file):
    # 1. Process Switzerland (ACTUAL 2025 data)
    def process_switzerland_average(filename):
        path = os.path.join(base_path, ch_file)
        df = pd.read_csv(path)

        # Clean and parse timestamps (removing (CET)/(CEST))
        raw_times = df['MTU (CET/CEST)'].str.split(' - ').str[0]
        clean_times = raw_times.str.replace(r'\s*\(.*\)', '', regex=True)

        df['Timestamp'] = pd.to_datetime(clean_times, dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Timestamp']).set_index('Timestamp').sort_index()

        # Convert Price to numeric
        price_col = 'Day-ahead Price (EUR/MWh)'
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')

        # Resample to Hourly (averaging 4 quarters)
        df_hourly = df[[price_col]].resample('h').mean()

        # Filter strictly for 2025
        df_2025 = df_hourly.loc['2025-01-01 00:00:00':'2025-12-31 23:00:00'].copy()

        # Ensure we have exactly 8760 rows
        if len(df_2025) != 8760:
            full_range = pd.date_range(start='2025-01-01 00:00:00', end='2025-12-31 23:00:00', freq='h')
            df_2025 = df_2025.reindex(full_range).ffill()

        return df_2025['Day-ahead Price (EUR/MWh)'].values

    # 2. Process Netherlands (ACTUAL 2025 DATA)
    def process_netherlands_2025(filename):
        path = os.path.join(base_path, nl_file)
        df = pd.read_csv(path)

        # Clean and parse timestamps (removing (CET)/(CEST))
        raw_times = df['MTU (CET/CEST)'].str.split(' - ').str[0]
        clean_times = raw_times.str.replace(r'\s*\(.*\)', '', regex=True)

        df['Timestamp'] = pd.to_datetime(clean_times, dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Timestamp']).set_index('Timestamp').sort_index()

        # Convert Price to numeric
        price_col = 'Day-ahead Price (EUR/MWh)'
        df[price_col] = pd.to_numeric(df[price_col], errors='coerce')

        # Resample to Hourly (averaging 4 quarters)
        df_hourly = df[[price_col]].resample('h').mean()

        # Filter strictly for 2025
        df_2025 = df_hourly.loc['2025-01-01 00:00:00':'2025-12-31 23:00:00'].copy()

        # Ensure we have exactly 8760 rows
        if len(df_2025) != 8760:
            full_range = pd.date_range(start='2025-01-01 00:00:00', end='2025-12-31 23:00:00', freq='h')
            df_2025 = df_2025.reindex(full_range).ffill()

        return df_2025['Day-ahead Price (EUR/MWh)'].values

    try:
        print("Processing 2025 data for Switzerland ...")
        swiss_2025_values = process_switzerland_average(ch_file)

        print("Processing 2025 data for Netherlands...")
        dutch_2025_values = process_netherlands_2025(nl_file)

        # 3. Combine into final DataFrame
        # add a grid tarrif
        grid_tarrif_CH = 49 #(https://www.ekz.ch/de/angebote/strom/tarife/tarife-geschaeftskunden-ab-100MWh.html)
        grid_tarrif_NL = 30 #(https://www.tennet.eu/tariffs)
        # Check if arrays are same length (8760)
        min_len = min(len(swiss_2025_values), len(dutch_2025_values))

        combined_df = pd.DataFrame({
            'Hour_of_the_Year': range(1, min_len + 1),
            'Swiss_DAM_Price_2025': swiss_2025_values[:min_len] + grid_tarrif_CH,
            'Dutch_DAM_Price_2025': dutch_2025_values[:min_len] + grid_tarrif_NL
        })

        # 4. Save to Excel
        final_output_path = os.path.join(base_path, output_filename)
        combined_df.to_excel(final_output_path, index=False)

        print("-" * 50)
        print(f"✅ Success! Consolidated file created.")
        print(f"Location: {final_output_path}")
        print("-" * 50)

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    generate_consolidated_excel(base_path, ch_filename, nl_filename)
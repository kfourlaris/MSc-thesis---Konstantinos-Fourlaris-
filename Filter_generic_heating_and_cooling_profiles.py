import pandas as pd
import os


def filter_raw_data():
    base_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/'

    # List of the 6 raw files - Includes SH, SC, DHW both residential and tertiary
    raw_files = [
        'Residential_space_heating_load.csv',
        'Tertiary_space_heating_load.csv',
        'Residential_space_cooling_load.csv',
        'Tertiary_space_cooling_load.csv',
        'Residential_hot_domestic_water_load.csv',
        'Tertiary_hot_domestic_water_load.csv'
    ]

    target_codes = ['CH04', 'NL32'] #reduce the rows of the input data

    for file_name in raw_files:
        full_path = os.path.join(base_path, file_name)

        if os.path.exists(full_path):
            print(f"Processing {file_name}...")
            # Load raw data
            df = pd.read_csv(full_path)

            # Filter for Zurich (CH004) and Amsterdam (NL32)
            filtered_df = df[df['NUTS2_code'].isin(target_codes)]

            # Save as a new file (adding 'Filtered_' prefix)
            new_file_name = "Filtered_" + file_name
            filtered_df.to_csv(os.path.join(base_path, new_file_name), index=False)
            print(f"Saved: {new_file_name}")
        else:
            print(f"File not found: {file_name}")


if __name__ == "__main__":
    filter_raw_data()
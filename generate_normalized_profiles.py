import pandas as pd
import holidays
import numpy as np
from datetime import datetime, timedelta


def create_energy_demand_data():
    # 1. SETUP PATHS
    base_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/'

    # 2. GENERATE TIME RANGE FOR 2025
    start_date = datetime(2025, 1, 1, 0, 0)
    timestamps = [start_date + timedelta(hours=x) for x in range(8760)]
    df = pd.DataFrame({'Timestamp': timestamps})
    df['Date_Month_Year_Time'] = df['Timestamp'].dt.strftime('%d-%m-%Y %H:%M')
    df['Hour_of_Year'] = range(1, 8761)
    df['hour_lookup'] = df['Timestamp'].dt.hour + 1

    # 3. SEASON LOGIC (DHW Residential Only)
    def get_season(dt):
        md = dt.month * 100 + dt.day
        if 515 <= md <= 914:
            return 0  # Summer
        elif md >= 1101 or md <= 320:
            return 1  # Winter
        else:
            return 2  # Transition

    df['Season_Lookup'] = df['Timestamp'].apply(get_season)

    # 4. DAY TYPE LOGIC
    zh_hols = holidays.CH(prov='ZH', years=2025)
    am_hols = holidays.NL(years=2025)
    df['DT_ZH'] = df['Timestamp'].apply(
        lambda dt: 2 if (dt in zh_hols or dt.weekday() == 6) else (1 if dt.weekday() == 5 else 0))
    df['DT_AM'] = df['Timestamp'].apply(
        lambda dt: 2 if (dt in am_hols or dt.weekday() == 6) else (1 if dt.weekday() == 5 else 0))

    # 5. LOAD TEMPERATURES
    def get_averaged_temp(file_name):
        # Load the full historical dataset
        raw = pd.read_csv(base_path + file_name)
        raw['time'] = pd.to_datetime(raw['time'])

        # Group by Month, Day, and Hour and calculate the average temperature
        # This creates a "typical" value for every hour of the year
        avg_series = raw.groupby([
            raw['time'].dt.month,
            raw['time'].dt.day,
            raw['time'].dt.hour
        ])['temp'].mean()

        return avg_series.values

    # Apply the averaging logic to both cities
    df['ZH_Temp'] = get_averaged_temp('Zurich_meteo_raw_data.csv')
    df['AM_Temp'] = get_averaged_temp('Amsterdam_meteo_raw_data.csv')

    # 6. HEATING/COOLING LOOKUP FUNCTION
    def process_thermal_file(file_name, threshold, mode='heating'):
        ref_df = pd.read_csv(base_path + file_name)
        lookup = {(n, d, h): (t, l) for (n, d, h), g in ref_df.groupby(['NUTS2_code', 'day_type', 'hour'])
                  for t, l in [(g['temperature'].values, g['load'].values)]}

        def get_val(row, code, t_col, dt_col):
            t_val = row[t_col]
            if (mode == 'heating' and t_val > threshold) or (mode == 'cooling' and t_val < threshold):
                return 0.0
            key = (code, row[dt_col], row['hour_lookup'])
            if key not in lookup: return 0.0
            temps, loads = lookup[key]
            return loads[np.abs(temps - t_val).argmin()]

        zh_raw = df.apply(lambda r: get_val(r, 'CH04', 'ZH_Temp', 'DT_ZH'), axis=1)
        am_raw = df.apply(lambda r: get_val(r, 'NL32', 'AM_Temp', 'DT_AM'), axis=1)
        return zh_raw / zh_raw.sum(), am_raw / am_raw.sum()

    # 7. DOMESTIC HOT WATER LOOKUP FUNCTION
    def process_dhw_file(file_name, use_season=True):
        ref_df = pd.read_csv(base_path + file_name)

        if use_season:
            # Residential Logic: Includes Season
            lookup = ref_df.set_index(['NUTS2_code', 'day_type', 'hour', 'season'])['load'].to_dict()

            def get_dhw(row, code, dt_col):
                key = (code, row[dt_col], row['hour_lookup'], row['Season_Lookup'])
                return lookup.get(key, 0.0)
        else:
            # Tertiary Logic: Ignores Season
            lookup = ref_df.set_index(['NUTS2_code', 'day_type', 'hour'])['load'].to_dict()

            def get_dhw(row, code, dt_col):
                key = (code, row[dt_col], row['hour_lookup'])
                return lookup.get(key, 0.0)

        zh_raw = df.apply(lambda r: get_dhw(r, 'CH04', 'DT_ZH'), axis=1)
        am_raw = df.apply(lambda r: get_dhw(r, 'NL32', 'DT_AM'), axis=1)
        return zh_raw / zh_raw.sum(), am_raw / am_raw.sum()

    # 8. EXECUTE ALL CALCULATIONS
    print("Processing Heating & Cooling...")
    df['ZH_res_heating'], df['AM_res_heating'] = process_thermal_file('Filtered_Residential_space_heating_load.csv', 17,
                                                                      'heating')
    df['ZH_ter_heating'], df['AM_ter_heating'] = process_thermal_file('Filtered_Tertiary_space_heating_load.csv', 17,
                                                                      'heating')
    df['ZH_res_cooling'], df['AM_res_cooling'] = process_thermal_file('Filtered_Residential_space_cooling_load.csv', 20,
                                                                      'cooling')
    df['ZH_ter_cooling'], df['AM_ter_cooling'] = process_thermal_file('Filtered_Tertiary_space_cooling_load.csv', 20,
                                                                      'cooling')

    print("Processing Residential Hot Water (Seasonal)...")
    df['ZH_res_hot_water'], df['AM_res_hot_water'] = process_dhw_file('Filtered_Residential_hot_domestic_water_load.csv',
                                                                      use_season=True)

    print("Processing Tertiary Hot Water (Hourly only)...")
    df['ZH_ter_hot_water'], df['AM_ter_hot_water'] = process_dhw_file('Filtered_Tertiary_hot_domestic_water_load.csv',
                                                                      use_season=False)

    # 9. FINAL EXCEL EXPORT
    final_cols = [
        'Date_Month_Year_Time', 'Hour_of_Year', 'DT_ZH', 'DT_AM', 'ZH_Temp', 'AM_Temp',
        'ZH_res_heating', 'AM_res_heating', 'ZH_ter_heating', 'AM_ter_heating',
        'ZH_res_cooling', 'AM_res_cooling', 'ZH_ter_cooling', 'AM_ter_cooling',
        'ZH_res_hot_water', 'AM_res_hot_water', 'ZH_ter_hot_water', 'AM_ter_hot_water'
    ]

    output_path = base_path + "Normalized_heating_and_cooling_profiles_2025.xlsx"
    df[final_cols].to_excel(output_path, index=False)
    print(f"Final Report saved successfully to: {output_path}")


if __name__ == "__main__":
    create_energy_demand_data()
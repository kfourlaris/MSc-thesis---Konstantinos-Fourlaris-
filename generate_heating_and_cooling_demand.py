import pandas as pd
import matplotlib.pyplot as plt


def calculate_final_energy_demands():
    base_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/'

    # ---------------------------------------------------------
    # 1. THE CONTROL PANEL
    # ---------------------------------------------------------
    params = {
        'Zurich': {
            'Annual_Heat_MWh': 1350000,  # Total Heat (SH + DHW)
            'Annual_Cooling_MWh': 175000,
            'DHW_Share_of_Heat': 0.20,  # 20% of total heat is DHW
            'Network_Share_Res': 0.65,  # 65% Residential share of network
            'Network_Share_Ter': 0.35  # 35% Tertiary share of network
        },
        'Amsterdam': {
            'Annual_Heat_MWh': 2000000,  # Total Heat (SH + DHW)
            'Annual_Cooling_MWh': 100000,
            'DHW_Share_of_Heat': 0.30,  # 30% of total heat is DHW
            'Network_Share_Res': 0.55,  # 55% Residential share of network
            'Network_Share_Ter': 0.45  # 45% Tertiary share of network
        },
        'Global': {
            'Cooling_Share_Res': 0.10,  # 10% Res for cooling
            'Cooling_Share_Ter': 0.90  # 90% Ter for cooling
        }
    }

    # 2. LOAD DATA
    input_file = base_path + "Normalized_heating_and_cooling_profiles_2025.xlsx"
    try:
        df = pd.read_excel(input_file)
    except Exception as e:
        print(f"Error: {e}")
        return

    # 3. CALCULATE SEPARATE BUCKETS
    for city in ['Zurich', 'Amsterdam']:
        p = params[city]

        # Split total energy into SH and DHW buckets
        mwh_dhw = p['Annual_Heat_MWh'] * p['DHW_Share_of_Heat']
        mwh_sh = p['Annual_Heat_MWh'] * (1 - p['DHW_Share_of_Heat'])

        # Get City-specific column prefixes
        c_pre = 'ZH' if city == 'Zurich' else 'AM'

        # --- HEATING CALCULATION ---
        # Part A: Space Heating (Normalized Profiles * Network Shares) * SH Bucket
        sh_profile = (df[f'{c_pre}_res_heating'] * p['Network_Share_Res'] +
                      df[f'{c_pre}_ter_heating'] * p['Network_Share_Ter']) * mwh_sh

        # Part B: Hot Water (Normalized Profiles * Network Shares) * DHW Bucket
        dhw_profile = (df[f'{c_pre}_res_hot_water'] * p['Network_Share_Res'] +
                       df[f'{c_pre}_ter_hot_water'] * p['Network_Share_Ter']) * mwh_dhw

        df[f'{city}_Total_Heating_MWh'] = sh_profile + dhw_profile

        # --- COOLING CALCULATION ---
        df[f'{city}_Total_Cooling_MWh'] = (
                                              (df[f'{c_pre}_res_cooling'] * params['Global']['Cooling_Share_Res'] +
                                               df[f'{c_pre}_ter_cooling'] * params['Global']['Cooling_Share_Ter'])
                                          ) * p['Annual_Cooling_MWh']

    # 4. EXPORT
    output_cols = [
        'Date_Month_Year_Time', 'Hour_of_Year',
        'Zurich_Total_Heating_MWh', 'Amsterdam_Total_Heating_MWh',
        'Zurich_Total_Cooling_MWh', 'Amsterdam_Total_Cooling_MWh'
    ]

    final_path = base_path + "Final_Network_Demand_MWh.xlsx"
    df[output_cols].to_excel(final_path, index=False)

    print("Success! Corrected MWh Calculation complete.")

    # ---------------------------------------------------------
    # 5. PLOTTING LOGIC
    # ---------------------------------------------------------
    print("Generating plots...")

    # Plot 1: HEATING DEMAND
    plt.figure(figsize=(15, 6))
    plt.plot(df['Hour_of_Year'], df['Zurich_Total_Heating_MWh'], label='Zurich Heating', alpha=0.7, color='firebrick')
    plt.plot(df['Hour_of_Year'], df['Amsterdam_Total_Heating_MWh'], label='Amsterdam Heating', alpha=0.7,
             color='darkorange')
    plt.title('Total Hourly Heating Demand 2025 (Space Heating + DHW)')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Demand (MWh)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend()
    plt.savefig(base_path + "Heating_Demand_Plot.png", dpi=300)
    plt.close()

    # Plot 2: COOLING DEMAND
    plt.figure(figsize=(15, 6))
    plt.plot(df['Hour_of_Year'], df['Zurich_Total_Cooling_MWh'], label='Zurich Cooling', alpha=0.7, color='royalblue')
    plt.plot(df['Hour_of_Year'], df['Amsterdam_Total_Cooling_MWh'], label='Amsterdam Cooling', alpha=0.7,
             color='lightseagreen')
    plt.title('Total Hourly Cooling Demand 2025')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Demand (MWh)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend()
    plt.savefig(base_path + "Cooling_Demand_Plot.png", dpi=300)
    plt.close()

    print(f"Plots saved as PNG in: {base_path}")

    # ---------------------------------------------------------
    # 3. ZURICH COOLING (Initial Linewidth Style)
    # ---------------------------------------------------------
    print("Generating Zurich Cooling Plot (Initial Style)...")
    plt.figure(figsize=(15, 6))
    plt.plot(df['Hour_of_Year'], df['Zurich_Total_Cooling_MWh'],
             label='Zurich Cooling',
             color='royalblue',
             alpha=0.7)  # Using initial default linewidth and alpha

    plt.title('Zurich: Total Hourly Cooling Demand 2025')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Demand (MWh)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend()

    plt.savefig(base_path + "Zurich_Cooling_Initial_Style.png", dpi=300)
    plt.close()

    print(f"Zurich-only plots saved with original styling to: {base_path}")

    # ---------------------------------------------------------
    # 2. ZURICH HEATING (Initial Linewidth Style)
    # ---------------------------------------------------------
    print("Generating Zurich Heating Plot (Initial Style)...")
    plt.figure(figsize=(15, 6))
    plt.plot(df['Hour_of_Year'], df['Zurich_Total_Heating_MWh'],
             label='Zurich Heating',
             color='firebrick',
             alpha=0.7)  # Using initial default linewidth and alpha

    plt.title('Zurich: Total Hourly Heating Demand 2025')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Demand (MWh)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend()

    plt.savefig(base_path + "Zurich_Heating_Initial_Style.png", dpi=300)
    plt.close()

if __name__ == "__main__":
    calculate_final_energy_demands()
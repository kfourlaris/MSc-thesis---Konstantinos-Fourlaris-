import numpy as np
import pandas as pd

# --- GLOBAL SETTINGS (Subject to change) ---
INTEREST_RATE = 0.12
LIFESPAN = 20
T_SINK = 70.0  # DH Supply Temperature
T_RETURN = 30  # DH Return Temperature
T_COOLING = 6  # DC Supply Temperature Reporting instructions for completing the district heating and cooling template Directive 2017/27/EU

# --- ENERGY DEMAND ---
# CHANGE THIS TO "Amsterdam" OR "Zurich" TO SWITCH THE ENTIRE MODEL
SELECTED_CITY = "Amsterdam"

# File paths
DEMAND_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Final_Network_Demand_MWh.xlsx'
PRICE_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/DAM_Prices_2025_Consolidated.xlsx'

# Mapping dictionary to handle the column names dynamically
CITY_CONFIG = {
    "Zurich": {
        "heat_col": "Zurich_Total_Heating_MWh",
        "cool_col": "Zurich_Total_Cooling_MWh",
        "elec_price_col": "Swiss_DAM_Price_2025"  # Averaged profile for Switzerland
    },
    "Amsterdam": {
        "heat_col": "Amsterdam_Total_Heating_MWh",
        "cool_col": "Amsterdam_Total_Cooling_MWh",
        "elec_price_col": "Dutch_DAM_Price_2025" # Actual 2025 profile for NL
    }
}

# --- EXPERIMENT CONTROL PANEL ---
# Set to True to enable, False to disable
TECH_SWITCHES = {
    "BiomassBoiler": True,
    "CHP": True,
    "LargeScaleHeatPump": True,
    "TES": True,
    "LargeScaleChiller": False
}

# 2. Load Electricity Prices
df_prices = pd.read_excel(PRICE_DATA_PATH)
# We convert EUR/MWh to EUR/kWh if your model uses kWh for energy (divide by 1000)
elec_prices_kwh = df_prices[CITY_CONFIG[SELECTED_CITY]["elec_price_col"]].values / 1000

# --- MARKET PRICES ---
# Create a full year time range for 2025
time_index = pd.date_range(start='2025-01-01', periods=8760, freq='h')

BIOMASS_PRICE = 0.05  # Euro/kWh
gas_prices_monthly = 0.056

# Monthly gas prices in EUR/kWh => Source: (https://www.protergia.gr/en/home/natural-gas/ttf-prices-per-month/)
#monthly_gas_prices = {
    #1: 0.045058 * 1.15, 2: 0.048140 * 1.15, 3: 0.047140 * 1.15,
    #4: 0.041960 * 1.15, 5: 0.035622 * 1.15, 6: 0.035340 * 1.15,
    #7: 0.036697 * 1.15, 8: 0.033847 * 1.15, 9: 0.032869 * 1.15,
    #10: 0.032343 * 1.15, 11: 0.31946 * 1.15, 12: 0.030884 * 1.15,
#}

#gas_prices_monthly = np.array([
    #monthly_gas_prices[dt.month]
    #for dt in time_index
#])

FUEL_PRICES = {
    "biomass": BIOMASS_PRICE,
    "gas": gas_prices_monthly
}
ELEC_REVENUE = 0.10  # Selling price for CHP electricity
DYNAMIC_ELEC_PRICES = elec_prices_kwh

# --- DATA GENERATION (Ambient Temperatures) ---
# Here we would later load Zurich/Amsterdam Excel/CSV files
monthly_temps = {
    1: 4, 2: 2, 3: 5, 4: 7, 5: 12, 6: 14,
    7: 17, 8: 18, 9: 15, 10: 11, 11: 7, 12: 4
}

# Map the monthly averages to every hour
T_source_hourly = np.array([monthly_temps[dt.month] for dt in time_index])

# --- MATH FUNCTIONS ---
def _calculate_annuity_factor(i, n):
    if i == 0: return 1 / n
    return (i * (1 + i)**n) / ((1 + i)**n - 1)

def _calculate_heating_cop(T_s_vec, T_k):
    dT = T_k - np.array(T_s_vec)
    # The Regression Formula from (https://doi.org/10.1016/j.rser.2020.110646) for R717 refrigerant
    cop = 0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684
    return np.maximum(cop, 1.0).tolist()

def _calculate_cooling_cop(T_s_vec, T_k):
    """
        Calculates a dynamic cooling COP vector for an electric motor-driven chiller.

        The base coefficient (4.70) and temperature sensitivity factor (0.0045)
        are calibrated so that the machine operates around a standard COP of 4.5
        under realistic summer lake temperature lifts.
        """

    # Source: (ASHRAE Standard 90.1-2019 / 2022 (Table 6.8.1-3: Water-Chilling Packages - Minimum Efficiency Requirements)

    cop_cool = 4.70 * (1.0 - 0.0045 * (np.array(T_s_vec) - T_k))

    # Enforce a physical lower safety bound just in case
    return np.maximum(cop_cool, 0.1).tolist()

# --- EXPORTED VARIABLES ---
ANNUITY_FACTOR = _calculate_annuity_factor(INTEREST_RATE, LIFESPAN)
COP_VEC = _calculate_heating_cop(T_source_hourly, T_SINK)
COP_COOL_VEC = _calculate_cooling_cop(T_source_hourly, T_COOLING)



import numpy as np
import pandas as pd

# --- GLOBAL SETTINGS (Subject to change) ---
INTEREST_RATE = 0.12
LIFESPAN = 20
T_SINK = 70.0  # DH Supply Temperature
T_RETURN = 30  # DH Return Temperature
T_COOLING = 5  # DC Supply Temperature

# --- ENERGY DEMAND ---
# CHANGE THIS TO "Amsterdam" OR "Zurich" TO SWITCH THE ENTIRE MODEL
SELECTED_CITY = "Zurich"

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
    "TES": True
}

# 2. Load Electricity Prices
df_prices = pd.read_excel(PRICE_DATA_PATH)
# We convert EUR/MWh to EUR/kWh if your model uses kWh for energy (divide by 1000)
elec_prices_kwh = df_prices[CITY_CONFIG[SELECTED_CITY]["elec_price_col"]].values / 1000

# --- MARKET PRICES ---
FUEL_PRICES = {"biomass": 0.05, "gas": 0.056}  # Euro/kWh
ELEC_REVENUE = 0.10  # Selling price for CHP electricity
DYNAMIC_ELEC_PRICES = elec_prices_kwh

# --- DATA GENERATION (Ambient Temperatures) ---
# Here we would later load Zurich/Amsterdam Excel/CSV files
monthly_temps = {
    1: 4, 2: 2, 3: 5, 4: 7, 5: 12, 6: 14,
    7: 17, 8: 18, 9: 15, 10: 11, 11: 7, 12: 4
}

# Create a full year time range for 2025
time_index = pd.date_range(start='2025-01-01', periods=8760, freq='h')

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
    dT = T_k - np.array(T_s_vec)
    # The Regression Formula from (https://doi.org/10.1016/j.rser.2020.110646) for R717 refrigerant - 1) and reversible machines basic thermodynamics
    cop = 0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684 - 1
    return np.maximum(cop, 0.1).tolist()


# --- EXPORTED VARIABLES ---
ANNUITY_FACTOR = _calculate_annuity_factor(INTEREST_RATE, LIFESPAN)
COP_VEC = _calculate_heating_cop(T_source_hourly, T_SINK)
COP_COOL_VEC = _calculate_cooling_cop(T_COOLING, T_source_hourly)



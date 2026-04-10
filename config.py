import numpy as np

# --- GLOBAL SETTINGS (Subject to change) ---
INTEREST_RATE = 0.12
LIFESPAN = 20
T_SINK = 75.0  # DH Supply Temperature

# --- ENERGY DEMAND ---
# CHANGE THIS TO "Amsterdam" OR "Zurich" TO SWITCH THE ENTIRE MODEL
SELECTED_CITY = "Zurich"

# File paths
INPUT_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Final_Network_Demand_MWh.xlsx'

# Mapping dictionary to handle the column names dynamically
CITY_CONFIG = {
    "Zurich": {
        "heat_col": "Zurich_Total_Heating_MWh",
        "cool_col": "Zurich_Total_Cooling_MWh"
    },
    "Amsterdam": {
        "heat_col": "Amsterdam_Total_Heating_MWh",
        "cool_col": "Amsterdam_Total_Cooling_MWh"
    }
}

# --- MARKET PRICES ---
FUEL_PRICES = {"biomass": 0.05, "gas": 0.12}  # Euro/kWh
ELEC_REVENUE = 0.10  # Selling price for CHP electricity
ELEC_PRICE = 0.2     # Buying price for Heat Pump electricity

# --- DATA GENERATION (Ambient Temperatures) ---
# Here we would later load Zurich/Amsterdam Excel/CSV files
T_source_hourly = 20 + 10 * np.sin(np.linspace(0, 2 * np.pi, 8760))

# --- MATH FUNCTIONS ---
def _calculate_annuity_factor(i, n):
    if i == 0: return 1 / n
    return (i * (1 + i)**n) / ((1 + i)**n - 1)

def _calculate_regression_cop(T_s_vec, T_k):
    dT = T_k - np.array(T_s_vec)
    # The Regression Formula from (https://doi.org/10.1016/j.rser.2020.110646) for R717 refrigerant
    cop = 0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684
    return np.maximum(cop, 1.0).tolist()

# --- EXPORTED VARIABLES ---
ANNUITY_FACTOR = _calculate_annuity_factor(INTEREST_RATE, LIFESPAN)
COP_VEC = _calculate_regression_cop(T_source_hourly, T_SINK)
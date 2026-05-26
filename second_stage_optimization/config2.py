import numpy as np
import pandas as pd

# =============================================================================
# 1. FIXED SYSTEM FOOTPRINT (HARD COPIED FROM STAGE 1 DETERMINISTIC RUN)
# =============================================================================
INSTALLED_TECH = {
    "BiomassBoiler": {
        "P_cap": 0,       # Paste your Stage 1 optimal kW output here
        "capex_per_kw": 350,    # Euro/kW
        "opex_per_kw": 7        # Euro/kW/year
    },
    "CHP": {
        "P_cap": 0,       # Paste your Stage 1 optimal kW_el output here
        "capex_per_kw": 3000,   # Euro/kW_el
        "opex_per_kw": 60       # Euro/kW_el/year
    },
    "LargeScaleHeatPump": {
        "P_cap": 805000.00,       # Paste your Stage 1 optimal kW_th output here
        "capex_per_kw": 1200,   # Euro/kW_th
        "opex_per_kw": 24       # Euro/kW_th/year
    },
    "TES": {
        "E_cap": 2006884.00,       # Paste your Stage 1 optimal kWh output here
        "capex_per_kwh": 12,    # Euro/kWh
        "opex_per_kwh": 0.5     # Euro/kWh/year
    }
}

# =============================================================================
# 2. GLOBAL SETTINGS (MATCHING STAGE 1 FINANCIAL STRUCTURES)
# =============================================================================
INTEREST_RATE = 0.12
LIFESPAN = 20
T_SINK = 65.0

def _calculate_annuity_factor(i, n):
    if i == 0: return 1 / n
    return (i * (1 + i)**n) / ((1 + i)**n - 1)

ANNUITY_FACTOR = _calculate_annuity_factor(INTEREST_RATE, LIFESPAN)

# Market Variable Baselines
FUEL_PRICES = {"biomass": 0.05, "gas": 0.056}  # Euro/kWh
ELEC_REVENUE = 0.10                             # Base market price for CHP sales

# =============================================================================
# 3. HIGH-RESOLUTION TIMESTEP DATA EXPANSION (8760 -> 35040)
# =============================================================================
SELECTED_CITY = "Zurich"
DEMAND_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Final_Network_Demand_MWh.xlsx'
PRICE_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/DAM_Prices_2025_Consolidated.xlsx'

CITY_CONFIG = {
    "Zurich": {
        "heat_col": "Zurich_Total_Heating_MWh",
        "cool_col": "Zurich_Total_Cooling_MWh",
        "elec_price_col": "Swiss_DAM_Price_2025"
    },
    "Amsterdam": {
        "heat_col": "Amsterdam_Total_Heating_MWh",
        "cool_col": "Amsterdam_Total_Cooling_MWh",
        "elec_price_col": "Dutch_DAM_Price_2025"
    }
}

# --- 1. LOAD DEMAND DATA FROM EXCEL & SCALE TO 15-MIN QUARTERS ---
# Using read_excel to handle your original .xlsx files properly
df_demand = pd.read_excel(DEMAND_DATA_PATH)
selected_col_heat = CITY_CONFIG[SELECTED_CITY]["heat_col"]
selected_col_cool = CITY_CONFIG[SELECTED_CITY]["cool_col"]

# First, convert MWh to hourly kWh baselines (extensive properties)
heat_kwh_hourly = (df_demand[selected_col_heat] * 1000).tolist()
cool_kwh_hourly = (df_demand[selected_col_cool] * 1000).tolist()

# 15-Minute Demand Expansion: Divide by 4 for each quarter-hour block to find true ENERGY (kWh)
HEAT_DEMAND_15MIN = [hourly_val / 4 for hourly_val in heat_kwh_hourly for _ in range(4)]
COOLING_DEMAND_15MIN = [hourly_val / 4 for hourly_val in cool_kwh_hourly for _ in range(4)]

# Calculate the true peak thermal power rate (kW) for your TES constraint structures
# (Energy in 15 mins * 4 quarters/hour = Peak instantaneous power rate in kW)
PEAK_DEMAND_KW = max(HEAT_DEMAND_15MIN) * 4

# --- 2. TEMPERATURE DATA & HIGH-RESOLUTION COP VECTORS ---
# Create a high-resolution 15-minute time range for the full year 2025 (8760 hours * 4 quarters = 35040 periods)
time_index_15min = pd.date_range(start='2025-01-01', periods=35040, freq='15min')

monthly_temps = {
    1: 4, 2: 2, 3: 5, 4: 7, 5: 12, 6: 14,
    7: 17, 8: 18, 9: 15, 10: 11, 11: 7, 12: 4
}

# Map the monthly averages directly to every 15-minute interval across the year
T_source_15min = np.array([monthly_temps[dt.month] for dt in time_index_15min])

def _calculate_heating_cop(T_s_vec, T_k):
    dT = T_k - np.array(T_s_vec)
    # The Regression Formula from R717 refrigerant performance data
    cop = 0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684
    return np.maximum(cop, 1.0).tolist()

def _calculate_cooling_cop(T_s_vec, T_k):
    dT = T_k - np.array(T_s_vec)
    # The Regression Formula from R717 refrigerant performance data - 1
    cop = (0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684) - 1
    return np.maximum(cop, 0.1).tolist()

# Compute the high-resolution 15-minute COP vectors natively from the 15-min temperature array
COP_VEC_15MIN = _calculate_heating_cop(T_source_15min, T_SINK)
COP_COOL_VEC_15MIN = _calculate_cooling_cop(T_source_15min, T_SINK)

# --- LOAD AND STRETCH BASE ELECTRICITY PRICES ---
df_prices = pd.read_excel(PRICE_DATA_PATH)
elec_prices_kwh_hourly = df_prices[CITY_CONFIG[SELECTED_CITY]["elec_price_col"]].values / 1000
DYNAMIC_ELEC_PRICES_15MIN = [val for val in elec_prices_kwh_hourly for _ in range(4)]


# --- BALANCING MARKET SCENARIO PATHS ---
# Automatically switch paths based on the selected city
if SELECTED_CITY == "Zurich":
    BALANCING_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/Representative_CH_Price_Scenarios.xlsx'
else:
    BALANCING_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/Representative_NL_Price_Scenarios.xlsx'

# 1. Load the Probabilities dynamically from the selected file
df_probs = pd.read_excel(BALANCING_DATA_PATH, sheet_name='Probabilities')

# Map Scenario names like 'Scenario 1' to 'S1' to match your column headers
df_probs['Short_Name'] = df_probs['Scenario'].str.replace('Scenario ', 'S')
PROBABILITY = dict(zip(df_probs['Short_Name'], df_probs['Probability']))
SCENARIOS = list(PROBABILITY.keys())  # Generates ['S1', 'S2', 'S3', 'S4', 'S5']

# 2. Load the 15-minute price series (35,040 rows)
df_bal_prices = pd.read_excel(BALANCING_DATA_PATH, sheet_name='Price_Data')

# Parse prices for both upward and downward regulation, converting EUR/MWh to EUR/kWh (divide by 1000)
BAL_PRICE_UP = {}
BAL_PRICE_DOWN = {}

for s in SCENARIOS:
    BAL_PRICE_UP[s] = (df_bal_prices[f"{s}_Balancing_Up"] / 1000).tolist()
    BAL_PRICE_DOWN[s] = (df_bal_prices[f"{s}_Balancing_Down"] / 1000).tolist()
import json
import pandas as pd
import numpy as np
import os

# =============================================================================
# 1. RESULTS OF FIRST OPTIMIZATION
# =============================================================================

json_input_path = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/first_stage_optimization/stage1_optimal_capacities.json"
try:
    with open(json_input_path, 'r') as f:
        stage1_caps = json.load(f)
except FileNotFoundError:
    print(f"CRITICAL ERROR: {json_input_path} not found. Did you run Stage 1 first?")
    stage1_caps = {"BiomassBoiler": 0.0, "CHP": 0.0, "LargeScaleHeatPump": 0.0, "TES": 0.0}

# DYNAMICALLY GENERATE THE FIXED FOOTPRINT
INSTALLED_TECH = {
    "BiomassBoiler": {
        "P_cap": stage1_caps.get("BiomassBoiler", 0.0),
        "capex_per_kw": 0,
        "opex_per_kw": 7
    },
    "CHP": {
        "P_cap": stage1_caps.get("CHP", 0.0),
        "capex_per_kw": 0,
        "opex_per_kw": 60
    },
    "LargeScaleHeatPump": {
        "P_cap": stage1_caps.get("LargeScaleHeatPump", 0.0),
        "capex_per_kw": 1700,
        "opex_per_kw": 34
    },
    "TES": {
        "E_cap": stage1_caps.get("TES", 0.0),
        "capex_per_kwh": 8,
        "opex_per_kwh": 0
    }
}

# =============================================================================
# 2. GLOBAL SETTINGS (MATCHING STAGE 1 FINANCIAL STRUCTURES)
# =============================================================================
INTEREST_RATE = 0.12
LIFESPAN = 20
T_SINK = 70.0
T_RETURN = 30
T_COOLING = 6

def _calculate_annuity_factor(i, n):
    if i == 0: return 1 / n
    return (i * (1 + i)**n) / ((1 + i)**n - 1)

ANNUITY_FACTOR = _calculate_annuity_factor(INTEREST_RATE, LIFESPAN)

# =============================================================================
# 3. BASE FUEL PRICING (BIOMASS & GAS)
# =============================================================================
BIOMASS_PRICE = 0.05  # Euro/kWh
ELEC_REVENUE = 0.10   # Base market price for CHP sales (Euro/kWh)

# GAS PRICE SETUP
# 1. Read the CSV file containing the carbon costs (EU ETS Emissions CO2 Costs)
carbon_csv_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/eu_ets_2025.csv'
carbon_df = pd.read_csv(carbon_csv_path)

# Ensure the date column is parsed as datetime objects and sorted sequentially
carbon_df['date'] = pd.to_datetime(carbon_df['date'])
carbon_df.set_index('date', inplace=True)

# Generate an explicit, complete 365-day calendar target index for 2025
full_year_days = pd.date_range(start='2025-01-01', end='2025-12-31', freq='D')
carbon_df = carbon_df.reindex(full_year_days)

# 3. Apply your custom handling for missing start/end boundary values:
carbon_df.loc['2025-01-01'] = carbon_df.loc['2025-01-02']  # Backward-fill
carbon_df.loc['2025-12-31'] = carbon_df.loc['2025-12-30']  # Forward-fill

# 2. Extract the clean sequence of daily carbon prices (365 values)
daily_carbon_prices = carbon_df['price'].values

# 3. Define the conversion factor (EUR/tonne of CO2 to EUR/kWh of natural gas)
conversion_factor = 0.000201

# 4. Baseline monthly gas prices in EUR/kWh
monthly_gas_prices_base = {
    1: 0.045058 * 1.15, 2: 0.048140 * 1.15, 3: 0.047140 * 1.15,
    4: 0.041960 * 1.15, 5: 0.035622 * 1.15, 6: 0.035340 * 1.15,
    7: 0.036697 * 1.15, 8: 0.033847 * 1.15, 9: 0.032869 * 1.15,
    10: 0.032343 * 1.15, 11: 0.031946 * 1.15, 12: 0.030884 * 1.15,
}

# 5. Initialize the flat 8760 hours array
gas_input_prices_hourly = np.zeros(8760)

# 6. Map base prices AND day-by-day carbon costs directly to each hour
for day in range(365):
    hour_start = day * 24
    hour_end = hour_start + 24

    if day < 31: month = 1
    elif day < 59: month = 2
    elif day < 90: month = 3
    elif day < 120: month = 4
    elif day < 151: month = 5
    elif day < 181: month = 6
    elif day < 212: month = 7
    elif day < 243: month = 8
    elif day < 273: month = 9
    elif day < 304: month = 10
    elif day < 334: month = 11
    else: month = 12

    base_price = monthly_gas_prices_base[month]
    carbon_price_today = daily_carbon_prices[day]
    gas_input_prices_hourly[hour_start:hour_end] = base_price + (carbon_price_today * conversion_factor)

# Duplicate every single hourly gas price 4 times sequentially for 15-minute blocks
gas_input_prices_15min = np.array([val for val in gas_input_prices_hourly for _ in range(4)])

FUEL_PRICES = {
    "biomass": BIOMASS_PRICE,
    "gas": gas_input_prices_15min
}

# =============================================================================
# 4. HIGH-RESOLUTION TIMESTEP DATA EXPANSION (8760 -> 35040)
# =============================================================================
SELECTED_CITY = "Zurich"
DEMAND_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Final_Network_Demand_MWh.xlsx'

CITY_CONFIG = {
    "Zurich": {
        "heat_col": "Zurich_Total_Heating_MWh",
        "cool_col": "Zurich_Total_Cooling_MWh",
    },
    "Amsterdam": {
        "heat_col": "Amsterdam_Total_Heating_MWh",
        "cool_col": "Amsterdam_Total_Cooling_MWh",
    }
}

# --- A. LOAD DEMAND DATA FROM EXCEL & SCALE TO 15-MIN QUARTERS ---
df_demand = pd.read_excel(DEMAND_DATA_PATH)
selected_col_heat = CITY_CONFIG[SELECTED_CITY]["heat_col"]
selected_col_cool = CITY_CONFIG[SELECTED_CITY]["cool_col"]

# Convert MWh to hourly kWh baselines
heat_kwh_hourly = (df_demand[selected_col_heat] * 1000).tolist()
cool_kwh_hourly = (df_demand[selected_col_cool] * 1000).tolist()

# 15-Minute Demand Expansion: Divide by 4 for true ENERGY (kWh) per quarter
HEAT_DEMAND_15MIN = [hourly_val / 4 for hourly_val in heat_kwh_hourly for _ in range(4)]
COOLING_DEMAND_15MIN = [hourly_val / 4 for hourly_val in cool_kwh_hourly for _ in range(4)]

# Peak instantaneous power rate in kW (for TES constraints)
PEAK_DEMAND_KW = max(HEAT_DEMAND_15MIN) * 4

# --- B. TEMPERATURE DATA & HIGH-RESOLUTION COP VECTORS ---
time_index_15min = pd.date_range(start='2025-01-01', periods=35040, freq='15min')

monthly_temps = {
    1: 4, 2: 2, 3: 5, 4: 7, 5: 12, 6: 14,
    7: 17, 8: 18, 9: 15, 10: 11, 11: 7, 12: 4
}
T_source_15min = np.array([monthly_temps[dt.month] for dt in time_index_15min])

def _calculate_heating_cop(T_s_vec, T_k):
    dT = T_k - np.array(T_s_vec)
    cop = 0.0014515 * (dT ** 2) - 0.23104 * dT + 11.684
    return np.maximum(cop, 1.0).tolist()

def _calculate_cooling_cop(T_s_vec, T_k):
    cop_cool = 4.70 * (1.0 - 0.0045 * (np.array(T_s_vec) - T_k))
    return np.maximum(cop_cool, 0.1).tolist()

COP_VEC_15MIN = _calculate_heating_cop(T_source_15min, T_SINK)
COP_COOL_VEC_15MIN = _calculate_cooling_cop(T_source_15min, T_COOLING)


# =============================================================================
# 5. MULTI-SCENARIO PROBABILISTIC MARKET INJECTIONS (DAM & BALANCING)
# =============================================================================

# --- A. BALANCING MARKET SCENARIO PATHS & LOADING ---
if SELECTED_CITY == "Zurich":
    BALANCING_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Zurich/Representative_CH_Price_Scenarios.xlsx'
else:
    BALANCING_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Balancing Energy Prices Amsterdam/Representative_NL_Price_Scenarios.xlsx'

# Load the Balancing Probabilities dynamically
df_probs_bal = pd.read_excel(BALANCING_DATA_PATH, sheet_name='Probabilities')
df_probs_bal['Short_Name'] = df_probs_bal['Scenario'].str.replace('Scenario ', 'S')

PROBABILITY_BAL = dict(zip(df_probs_bal['Short_Name'], df_probs_bal['Probability']))
SCENARIOS_BAL = list(PROBABILITY_BAL.keys())  # Generates ['S1', 'S2', 'S3', 'S4', 'S5']

# Load the 15-minute Balancing price series
df_bal_prices = pd.read_excel(BALANCING_DATA_PATH, sheet_name='Price_Data')
BAL_PRICE_UP = {}
BAL_PRICE_DOWN = {}

for s in SCENARIOS_BAL:
    BAL_PRICE_UP[s] = (df_bal_prices[f"{s}_Balancing_Up"] / 1000).tolist()
    BAL_PRICE_DOWN[s] = (df_bal_prices[f"{s}_Balancing_Down"] / 1000).tolist()


# --- B. DAY-AHEAD MARKET (DAM) SCENARIO PATHS & LOADING ---
if SELECTED_CITY == "Zurich":
    DAM_SCENARIO_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Zurich/Representative_DAM_Price_Scenarios_CH_Expanded.xlsx'
else:
    DAM_SCENARIO_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Day Ahead Energy Prices Amsterdam/Representative_DAM_Price_Scenarios_NL_Expanded.xlsx'

# Load the Day-Ahead Probabilities dynamically
df_probs_da = pd.read_excel(DAM_SCENARIO_DATA_PATH, sheet_name='Probabilities')
df_probs_da['Short_Name'] = df_probs_da['Scenario'].str.replace('Scenario ', 'S')

PROBABILITY_DA = dict(zip(df_probs_da['Short_Name'], df_probs_da['Probability']))
SCENARIOS_DA = list(PROBABILITY_DA.keys())  # Generates ['S1', 'S2', 'S3', 'S4', 'S5']

# Load the 15-minute Day-Ahead price series (35,040 rows)
df_dam_prices = pd.read_excel(DAM_SCENARIO_DATA_PATH, sheet_name='Price_Data')
DYNAMIC_ELEC_PRICES_15MIN_SCENARIO = {}

for s in SCENARIOS_DA:
    # Convert EUR/MWh to EUR/kWh
    DYNAMIC_ELEC_PRICES_15MIN_SCENARIO[s] = (df_dam_prices[f"{s}_DayAhead_Price"] / 1000).tolist()

print("\nConfig loaded successfully. Ready for joint stochastic optimization.")
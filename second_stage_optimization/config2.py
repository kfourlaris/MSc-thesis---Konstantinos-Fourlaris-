import numpy as np
import pandas as pd
import json

# =============================================================================
# 1. Results of first optimization
# =============================================================================

json_input_path = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/first_stage_optimization/stage1_optimal_capacities.json"
try:
    with open(json_input_path, 'r') as f:
        stage1_caps = json.load(f)
except FileNotFoundError:
    print(f"CRITICAL ERROR: {json_input_path} not found. Did you run Stage 1 first?")
    stage1_caps = {"BiomassBoiler": 0.0, "CHP": 0.0, "LargeScaleHeatPump": 0.0, "TES": 0.0}

# 2. DYNAMICALLY GENERATE THE FIXED FOOTPRINT
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

# Market Variable Baselines
#BIOMASS PRICE
BIOMASS_PRICE = 0.05  # Euro/kWh

#GAS PRICE
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
# For Jan 1st (2025-01-01), backward-fill from Jan 2nd
carbon_df.loc['2025-01-01'] = carbon_df.loc['2025-01-02']
# For Dec 31st (2025-12-31), forward-fill from Dec 30th
carbon_df.loc['2025-12-31'] = carbon_df.loc['2025-12-30']

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
# Loop through all 365 days of the year, converting each day to its 24 hourly values
for day in range(365):
    hour_start = day * 24
    hour_end = hour_start + 24

    # Identify which month this specific day falls under (for Non-Leap Years)
    # Day index ranges: Jan (0-30), Feb (31-58), Mar (59-89), etc.
    if day < 31:
        month = 1  # January
    elif day < 59:
        month = 2  # February
    elif day < 90:
        month = 3  # March
    elif day < 120:
        month = 4  # April
    elif day < 151:
        month = 5  # May
    elif day < 181:
        month = 6  # June
    elif day < 212:
        month = 7  # July
    elif day < 243:
        month = 8  # August
    elif day < 273:
        month = 9  # September
    elif day < 304:
        month = 10  # October
    elif day < 334:
        month = 11  # November
    else:
        month = 12  # December

    # Extract the specific base price for this month
    base_price = monthly_gas_prices_base[month]

    # Extract the exact carbon price for this specific day
    carbon_price_today = daily_carbon_prices[day]

    # Apply the equation per hour block: base_price + (daily_carbon * conversion_factor)
    gas_input_prices_hourly[hour_start:hour_end] = base_price + (carbon_price_today * conversion_factor)

# Duplicate every single hourly gas price 4 times sequentially for 15-minute blocks
gas_input_prices_15min = np.array([val for val in gas_input_prices_hourly for _ in range(4)])

print(f"Hourly gas array size generated: {len(gas_input_prices_hourly)}")
print(f"Expanded 15-min gas array size for Stage 2: {len(gas_input_prices_15min)}")

# Verify the first two hours (8 quarter-hour steps) match
print("First 8 15-minute gas prices:")
print(gas_input_prices_15min[:8])

FUEL_PRICES = {
    "biomass": BIOMASS_PRICE,
    "gas": gas_input_prices_15min
}
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

# Compute the high-resolution 15-minute COP vectors natively from the 15-min temperature array
COP_VEC_15MIN = _calculate_heating_cop(T_source_15min, T_SINK)
COP_COOL_VEC_15MIN = _calculate_cooling_cop(T_source_15min, T_COOLING)

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
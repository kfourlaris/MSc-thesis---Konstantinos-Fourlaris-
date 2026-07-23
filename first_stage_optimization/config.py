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
SELECTED_CITY = "Zurich"

# File paths
DEMAND_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Final_Network_Demand_MWh.xlsx'
PRICE_DATA_PATH = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/DAM_Prices_2025_Consolidated.xlsx'

# Mapping dictionary to handle the column names dynamically
CITY_CONFIG = {
    "Zurich": {
        "heat_col": "Zurich_Total_Heating_MWh",
        "cool_col": "Zurich_Total_Cooling_MWh",
        "elec_price_col": "Swiss_DAM_Price_2025"  # Actual 2025 price profile for Switzerland
    },
    "Amsterdam": {
        "heat_col": "Amsterdam_Total_Heating_MWh",
        "cool_col": "Amsterdam_Total_Cooling_MWh",
        "elec_price_col": "Dutch_DAM_Price_2025" # Actual 2025 price profile for Netherlands
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
# We convert EUR/MWh to EUR/kWh since the model uses kWh for energy (divide by 1000)
elec_prices_kwh = df_prices[CITY_CONFIG[SELECTED_CITY]["elec_price_col"]].values / 1000

# --- MARKET PRICES ---
# Create a full year time range for 2025
time_index = pd.date_range(start='2025-01-01', periods=8760, freq='h')

#BIOMASS PRICE
BIOMASS_PRICE = 0.05  # Euro/kWh (https://doi.org/10.1016/j.heliyon.2024.e33322)

#GAS PRICE
# 1. Read the CSV file containing the carbon costs (EU ETS Emissions CO2 Costs) (Source = Python)
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
conversion_factor = 0.000201 #Source = (https://www.volker-quaschning.de/datserv/CO2-spez/index_e.php)

# 4. Baseline monthly gas prices in EUR/kWh (Source = https://www.protergia.gr/en/home/natural-gas/ttf-prices-per-month/)
# Multiplication by 1.15 is about modeling any transportation and contract cost for delivering natural gas to the CHP power plant
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

    # Identify which month this specific day falls under (for Non-Leap Year 2025)
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

print(gas_input_prices_hourly)
print(len(gas_input_prices_hourly))
print("Printing the first 480 hourly gas prices (including dynamic carbon premium):")
with np.printoptions(threshold=np.inf):
    print(gas_input_prices_hourly[:480])

FUEL_PRICES = {
    "biomass": BIOMASS_PRICE,
    "gas": gas_input_prices_hourly
}

ELEC_REVENUE = 0.10  # Selling price for CHP electricity
DYNAMIC_ELEC_PRICES = elec_prices_kwh

# --- DATA GENERATION (Water Temperatures (Lake/river)) ---
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


# =========================================================================
# --- LIFE CYCLE ASSESSMENT (LCA) RAW EMISSION FACTORS & CONVERSIONS ---
# =========================================================================

# 1. OPERATIONAL EMISSIONS
# -------------------------------------------------------------------------
# Values map directly to Switzerland (CH) and the Netherlands (NL) EcoInvent dataset
REGIONAL_LCA_DATA = {
    "Zurich": {
        "raw_em_elec_kg_kwh": 0.0194,   # market for electricity high voltage CH (kg CO2-Eq / KWh)
        "raw_em_gas_kg_m3": 0.58,       # market for natural gas high pressure CH TRANSPORTATION ONLY (kg CO2-Eq / m³)
        "raw_em_biomass_kg_kg": 0.0488  # market for wood chips CH (kg CO2-Eq / kg)
    },
    "Amsterdam": {
        "raw_em_elec_kg_kwh": 0.427,    # market for electricity high voltage NL (kg CO2-Eq / KWh)
        "raw_em_gas_kg_m3": 0.451,      # market for natural gas high pressure NL TRANSPORTATION ONLY (kg CO2-Eq / m³)
        "raw_em_biomass_kg_kg": 0.0438  # market for wood chips (kg CO2-Eq / kg)
    }
}

# 2. PHYSICAL CONVERSION PARAMETERS
# -------------------------------------------------------------------------
GAS_LHV_KWH_M3 = 10.55         # Lower Heating Value (LHV) of Natural Gas (~10.55 kWh/m³) source: Energy Statistics manual IEA
BIOMASS_LHV_KWH_KG = 3.5       # Lower Heating Value (LHV) of usable wet wood chips (~3.5 kWh/kg) source: Typical calorific values of fuels
GAS_BURNING_KG_PER_KWH = 0.2   # Emissions from burning the natural gas 0.2 kg of CO2 per KWh source: https://www.volker-quaschning.de/datserv/CO2-spez/index_e.php

# 3. DYNAMIC REGIONAL SELECTION
# -------------------------------------------------------------------------
# Automatically determines the active region based on SELECTED_CITY
ACTIVE_REGION = "Zurich" if SELECTED_CITY == "Zurich" else "Amsterdam"

# Extracting the raw values based on the active region
_raw_elec = REGIONAL_LCA_DATA[ACTIVE_REGION]["raw_em_elec_kg_kwh"]
_raw_gas = REGIONAL_LCA_DATA[ACTIVE_REGION]["raw_em_gas_kg_m3"]
_raw_biomass = REGIONAL_LCA_DATA[ACTIVE_REGION]["raw_em_biomass_kg_kg"]

# 4. STANDARDIZED CONVERSIONS (Calculated automatically in Tons CO2-Eq / kWh)
# -------------------------------------------------------------------------
# Convert kg to tons (/ 1000)

# Electricity:
EM_ELEC_Ton_KWH = _raw_elec / 1000

# Natural Gas:
EM_GAS_Ton_KWH = ((_raw_gas / GAS_LHV_KWH_M3) / 1000) + (GAS_BURNING_KG_PER_KWH / 1000)

# Biomass:
EM_BIOMASS_Ton_KWH = (_raw_biomass / BIOMASS_LHV_KWH_KG) / 1000


# 5. EMBEDDED INFRASTRUCTURE EMISSIONS (Common across locations)
# -------------------------------------------------------------------------
# EcoInvent metrics converted to Tons CO2-Eq per KW
_EM_BOILER_PLANT_TON_KW = (55.8 / 1000) / LIFESPAN  # market for furnace wood chips with silo 5000 KW -> 2.79 * 10^5 kg co2 per 5000 KW
_EM_CHP_PLANT_TON_KW = (54.4 / 1000) / LIFESPAN     # heat and power co-generation unit construction, 1MW electrical, components for heat only_Europe -> 5.44 * 10^4 kg co2 per 1000 KW
_EM_TES_TON_M3 = (0.587 / 1000) / LIFESPAN          # excavation, hydraulic digger -> 0.587 kg co2 per m^3
_EM_HP_TON_KG = 2.53 / 1000                         # market for industrial machine heavy unspecified -> 2.53 kg co2 per kg of machinery

# HP and Chiller kilos to KW according to MAN brochure (50000 KW equal to 20000 kg):
KG_PER_KW_MACHINERY = 0.4 # 1 KG OF MACHINERY EQUAL TO 0.4 KW of power
_EM_HP_TON_KW = (_EM_HP_TON_KG * KG_PER_KW_MACHINERY) / LIFESPAN

# 6. EXPORT PACK
# -------------------------------------------------------------------------
TON_CO2_EMISSION_FACTORS = {
    # Operational vectors (per kWh)
    "electricity": EM_ELEC_Ton_KWH,
    "gas": EM_GAS_Ton_KWH,
    "biomass": EM_BIOMASS_Ton_KWH,

    # Capital assets footprint vectors (per kW or per m³)
    "biomass_embedded": _EM_BOILER_PLANT_TON_KW,
    "chp_embedded": _EM_CHP_PLANT_TON_KW,
    "lshp_embedded": _EM_HP_TON_KW,
    "tes_embedded": _EM_TES_TON_M3,
}

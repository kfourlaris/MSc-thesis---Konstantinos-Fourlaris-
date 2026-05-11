import pandas as pd
import matplotlib.pyplot as plt
import gurobipy as gp
from gurobipy import GRB


x = pd.DataFrame({'NAME':['FOURLARIS']})
print(x)

# Import the classes
import config
from CHP import CHP
from BiomassBoiler import BiomassBoiler
from LSHP import LargeScaleHeatPump
from TES import PitThermalEnergyStorage

# --- PRE-MODELING CHECK ---
# Verify the data is flowing
print(f"Using CRF: {config.ANNUITY_FACTOR:.4f}")
print(f"Average COP: {sum(config.COP_VEC)/8760:.2f}")

# --- STEP 0: LOAD DYNAMIC DEMAND DATA ---
# Load the final MWh file
df_demand = pd.read_excel(config.DEMAND_DATA_PATH)
df_prices = pd.read_excel(config.PRICE_DATA_PATH)

# Get the correct column name from config mapping
selected_col_heat = config.CITY_CONFIG[config.SELECTED_CITY]["heat_col"]
selected_col_cool = config.CITY_CONFIG[config.SELECTED_CITY]["cool_col"]
selected_elec_col = config.CITY_CONFIG[config.SELECTED_CITY]["elec_price_col"]

# Extract the hourly values as a list (8760 values)
# Note: Since your model uses kW, and the file is in MWh,
# 1 MWh in one hour = 1000 kW power.
HEAT_DEMAND_VEC = (df_demand[selected_col_heat] * 1000).tolist()
COOLING_DEMAND_VEC = (df_demand[selected_col_cool] * 1000).tolist()
peak_demand_kw = max(HEAT_DEMAND_VEC)
ELEC_PRICE_VEC = (df_prices[selected_elec_col] / 1000).tolist()

# --- STEP 1: INITIALIZATION ---
model = gp.Model("District_Energy_Optimization")
timesteps = range(8760)  # Hourly resolution for one year
model.setParam('MIPGap', 0.1) #for making it run faster

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
boiler = BiomassBoiler("BB_Zurich")
chp = CHP("CHP_Zurich")
hp = LargeScaleHeatPump("HP_Zurich")
tes = PitThermalEnergyStorage("TES_Zurich")
technologies = [boiler, chp, hp]

# Update the constraints loop
for tech in technologies:
    tech.add_variables(model, timesteps)
    if isinstance(tech, LargeScaleHeatPump):
        tech.add_constraints(model, timesteps, config.COP_VEC) # Pass cop_vector here
    else:
        tech.add_constraints(model, timesteps)
tes.add_variables(model, timesteps)
tes.add_constraints(model, timesteps, hp_instance=hp, peak_demand_kw=peak_demand_kw)

# --- STEP 3: GLOBAL ENERGY BALANCE ---
# Heat production from all units must meet demand every hour
model.addConstrs(
    (gp.quicksum(tech.V_heat[t] for tech in technologies) + tes.V_disch[t] - tes.U_charge[t] == HEAT_DEMAND_VEC[t]
     for t in timesteps),
    name="Global_Heat_Demand_Balance"
)
model.addConstrs(
    (gp.quicksum(tech.V_cool[t] for tech in technologies if hasattr(tech, 'V_cool')) == COOLING_DEMAND_VEC[t]
     for t in timesteps),
    name="Global_Cooling_Demand_Balance"
)

# --- STEP 4: OBJECTIVE FUNCTION ---
# Minimize Total Annual Cost = Investment + OPEX + Fuel Costs - Electricity Revenue
annual_investment = gp.quicksum(
    tech.P_cap * (tech.capex_per_kw * config.ANNUITY_FACTOR + tech.opex_per_kw) for tech in technologies
) + (tes.E_cap * tes.capex_per_kwh * config.ANNUITY_FACTOR)

# Operational costs (X variables) summed over the year
fuel_costs = gp.quicksum(
    boiler.U_biomass[t] * config.FUEL_PRICES["biomass"] +
    chp.U_gas[t] * config.FUEL_PRICES["gas"] +
    hp.U_elec[t] * ELEC_PRICE_VEC[t]
    for t in timesteps
)

# Revenue from CHP electricity sales
elec_revenue = gp.quicksum(chp.V_elec[t] * config.ELEC_REVENUE for t in timesteps)

model.setObjective(annual_investment + fuel_costs - elec_revenue, GRB.MINIMIZE)

# --- STEP 5: OPTIMIZE & RESULTS ---
model.optimize()

if model.Status == GRB.OPTIMAL:
    print(f"Optimal Total Cost: {model.ObjVal} Euro")
    print(f"Installed Boiler Capacity: {boiler.P_cap.X} kW")
    print(f"Installed CHP Capacity: {chp.P_cap.X} kW")
    print(f"Installed HP Capacity: {hp.P_cap.X} kW")
    print (f"Installed TES Capacity: {tes.E_cap.X:.2f} kWh")

    # Existing print for Energy Capacity
    tes_energy_kwh = tes.E_cap.X
    print(f"Installed TES Capacity: {tes_energy_kwh:.2f} kWh")

    # --- NEW: VOLUME CALCULATION ---
    # Define your Delta T (DT).
    # Example: If using 65°C supply and 25°C return (4th Gen target), DT = 40.
    # The paper uses 60°C for their cavern.
    delta_t = config.T_SINK - config.T_RETURN  # Replace with your specific DT value

    # Constant for water: 1.162 Wh per kg per degree Celsius
    # Convert to kWh: 0.001162 kWh / (kg * °C)
    # Volume in m3 (assuming 1000kg/m3)
    tes_volume_m3 = tes_energy_kwh / (1.162 * delta_t)

    print(f"Required TES Volume: {tes_volume_m3:.2f} m³")

if model.Status == GRB.OPTIMAL:
    # 1. Extract results into arrays
    t_plot = range(8760)  # Plotting 8760 hours

    # Extract hourly production from each tech
    boiler_gen = [boiler.V_heat[t].X for t in t_plot]
    chp_gen = [chp.V_heat[t].X for t in t_plot]
    hp_gen = [hp.V_heat[t].X for t in t_plot]
    actual_demand = [HEAT_DEMAND_VEC[t] for t in t_plot]

    # 2. Create the Stacked Area Plot
    plt.figure(figsize=(12, 6))

    # Stack the technologies
    plt.stackplot(t_plot, boiler_gen, chp_gen, hp_gen,
                  labels=['Biomass Boiler', 'CHP Plant', 'HP Plant'],
                  colors=['#2ecc71', '#3498db', '#e74c3c'], alpha=0.8)

    # Overlay the total demand line
    plt.plot(t_plot, actual_demand, color='black', linestyle='--',
             linewidth=2, label='Total Heat Demand')

    # 3. Formatting
    plt.title(f'Hourly Heat Dispatch')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Heat Production / Demand (kW)')
    plt.legend(loc='upper right')
    plt.grid(axis='y', linestyle=':', alpha=0.6)

    plt.tight_layout()
    plt.show()

    # 1. Extract Storage Data
    # We use negative for charge to show it as a 'drain' on the system
    charge_vals = [-tes.U_charge[t].X for t in t_plot]
    disch_vals = [tes.V_disch[t].X for t in t_plot]
    soc_vals = [tes.E_state[t].X for t in t_plot]  # State of Charge (kWh)

    # 2. Create the Figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # --- Subplot 1: Charge/Discharge Activity ---
    ax1.fill_between(t_plot, disch_vals, label='Discharging (+)', color='orange', alpha=0.7)
    ax1.fill_between(t_plot, charge_vals, label='Charging (-)', color='navy', alpha=0.7)
    ax1.axhline(0, color='black', linewidth=1)
    ax1.set_ylabel('Power Flow (kW)')
    ax1.set_title(f'TES Operation: Charging vs. Discharging')
    ax1.legend(loc='upper right')
    ax1.grid(alpha=0.3)

    # --- Subplot 2: State of Charge (Energy Level) ---
    ax2.plot(t_plot, soc_vals, color='green', linewidth=1.5, label='Stored Energy')
    ax2.fill_between(t_plot, soc_vals, color='green', alpha=0.1)
    ax2.set_ylabel('Stored Energy (kWh)')
    ax2.set_xlabel('Hour of the Year')
    ax2.set_title('TES Energy Level (State of Charge)')
    ax2.legend(loc='upper right')
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.show()
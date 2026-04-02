import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from CRF import annuity_factor

x = pd.DataFrame({'NAME':['FOURLARIS']})
print(x)


import gurobipy as gp
from gurobipy import GRB
# Import your classes from your local file
from CHP import CHP
from BiomassBoiler import BiomassBoiler
from LSHP import LargeScaleHeatPump

# --- STEP 1: INITIALIZATION ---
model = gp.Model("District_Energy_Optimization")
timesteps = range(8760)  # Hourly resolution for one year [cite: 200]

# --- STEP 1: Define physical parameters ---
T_source_hourly = [293.16] * 2000 + [304.27] * 3000 + [263.15] * (8760-5000)
T_sink_K = 85 + 273.15  # Target DH supply temp (85°C) in Kelvin [cite: 149]
eta_sys = 0.5           # System efficiency (Carnot efficiency fraction) [cite: 237]

# --- STEP 2: Calculate the hourly COP ---
# Assume 'T_source_hourly' is your list of 8760 ambient water/air temps in Kelvin
# Based on the formula: COP = eta * (T_sink / (T_sink - T_source))
cop_vector = [eta_sys * (T_sink_K / (T_sink_K - T_s)) for T_s in T_source_hourly]


# Sample Input Data (Replace with your Zurich/Amsterdam datasets) [cite: 254]
heat_demand = [55000] * 3000 + [30000] * 3000 + [53000] * (8760 - 6000)  # Placeholder hourly D_h [cite: 254]
fuel_prices = {"biomass": 0.05, "gas": 0.12}  # Euro/kWh [cite: 254]
electricity_revenue = 0.10
elec_price = 0.2   # Euro/kWh

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
boiler = BiomassBoiler("BB_Zurich")
chp = CHP("CHP_Zurich")
hp = LargeScaleHeatPump("HP_Zurich")
technologies = [boiler, chp, hp]

# Update the constraints loop to handle the Heat Pump's unique cop_vector
for tech in technologies:
    tech.add_variables(model, timesteps)
    if isinstance(tech, LargeScaleHeatPump):
        tech.add_constraints(model, timesteps, cop_vector) # Pass cop_vector here
    else:
        tech.add_constraints(model, timesteps)

# --- STEP 3: GLOBAL ENERGY BALANCE ---
# Heat production from all units must meet demand every hour [cite: 232]
model.addConstrs(
    (gp.quicksum(tech.V_heat[t] for tech in technologies) == heat_demand[t]
     for t in timesteps),
    name="Heat_Demand_Balance"
)

# --- STEP 4: OBJECTIVE FUNCTION ---
# Minimize Total Annual Cost = Investment + Fuel Costs - Electricity Revenue [cite: 229]
annual_investment = gp.quicksum(
    tech.P_cap * (tech.capex_per_kw * annuity_factor + tech.opex_per_kw) for tech in technologies
)

# Operational costs (X variables) summed over the year [cite: 207]
fuel_costs = gp.quicksum(
    boiler.U_biomass[t] * fuel_prices["biomass"] +
    chp.U_gas[t] * fuel_prices["gas"] +
    hp.U_elec[t] * elec_price
    for t in timesteps
)

# Revenue from CHP electricity sales [cite: 34]
elec_revenue = gp.quicksum(chp.V_elec[t] * electricity_revenue for t in timesteps)

model.setObjective(annual_investment + fuel_costs - elec_revenue, GRB.MINIMIZE)

# --- STEP 5: OPTIMIZE & RESULTS ---
model.optimize()

if model.Status == GRB.OPTIMAL:
    print(f"Optimal Total Cost: {model.ObjVal} Euro")
    print(f"Installed Boiler Capacity: {boiler.P_cap.X} kW")
    print(f"Installed CHP Capacity: {chp.P_cap.X} kW")
    print(f"Installed HP Capacity: {hp.P_cap.X} kW")

if model.Status == GRB.OPTIMAL:
    # 1. Extract results into arrays
    t_plot = range(8760)  # Plotting 8760 hours

    # Extract hourly production from each tech
    boiler_gen = [boiler.V_heat[t].X for t in t_plot]
    chp_gen = [chp.V_heat[t].X for t in t_plot]
    hp_gen = [hp.V_heat[t].X for t in t_plot]
    actual_demand = [heat_demand[t] for t in t_plot]

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
    plt.title(f'Hourly Heat Dispatch - {boiler.name} & {chp.name}')
    plt.xlabel('Hour of the Year')
    plt.ylabel('Heat Production / Demand (kW)')
    plt.legend(loc='upper right')
    plt.grid(axis='y', linestyle=':', alpha=0.6)

    plt.tight_layout()
    plt.show()
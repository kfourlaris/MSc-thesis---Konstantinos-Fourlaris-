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

# --- PRE-MODELING CHECK ---
# Verify the data is flowing
print(f"Using CRF: {config.ANNUITY_FACTOR:.4f}")
print(f"Average COP: {sum(config.COP_VEC)/8760:.2f}")

# --- STEP 0: LOAD DYNAMIC DEMAND DATA ---
# Load the final MWh file
df_demand = pd.read_excel(config.INPUT_DATA_PATH)

# Get the correct column name from config mapping
selected_col = config.CITY_CONFIG[config.SELECTED_CITY]["heat_col"]

# Extract the hourly values as a list (8760 values)
# Note: Since your model uses kW, and the file is in MWh,
# 1 MWh in one hour = 1000 kW power.
HEAT_DEMAND_VEC = (df_demand[selected_col] * 1000).tolist()

# --- STEP 1: INITIALIZATION ---
model = gp.Model("District_Energy_Optimization")
timesteps = range(8760)  # Hourly resolution for one year

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
boiler = BiomassBoiler("BB_Zurich")
chp = CHP("CHP_Zurich")
hp = LargeScaleHeatPump("HP_Zurich")
technologies = [boiler, chp, hp]

# Update the constraints loop
for tech in technologies:
    tech.add_variables(model, timesteps)
    if isinstance(tech, LargeScaleHeatPump):
        tech.add_constraints(model, timesteps, config.COP_VEC) # Pass cop_vector here
    else:
        tech.add_constraints(model, timesteps)

# --- STEP 3: GLOBAL ENERGY BALANCE ---
# Heat production from all units must meet demand every hour
model.addConstrs(
    (gp.quicksum(tech.V_heat[t] for tech in technologies) == HEAT_DEMAND_VEC[t]
     for t in timesteps),
    name="Heat_Demand_Balance"
)

# --- STEP 4: OBJECTIVE FUNCTION ---
# Minimize Total Annual Cost = Investment + OPEX + Fuel Costs - Electricity Revenue
annual_investment = gp.quicksum(
    tech.P_cap * (tech.capex_per_kw * config.ANNUITY_FACTOR + tech.opex_per_kw) for tech in technologies
)

# Operational costs (X variables) summed over the year
fuel_costs = gp.quicksum(
    boiler.U_biomass[t] * config.FUEL_PRICES["biomass"] +
    chp.U_gas[t] * config.FUEL_PRICES["gas"] +
    hp.U_elec[t] * config.ELEC_PRICE
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
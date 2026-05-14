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
model.setParam('MIPGap', 0.02) #for making it run faster

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
all_techs = {
    "BiomassBoiler": BiomassBoiler("BB_Zurich"),
    "CHP": CHP("CHP_Zurich"),
    "LargeScaleHeatPump": LargeScaleHeatPump("HP_Zurich")
}

technologies = [obj for name, obj in all_techs.items() if config.TECH_SWITCHES.get(name, True)]

# 1. ADD ALL VARIABLES FIRST
for tech in technologies:
    tech.add_variables(model, timesteps)

tes_enabled = config.TECH_SWITCHES.get("TES", True)
if tes_enabled:
    tes = PitThermalEnergyStorage("TES_Zurich")
    tes.add_variables(model, timesteps) # Variables for TES added here

# 2. ADD CONSTRAINTS LATER
for tech in technologies:
    if isinstance(tech, LargeScaleHeatPump):
        tech.add_constraints(model, timesteps, config.COP_VEC, config.COP_COOL_VEC)
    else:
        tech.add_constraints(model, timesteps)

# 3. NOW ADD TES CONSTRAINTS (Variables for HP now exist!)
if tes_enabled:
    tes.add_constraints(model, timesteps, hp_instance=all_techs["LargeScaleHeatPump"], peak_demand_kw=peak_demand_kw)

# --- STEP 3: GLOBAL ENERGY BALANCE ---
# Heat production from all units must meet demand every hour
model.addConstrs(
    (gp.quicksum(tech.V_heat[t] for tech in technologies) + (tes.V_disch[t] - tes.U_charge[t] if tes_enabled else 0) == HEAT_DEMAND_VEC[t]
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
)

if tes_enabled:
    annual_investment += (tes.E_cap * tes.capex_per_kwh * config.ANNUITY_FACTOR)

# Fuel costs (Use a conditional check for tech presence)
fuel_costs = gp.quicksum(
    (all_techs["BiomassBoiler"].U_biomass[t] * config.FUEL_PRICES["biomass"] if config.TECH_SWITCHES["BiomassBoiler"] else 0) +
    (all_techs["CHP"].U_gas[t] * config.FUEL_PRICES["gas"] if config.TECH_SWITCHES["CHP"] else 0) +
    (all_techs["LargeScaleHeatPump"].U_elec[t] * ELEC_PRICE_VEC[t] if config.TECH_SWITCHES["LargeScaleHeatPump"] else 0)
    for t in timesteps
)

# Revenue from CHP electricity sales
if config.TECH_SWITCHES["CHP"]:
    elec_revenue = gp.quicksum(all_techs["CHP"].V_elec[t] * config.ELEC_REVENUE for t in timesteps)
else:
    elec_revenue = 0

model.setObjective(annual_investment + fuel_costs - elec_revenue, GRB.MINIMIZE)

# --- STEP 5: OPTIMIZE & RESULTS ---
model.optimize()

if model.Status == GRB.OPTIMAL:
    print(f"Optimal Total Cost: {model.ObjVal} Euro")
    print(f"Installed Biomass Boiler Capacity: {all_techs['BiomassBoiler'].P_cap.X} kW")
    print(f"Installed CHP Capacity: {all_techs['CHP'].P_cap.X} kW")
    print(f"Installed LSHP Capacity: {all_techs['LargeScaleHeatPump'].P_cap.X} kW")
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
    t_plot = range(8760)
    jan_slice = range(288, 624)
    aug_slice = range(5160, 5496)


    # --- 1. HEAT DISPATCH PLOTS ---
    def create_heat_dispatch_figure(period, title):
        plt.figure(figsize=(12, 6))

        # Accessing variables via all_techs dictionary
        v_boiler = [all_techs['BiomassBoiler'].V_heat[i].X / 1000 if 'BiomassBoiler' in all_techs else 0 for i in
                    period]
        v_chp = [all_techs['CHP'].V_heat[i].X / 1000 if 'CHP' in all_techs else 0 for i in period]
        v_hp = [all_techs['LargeScaleHeatPump'].V_heat[i].X / 1000 if 'LargeScaleHeatPump' in all_techs else 0 for i in
                period]

        plt.stackplot([t_plot[i] for i in period],
                      v_boiler, v_chp, v_hp,
                      labels=['Biomass Boiler', 'CHP', 'Heat Pump'],
                      colors=['#2ecc71', '#3498db', '#e74c3c'], alpha=0.8)

        plt.plot([t_plot[i] for i in period], [HEAT_DEMAND_VEC[i] / 1000 for i in period],
                 color='black', linestyle='--', linewidth=2, label='Total Demand')
        plt.title(title)
        plt.xlabel('Hour of the Year')
        plt.ylabel('Power (MW)')
        plt.legend(loc='upper right')
        plt.grid(axis='y', linestyle=':', alpha=0.6)
        plt.tight_layout()
        plt.show()


    create_heat_dispatch_figure(t_plot, 'Heat Dispatch: Full Year')
    create_heat_dispatch_figure(jan_slice, 'Heat Dispatch: January Zoom (Hours 288-624)')
    create_heat_dispatch_figure(aug_slice, 'Heat Dispatch: August Zoom (Hours 5160-5496)')

    # --- 2. TES OPERATION PLOTS ---
    # Note: 'tes' variable name remains the same as per your print statement
    charge_vals = [-tes.U_charge[t].X / 1000 for t in t_plot]
    disch_vals = [tes.V_disch[t].X / 1000 for t in t_plot]
    soc_vals = [tes.E_state[t].X / 1000 for t in t_plot]


    def create_tes_double_subplot(period, title_suffix):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
        p_range = [t_plot[i] for i in period]

        ax1.fill_between(p_range, [disch_vals[i] for i in period], label='Discharging (+)', color='orange', alpha=0.7)
        ax1.fill_between(p_range, [charge_vals[i] for i in period], label='Charging (-)', color='navy', alpha=0.7)
        ax1.axhline(0, color='black', linewidth=1)
        ax1.set_ylabel('Power Flow (MW)')
        ax1.set_title(f'TES Operation: Charging vs. Discharging ({title_suffix})')
        ax1.legend(loc='upper right')
        ax1.grid(alpha=0.3)

        ax2.plot(p_range, [soc_vals[i] for i in period], color='green', linewidth=1.5, label='Stored Energy')
        ax2.fill_between(p_range, [soc_vals[i] for i in period], color='green', alpha=0.1)
        ax2.set_ylabel('Stored Energy (MWh)')
        ax2.set_xlabel('Hour of the Year')
        ax2.set_title(f'TES Energy Level (SoC) ({title_suffix})')
        ax2.legend(loc='upper right')
        ax2.grid(alpha=0.3)

        plt.tight_layout()
        plt.show()


    create_tes_double_subplot(t_plot, 'Full Year')
    create_tes_double_subplot(jan_slice, 'January Zoom')
    create_tes_double_subplot(aug_slice, 'August Zoom')


    # --- 3. COOLING DISPATCH PLOTS ---
    def create_cool_dispatch_figure(period, title):
        plt.figure(figsize=(12, 6))

        # Accessing cooling via all_techs['LargeScaleHeatPump']
        v_cool = [all_techs['LargeScaleHeatPump'].V_cool[i].X / 1000 if 'LargeScaleHeatPump' in all_techs else 0 for i
                  in period]

        plt.stackplot([t_plot[i] for i in period],
                      v_cool,
                      labels=['Heat Pump'],
                      colors=['#e74c3c'], alpha=0.8)

        plt.plot([t_plot[i] for i in period], [COOLING_DEMAND_VEC[i] / 1000 for i in period],
                 color='black', linestyle='--', linewidth=2, label='Total Demand')
        plt.title(title)
        plt.xlabel('Hour of the Year')
        plt.ylabel('Power (MW)')
        plt.legend(loc='upper right')
        plt.grid(axis='y', linestyle=':', alpha=0.6)
        plt.tight_layout()
        plt.show()


    create_cool_dispatch_figure(t_plot, 'Cool Dispatch: Full Year')
    create_cool_dispatch_figure(jan_slice, 'Cool Dispatch: January Zoom (Hours 288-624)')
    create_cool_dispatch_figure(aug_slice, 'Cool Dispatch: August Zoom (Hours 5160-5496)')
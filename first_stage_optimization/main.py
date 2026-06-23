import pandas as pd
import matplotlib.pyplot as plt
import gurobipy as gp
from gurobipy import GRB
import json


x = pd.DataFrame({'NAME':['FOURLARIS']})
print(x)

# Import the classes
from first_stage_optimization import config
from first_stage_optimization.CHP import CHP
from first_stage_optimization.BiomassBoiler import BiomassBoiler
from first_stage_optimization.LSHP import LargeScaleHeatPump
from first_stage_optimization.TES import PitThermalEnergyStorage
from first_stage_optimization.Chiller import LargeScaleChiller

# --- PRE-MODELING CHECK ---
# Verify the data is flowing
print(f"Using CRF: {config.ANNUITY_FACTOR:.4f}")
print(f"Average COP: {sum(config.COP_VEC) / 8760:.2f}")
print(f"Average cooling COP: {sum(config.COP_COOL_VEC) / 8760:.2f}")

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
ELEC_PRICE_VEC = config.DYNAMIC_ELEC_PRICES.tolist()

# --- STEP 1: INITIALIZATION ---
model = gp.Model("District_Energy_Optimization")
timesteps = range(8760)  # Hourly resolution for one year
model.setParam('MIPGap', 0.01) #for making it run faster

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
# 1. Check experiment conditions
lshp_enabled = config.TECH_SWITCHES.get("LargeScaleHeatPump", True)
tes_enabled = config.TECH_SWITCHES.get("TES", True)

# The chiller is only active if BOTH LSHP and TES are False
chiller_enabled = (not lshp_enabled) and (not tes_enabled)

all_techs = {
    "BiomassBoiler": BiomassBoiler("BB"),
    "CHP": CHP("CHP"),
    "LargeScaleHeatPump": LargeScaleHeatPump("HP")
}

# Inject chiller dynamically into the experiment if condition is met
if chiller_enabled:
    all_techs["Chiller"] = LargeScaleChiller("CH")

# Filter tech based on config switches + chiller
technologies = []
for name, obj in all_techs.items():
    if name == "Chiller":
        technologies.append(obj) # Already determined by chiller_enabled flag
    elif config.TECH_SWITCHES.get(name, True):
        technologies.append(obj)

# 1. ADD ALL VARIABLES FIRST
for tech in technologies:
    tech.add_variables(model, timesteps)

if tes_enabled:
    tes = PitThermalEnergyStorage("TES")
    tes.add_variables(model, timesteps) # Variables for TES added here

# 2. ADD CONSTRAINTS
for tech in technologies:
    if isinstance(tech, LargeScaleHeatPump):
        tech.add_constraints(model, timesteps, config.COP_VEC, config.COP_COOL_VEC)
    elif isinstance(tech, LargeScaleChiller):
        tech.add_constraints(model, timesteps, config.COP_COOL_VEC) # Uses cooling vector
    else:
        tech.add_constraints(model, timesteps)

if tes_enabled:
    # Safe check: if LSHP is off, pass None or handle it inside your TES constraint file
    hp_inst = all_techs["LargeScaleHeatPump"] if lshp_enabled else None
    tes.add_constraints(model, timesteps, hp_instance=hp_inst, peak_demand_kw=peak_demand_kw)

# --- STEP 3: GLOBAL ENERGY BALANCE ---
# Heat production from all units must meet demand every hour
model.addConstrs(
    (gp.quicksum(tech.V_heat[t] for tech in technologies if hasattr(tech, 'V_heat')) + (tes.V_disch[t] - tes.U_charge[t] if tes_enabled else 0) == HEAT_DEMAND_VEC[t]
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

# Dynamic fuel and electricity costs calculation loop
fuel_costs = 0
for t in timesteps:
    if config.TECH_SWITCHES.get("BiomassBoiler", True):
        fuel_costs += all_techs["BiomassBoiler"].U_biomass[t] * config.FUEL_PRICES["biomass"]
    if config.TECH_SWITCHES.get("CHP", True):
        fuel_costs += all_techs["CHP"].U_gas[t] * config.FUEL_PRICES["gas"]
    if lshp_enabled:
        fuel_costs += all_techs["LargeScaleHeatPump"].U_elec[t] * ELEC_PRICE_VEC[t]
    if chiller_enabled:
        fuel_costs += all_techs["Chiller"].U_elec[t] * ELEC_PRICE_VEC[t]

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

    # Check Biomass Boiler
    if config.TECH_SWITCHES.get('BiomassBoiler'):
        print(f"Installed Biomass Boiler Capacity: {all_techs['BiomassBoiler'].P_cap.X:.2f} kW")

    # Check CHP
    if config.TECH_SWITCHES.get('CHP'):
        print(f"Installed CHP Capacity: {all_techs['CHP'].P_cap.X:.2f} kW")

    # Check Heat Pump
    if lshp_enabled:
        print(f"Installed LSHP Capacity: {all_techs['LargeScaleHeatPump'].P_cap.X:.2f} kW")

    #Cgeck Chiller
    if chiller_enabled:
        print(f"Installed Chiller Capacity: {all_techs['Chiller'].P_cap.X:.2f} kW")

    # Check TES
    if tes_enabled:
        print(f"Installed TES Capacity: {tes.E_cap.X:.2f} kWh")
        tes_energy_kwh = tes.E_cap.X

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
    else:
        print("TES is disabled for this run.")


if model.Status == GRB.OPTIMAL:
    t_plot = range(8760)
    jan_slice = range(288, 624)
    aug_slice = range(5160, 5496)


    # --- 1. HEAT DISPATCH PLOTS ---
    def create_heat_dispatch_figure(period, title):
        plt.figure(figsize=(12, 6))

        # Check if technology is enabled before accessing .X, otherwise use a list of zeros
        if config.TECH_SWITCHES.get("BiomassBoiler"):
            v_boiler = [all_techs['BiomassBoiler'].V_heat[i].X / 1000 for i in period]
        else:
            v_boiler = [0] * len(period)

        if config.TECH_SWITCHES.get("CHP"):
            v_chp = [all_techs['CHP'].V_heat[i].X / 1000 for i in period]
        else:
            v_chp = [0] * len(period)

        if config.TECH_SWITCHES.get("LargeScaleHeatPump"):
            v_hp = [all_techs['LargeScaleHeatPump'].V_heat[i].X / 1000 for i in period]
        else:
            v_hp = [0] * len(period)

        plt.stackplot([t_plot[i] for i in period],
                      v_boiler, v_chp, v_hp,
                      labels=['Biomass Boiler', 'CHP', 'Heat Pump'],
                      colors=['#2ecc71', '#3498db', '#e74c3c'], alpha=0.8)

        plt.plot([t_plot[i] for i in period], [HEAT_DEMAND_VEC[i] / 1000 for i in period],
                 color='black', linestyle='--', linewidth=2, label='Heat Demand')
        plt.title(title)
        plt.xlabel('Hour of the Year')
        plt.ylabel('Power (MW)')
        plt.legend(loc='upper right')
        plt.grid(axis='y', linestyle=':', alpha=0.6)
        plt.tight_layout()
        plt.show()


    create_heat_dispatch_figure(t_plot, 'Heat Dispatch: Full Year')
    create_heat_dispatch_figure(jan_slice, 'Heat Dispatch: 13-26 January 2025')
    create_heat_dispatch_figure(aug_slice, 'Heat Dispatch: 4-17 August 2025')

    # --- 2. TES OPERATION PLOTS ---
    # Only calculate and show TES plots if TES technology exists in the run
    if tes_enabled:
        charge_vals = [-tes.U_charge[t].X / 1000 for t in t_plot]
        disch_vals = [tes.V_disch[t].X / 1000 for t in t_plot]
        soc_vals = [tes.E_state[t].X / 1000 for t in t_plot]
        tes_capacity_mwh = tes.E_cap.X / 1000
        soc_percent_vals = [(val / tes_capacity_mwh) * 100 for val in soc_vals]


        def create_tes_double_subplot(period, title_suffix):
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
            p_range = [t_plot[i] for i in period]

            ax1.fill_between(p_range, [disch_vals[i] for i in period], label='Discharging (+)', color='orange',
                             alpha=0.7)
            ax1.fill_between(p_range, [charge_vals[i] for i in period], label='Charging (-)', color='navy', alpha=0.7)
            ax1.axhline(0, color='black', linewidth=1)
            ax1.set_ylabel('Power Flow (MW)')
            ax1.set_title(f'TES Operation ({title_suffix})')
            ax1.legend(loc='upper right')
            ax1.grid(alpha=0.3)

            ax2.plot(p_range, [soc_percent_vals[i] for i in period], color='green', linewidth=1.5, label='Stored Energy')
            ax2.fill_between(p_range, [soc_percent_vals[i] for i in period], color='green', alpha=0.1)
            ax2.set_ylabel('State of Charge (%)')
            ax2.set_xlabel('Hour of the Year')
            ax2.legend(loc='upper right')
            ax2.grid(alpha=0.3)

            plt.tight_layout()
            plt.show()


        create_tes_double_subplot(t_plot, 'Full Year')
        create_tes_double_subplot(jan_slice, '13-26 January 2025')
        create_tes_double_subplot(aug_slice, '13-26 August 2025')

    # --- 3. COOLING DISPATCH PLOTS ---
    if lshp_enabled or chiller_enabled:
        def create_cool_dispatch_figure(period, title):
            plt.figure(figsize=(12, 6))

            if lshp_enabled:
                v_cool = [all_techs['LargeScaleHeatPump'].V_cool[i].X / 1000 for i in period]
                label = 'Heat Pump'
                color = '#e74c3c'
            else:
                v_cool = [all_techs['Chiller'].V_cool[i].X / 1000 for i in period]
                label = 'Chiller (AC)'
                color = '#9b59b6'  # Distinct purple layout for Chiller

            plt.stackplot([t_plot[i] for i in period], v_cool, labels=[label], colors=[color], alpha=0.8)
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
        create_cool_dispatch_figure(aug_slice, 'Cool Dispatch: August Zoom')

    # --- NEW: WRITE OPTIMAL CAPACITIES TO JSON FOR STAGE 2 ---
    stage1_results = {
        "BiomassBoiler": all_techs['BiomassBoiler'].P_cap.X if config.TECH_SWITCHES.get('BiomassBoiler') else 0.0,
        "CHP": all_techs['CHP'].P_cap.X if config.TECH_SWITCHES.get('CHP') else 0.0,
        "LargeScaleHeatPump": all_techs['LargeScaleHeatPump'].P_cap.X if config.TECH_SWITCHES.get(
            'LargeScaleHeatPump') else 0.0,
        "TES": tes.E_cap.X if config.TECH_SWITCHES.get('TES') else 0.0
    }

    # Explicitly save to your input data directory
    json_output_path = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/first_stage_optimization/stage1_optimal_capacities.json"

    with open(json_output_path, 'w') as f:
        json.dump(stage1_results, f, indent=4)

    print(f"\nSaved optimal footprints to JSON configuration: {json_output_path}")

    # --- NEW: SAVE HEAT PUMP DISPATCH TO EXCEL ---
    if lshp_enabled:
        print("\nExporting Heat Pump data to Excel...")
        hp_unit = all_techs['LargeScaleHeatPump']

        # Define the path where you want to save the Excel file
        excel_output_path = "/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/first_stage_optimization/lshp_operation.xlsx"

        # Organize the periods into a dictionary for clean looping
        tracked_periods = {
            "January_Slice": jan_slice,
            "August_Slice": aug_slice
        }

        # Use ExcelWriter to save multiple sheets to one file
        with pd.ExcelWriter(excel_output_path) as writer:
            for sheet_name, period_range in tracked_periods.items():
                # Gather variables hour by hour for the specific period
                export_data = {
                    "Hour_of_Year": [t for t in period_range],
                    "U_elec_kW": [hp_unit.U_elec[t].X for t in period_range],
                    "V_heat_kW": [hp_unit.V_heat[t].X for t in period_range]
                }

                # Turn it into a DataFrame and write to its respective sheet
                df_slice = pd.DataFrame(export_data)
                df_slice.to_excel(writer, sheet_name=sheet_name, index=False)

        print(f"Successfully saved Heat Pump operational profiles to: {excel_output_path}")
    else:
        print("\nLarge Scale Heat Pump is disabled; skipping Excel export.")
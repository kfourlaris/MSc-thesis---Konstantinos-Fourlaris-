import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Import the new 15-minute operational modules and high-res config
import config2
from second_stage_optimization.BiomassBoiler2 import BiomassBoiler15Min
from second_stage_optimization.CHP2 import CHP15Min
from second_stage_optimization.LSHP2 import LargeScaleHeatPump15Min
from second_stage_optimization.TES2 import PitThermalEnergyStorage15Min

# --- STEP 0: PRE-CHECK CONFIGURATION FLOW ---
print(f"--- Running Stage 2 Balancing Market Optimization for: {config2.SELECTED_CITY} ---")
print(f"Locked Annuity Factor (CRF): {config2.ANNUITY_FACTOR:.4f}")
print(f"Number of Scenarios Loaded: {len(config2.SCENARIOS)} ({config2.SCENARIOS})")
print(f"Total 15-Minute Timesteps: {len(config2.HEAT_DEMAND_15MIN)} intervals")

# --- STEP 1: INITIALIZE GUROBI MULTI-SCENARIO ENVIRONMENT ---
model = gp.Model("Stage2_15Min_Balancing_Optimization")
model.setParam('MIPGap', 0.008)  # Maintain identical performance gap target

timesteps_15min = range(35040)  # High-resolution time horizon (8760 * 4)

# --- STEP 2: INSTANTIATE TECHNOLOGIES (Switches removed, all fully active) ---
boiler = BiomassBoiler15Min("BB_Zurich")
chp = CHP15Min("CHP_Zurich")
lshp = LargeScaleHeatPump15Min("HP_Zurich")
tes = PitThermalEnergyStorage15Min("TES_Zurich")

technologies = [boiler, chp, lshp]

# --- STEP 3: LOOP SCENARIOS TO BUILD VARIABLES & CONSTRAINTS ---
for s in config2.SCENARIOS:
    # 1. Add operational variables for this specific scenario
    for tech in technologies:
        tech.add_variables(model, timesteps_15min, scenario=s)
    tes.add_variables(model, timesteps_15min, scenario=s)

    # 2. Enforce physical technology performance constraints
    boiler.add_constraints(model, timesteps_15min, scenario=s)
    chp.add_constraints(model, timesteps_15min, scenario=s)
    lshp.add_constraints(
        model,
        timesteps_15min,
        cop_vector_15min=config2.COP_VEC_15MIN,
        cop_cool_vector_15min=config2.COP_COOL_VEC_15MIN,
        scenario=s
    )

    # 3. Enforce inventory boundaries for thermal energy storage
    tes.add_constraints(
        model,
        timesteps_15min,
        hp_15min_instance=lshp,
        peak_demand_kw=config2.PEAK_DEMAND_KW,
        scenario=s
    )

    # 4. Global Network Energy Demand Balances per Scenario
    # Multiplied by 0.25 hours because tech variables are kW (Power), demand is kWh (Energy)
    model.addConstrs(
        (gp.quicksum(tech.V_heat[t, s] for tech in technologies) * 0.25 +
         (tes.V_disch[t, s] - tes.U_charge[t, s]) * 0.25 == config2.HEAT_DEMAND_15MIN[t]
         for t in timesteps_15min),
        name=f"Global_Heat_Demand_Balance_{s}"
    )

    model.addConstrs(
        (lshp.V_cool[t, s] * 0.25 == config2.COOLING_DEMAND_15MIN[t]
         for t in timesteps_15min),
        name=f"Global_Cooling_Demand_Balance_{s}"
    )

# --- STEP 4: MATRICULATE TOTAL EXPECTED OBJECTIVE FUNCTION ---

# Part A: The static, invariant structural investment overhead (From locked sizes)
total_fixed_annual_investment = (
        boiler.fixed_annual_cost +
        chp.fixed_annual_cost +
        lshp.fixed_annual_cost +
        tes.fixed_annual_cost
)

# Part B: Probability-weighted rolling operational costs/balancing arbitrage profiles
expected_operational_cost = 0

for s in config2.SCENARIOS:
    prob = config2.PROBABILITY[s]

    # Baseline fuel expenditures & baseline day-ahead electricity purchases
    baseline_spending_s = gp.quicksum(
        ((boiler.U_biomass[t, s] * 0.25) * config2.FUEL_PRICES["biomass"]) +
        ((chp.U_gas[t, s] * 0.25) * config2.FUEL_PRICES["gas"]) +
        ((lshp.U_elec[t, s] * 0.25) * config2.DYNAMIC_ELEC_PRICES_15MIN[t])
        for t in timesteps_15min
    )

    # Steady baseline spot-market revenues from CHP generation exports
    baseline_revenue_s = gp.quicksum(
        (chp.V_elec[t, s] * 0.25) * config2.ELEC_REVENUE
        for t in timesteps_15min
    )

    # Balancing Upward Revenue (Paid to the Heat Pump for REDUCING consumption)
    # Always subtract because it is a direct revenue stream
    bal_arbitrage_up_s = gp.quicksum(
        (lshp.V_balancing_up[t, s] * 0.25) * config2.BAL_PRICE_UP[s][t]
        for t in timesteps_15min
    )

    #Balancing Downward Effect (Paid/Billed to the Heat Pump for INCREASING consumption)
    # Always add because the Excel signs automatically dictate the financial flow:
    #   - If price is Negative: adding a negative drops your cost (Desperate grid pays you)
    #   - If price is Positive: adding a positive adds a cheap cost (Discounted charging)
    bal_arbitrage_down_s = gp.quicksum(
        (lshp.V_balancing_down[t, s] * 0.25) * config2.BAL_PRICE_DOWN[s][t]
        for t in timesteps_15min
    )

    # Aggregate net scenario operational result multiplied by probability metric
    expected_operational_cost += prob * (
                baseline_spending_s - baseline_revenue_s - bal_arbitrage_up_s + bal_arbitrage_down_s)

# Establish Unified Optimization Goal
model.setObjective(total_fixed_annual_investment + expected_operational_cost, GRB.MINIMIZE)

# --- STEP 5: SOLVE MODEL & REPORT STOCHASTIC SUMMARY ---
model.optimize()


if model.Status == GRB.OPTIMAL:
    print("\n" + "=" * 50)
    print("OPTIMIZATION SUCCESSFUL - STAGE 2 UNIFIED RESULTS")
    print("=" * 50)
    print(f"Unified Expected Total Annual Cost (TAC):  {model.ObjVal:,.2f} Euro")
    print(f" -> Fixed Capital & Maintenance Overhead:  {total_fixed_annual_investment:,.2f} Euro")
    print(f" -> Expected Multi-Scenario Net Opex:     {model.ObjVal - total_fixed_annual_investment:,.2f} Euro")
    print("=" * 50)

    # =========================================================================
    # --- STEP 6: PLOTTING FOR RESULTS VALIDATION (ZOOMED TO ONE SPECIFIC WEEK) ---
    # =========================================================================
    target_scenario = 'S1'  # Change to 'S2', 'S3', etc., to inspect others

    # Define your exact 1-week validation window
    start_t = 1344
    end_t = 2016
    week_timesteps = range(start_t, end_t)

    print(f"\nExtracting and rendering LSHP operational curves for Scenario: {target_scenario}...")
    print(f"Zooming into week profile: Timesteps {start_t} to {end_t}")

    u_elec_values = [lshp.U_elec[t, target_scenario].X for t in week_timesteps]
    bal_up_values = [lshp.V_balancing_up[t, target_scenario].X for t in week_timesteps]
    bal_down_values = [lshp.V_balancing_down[t, target_scenario].X for t in week_timesteps]

    net_elec_import = [
        u_elec_values[i] + bal_down_values[i] - bal_up_values[i] for i in range(len(week_timesteps))
    ]

    df_plot = pd.DataFrame({
        'Timestep': list(week_timesteps),
        'Baseline_Import': u_elec_values,
        'Balancing_Up': bal_up_values,
        'Balancing_Down': bal_down_values,
        'Net_Electrical_Import': net_elec_import
    })

    # =========================================================================
    # --- PRINT QUANTITATIVE VALUES FOR EVERY QUARTER OF THE EXAMINED WEEK ---
    # =========================================================================
    print("\n" + "=" * 95)
    print(f"      QUARTERLY OPERATIONAL DISPATCH DATA FOR LSHP (TIMESTEPS {start_t} TO {end_t})")
    print("=" * 95)
    # Print Table Header
    print(
        f"{'Timestep':<10} | {'Day of Year':<12} | {'Hour':<8} | {'Baseline (kW)':<15} | {'Bal_Up (kW)':<12} | {'Bal_Down (kW)':<13} | {'Net_Import (kW)':<15}")
    print("-" * 95)

    for idx, row in df_plot.iterrows():
        t_val = int(row['Timestep'])

        # Calculate real time layout assuming timestep 0 is Jan 1st 00:00
        # 4 intervals per hour means t / 4 = total hours passed
        total_hours_passed = t_val / 4
        day_of_year = int(total_hours_passed // 24) + 1
        hour_of_day = int(total_hours_passed % 24)
        minute_of_hour = int((t_val % 4) * 15)
        time_str = f"{hour_of_day:02d}:{minute_of_hour:02d}"

        # Print every quarterly interval entry with clean decimal formatting
        print(
            f"{t_val:<10} | Day {day_of_year:<8} | {time_str:<8} | {row['Baseline_Import']:<15,.2f} | {row['Balancing_Up']:<12,.2f} | {row['Balancing_Down']:<13,.2f} | {row['Net_Electrical_Import']:<15,.2f}")

    print("=" * 95 + "\n")

    plt.figure(figsize=(15, 6))

    # Plot tracking signals
    plt.plot(df_plot['Timestep'], df_plot['Baseline_Import'], label='Baseline Import ($U_{elec}$)',
             color='gray', linestyle='--', alpha=0.7, linewidth=1.5)
    plt.plot(df_plot['Timestep'], df_plot['Balancing_Down'], label='Balancing Down ($V_{bal,down}$ - Consuming More)',
             color='darkred', alpha=0.8, linewidth=1.5)
    plt.plot(df_plot['Timestep'], df_plot['Balancing_Up'], label='Balancing Up ($V_{bal,up}$ - Consuming Less)',
             color='darkgreen', alpha=0.8, linewidth=1.5)

    # FIX: Changed 'style' to 'linestyle'
    plt.plot(df_plot['Timestep'], df_plot['Net_Electrical_Import'], label='Net Physical Grid Import',
             color='blue', linewidth=2.0, linestyle='-')

    # Chart decorations
    plt.title(
        f'Zurich LSHP Electrical Dispatch Validation | Scenario {target_scenario} (Timesteps {start_t} - {end_t})',
        fontsize=13, fontweight='bold')
    plt.xlabel('15-Minute Operational Intervals', fontsize=11)
    plt.ylabel('Electrical Power Demand (kW)', fontsize=11)

    plt.xlim(start_t, end_t)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='none')

    plt.tight_layout()
    print("Rendering zoomed graph layout. Close the window manually to finish script execution.")
    plt.show(block=True)
else:
    print("Optimization terminated with status code:", model.Status)


import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json

# Import the new 15-minute operational modules and high-res config
import config3
from second_stage_optimization_new_approach.BiomassBoiler3 import BiomassBoiler15Min2
from second_stage_optimization_new_approach.CHP3 import CHP15Min2
from second_stage_optimization_new_approach.LSHP3 import LargeScaleHeatPump15Min2
from second_stage_optimization_new_approach.TES3 import PitThermalEnergyStorage15Min2

# --- STEP 0: PRE-CHECK CONFIGURATION FLOW ---
print(f"--- Running Stage 2 Balancing Market Optimization for: {config3.SELECTED_CITY} ---")
print(f"Locked Annuity Factor (CRF): {config3.ANNUITY_FACTOR:.4f}")
print(f"Number of Scenarios Loaded: {len(config3.SCENARIOS)} ({config3.SCENARIOS})")
print(f"Total 15-Minute Timesteps: {len(config3.HEAT_DEMAND_15MIN)} intervals")
print(f"Using CRF: {config3.ANNUITY_FACTOR:.4f}")
print(f"Average COP: {sum(config3.COP_VEC_15MIN) / 35040:.2f}")
print(f"Average cooling COP: {sum(config3.COP_COOL_VEC_15MIN) / 35040:.2f}")

# --- STEP 1: INITIALIZE GUROBI MULTI-SCENARIO ENVIRONMENT ---
model = gp.Model("Stage2_15Min_Balancing_Optimization_new_approach")
model.setParam('MIPGap', 0.08)  # Maintain identical performance gap target
# Force Gurobi to use the deterministic Barrier Method (skips concurrent wait)
model.setParam('Method', 3)

timesteps_15min = range(35040)  # High-resolution time horizon (8760 * 4)

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
boiler = BiomassBoiler15Min2("BB")
chp = CHP15Min2("CHP")
lshp = LargeScaleHeatPump15Min2("HP")
tes = PitThermalEnergyStorage15Min2("TES")

# =========================================================================
# --- STEP 3: INITIALIZE FIXED DAY-AHEAD PLAN VARIABLES ONCE (FIRST STAGE) ---
# =========================================================================
chp.add_variables(model, timesteps_15min)
chp.add_constraints(model, timesteps_15min)

boiler.add_variables(model, timesteps_15min)
boiler.add_constraints(model, timesteps_15min)

lshp.add_variables(model, timesteps_15min)

# =========================================================================
# --- STEP 4: LOOP SCENARIOS TO BUILD REAL-TIME BALANCING RULES ---
# =========================================================================
for s in config3.SCENARIOS:
    # 1. Add operational variables for this specific scenario
    lshp.add_scenario_variables(model, timesteps_15min, scenario=s)
    tes.add_variables(model, timesteps_15min, scenario=s)

    # 2. Enforce physical technology performance constraints per scenario
    lshp.add_constraints(
        model,
        timesteps_15min,
        cop_vector_15min=config3.COP_VEC_15MIN,
        cop_cool_vector_15min=config3.COP_COOL_VEC_15MIN,
        scenario=s
    )

    # 3. Enforce inventory boundaries for thermal energy storage
    tes.add_constraints(
        model,
        timesteps_15min,
        hp_15min_instance=lshp,
        peak_demand_kw=config3.PEAK_DEMAND_KW,
        scenario=s
    )

    # 4. Global Network Energy Demand Balances per Scenario
    # Multiplied by 0.25 hours because tech variables are kW (Power), demand is kWh (Energy)
    model.addConstrs(
        (boiler.V_heat[t] * 0.25 +       # <--- Corrected: Independent of scenario
         chp.V_heat[t] * 0.25 +          # <--- Corrected: Independent of scenario
         lshp.V_heat_DA[t] * 0.25 +      # <--- Corrected: Independent of scenario
         (tes.V_disch[t, s] - tes.U_charge[t, s]) * 0.25 == config3.HEAT_DEMAND_15MIN[t]
         for t in timesteps_15min),
        name=f"Global_Heat_Demand_Balance_{s}"
    )

    model.addConstrs(
        (lshp.V_cool[t] * 0.25 == config3.COOLING_DEMAND_15MIN[t]  # <--- Corrected: Independent of scenario
         for t in timesteps_15min),
        name=f"Global_Cooling_Demand_Balance_{s}"
    )

# --- STEP 5: MATRICULATE TOTAL EXPECTED OBJECTIVE FUNCTION ---

# Part A: The static, invariant structural investment overhead (From locked sizes)
total_fixed_annual_investment = (
        boiler.fixed_annual_cost +
        chp.fixed_annual_cost +
        lshp.fixed_annual_cost +
        tes.fixed_annual_cost
)

# Part B: Probability-weighted rolling operational costs/balancing arbitrage profiles
expected_operational_cost = 0

for s in config3.SCENARIOS:
    prob = config3.PROBABILITY[s]

    # Baseline fuel expenditures & baseline day-ahead electricity purchases
    baseline_spending_s = gp.quicksum(
        ((boiler.U_biomass[t] * 0.25) * config3.FUEL_PRICES["biomass"]) +        # <--- Corrected
        ((chp.U_gas[t] * 0.25) * config3.FUEL_PRICES["gas"]) +                  # <--- Corrected
        ((lshp.U_elec[t] * 0.25) * config3.DYNAMIC_ELEC_PRICES_15MIN[t])        # <--- Corrected
        for t in timesteps_15min
    )

    # Steady baseline spot-market revenues from CHP generation exports
    baseline_revenue_s = gp.quicksum(
        (chp.V_elec[t] * 0.25) * config3.ELEC_REVENUE                           # <--- Corrected
        for t in timesteps_15min
    )

    # Balancing Upward Revenue (Paid to the Heat Pump for REDUCING consumption)
    bal_arbitrage_up_s = gp.quicksum(
        (lshp.V_balancing_up[t, s] * 0.25) * config3.BAL_PRICE_UP[s][t]
        for t in timesteps_15min
    )

    # Balancing Downward Effect (Paid/Billed to the Heat Pump for INCREASING consumption)
    bal_arbitrage_down_s = gp.quicksum(
        (lshp.V_balancing_down[t, s] * 0.25) * config3.BAL_PRICE_DOWN[s][t]
        for t in timesteps_15min
    )

    # Aggregate net scenario operational result multiplied by probability metric
    expected_operational_cost += prob * (
                baseline_spending_s - baseline_revenue_s - bal_arbitrage_up_s + bal_arbitrage_down_s)

# Establish Unified Optimization Goal
model.setObjective(total_fixed_annual_investment + expected_operational_cost, GRB.MINIMIZE)

# --- STEP 6: SOLVE MODEL & REPORT STOCHASTIC SUMMARY ---
model.optimize()


if model.Status == GRB.OPTIMAL:
    # 1. Extract the actual optimized float values from the Gurobi algebraic objects
    numerical_bal_up = bal_arbitrage_up_s.getValue()
    numerical_bal_down = bal_arbitrage_down_s.getValue()

    # 2. Pre-calculate your specific financial breakdowns as pure numbers
    calculated_baseline_cost = model.ObjVal - total_fixed_annual_investment + numerical_bal_up - numerical_bal_down
    net_balancing_opex = - numerical_bal_up + numerical_bal_down

    print("\n" + "=" * 65)
    print("        OPTIMIZATION SUCCESSFUL - STAGE 2 BREAKDOWN RESULTS NEW APPROACH")
    print("=" * 65)
    print(f"Unified Expected Total Annual Cost (TAC):      {model.ObjVal:15,.2f} Euro")
    print("-" * 65)
    print(f" -> Fixed Capital & Maintenance Overhead:      {total_fixed_annual_investment:15,.2f} Euro")
    print(f" -> Expected Multi-Scenario Baseline Cost:     {calculated_baseline_cost:15,.2f} Euro")
    print(f" -> Balancing Participation Net Opex:          {net_balancing_opex:15,.2f} Euro")
    print("=" * 65)

    # =========================================================================
    # --- STEP 7: PLOTTING FOR RESULTS VALIDATION (ZOOMED TO ONE SPECIFIC WEEK) ---
    # =========================================================================
    target_scenario = 'S1'  # Change to 'S2', 'S3', etc., to inspect others

    # Define your exact 1-week validation window
    start_t = 1152
    end_t = 2496
    week_timesteps = range(start_t, end_t)

    print(f"\nExtracting and rendering LSHP operational curves for Scenario: {target_scenario}...")
    print(f"Zooming into week profile: Timesteps {start_t} to {end_t}")

    u_elec_values = [lshp.U_elec[t].X for t in week_timesteps]  # <--- Corrected
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

    # =========================================================================
    # --- STEP 8: PLOTTING FOR RESULTS VALIDATION (MULTI-WEEK COMPARISON) ---
    # =========================================================================
    target_scenario = 'S1'  # Target scenario profile to isolate

    # Define the two distinct 1-week evaluation horizons
    validation_periods = [
        (1152, 2496, "Winter Week (Jan)"),
        (20640, 21984, "Summer Week (Jul)")
    ]

    print(f"\n" + "=" * 60)
    print(f" GENERATING STAGE 2 MULTI-PERIOD SYSTEM DISPATCH FIGURES")
    print(f" Isolated Scenario Profile: {target_scenario}")
    print("=" * 60)

    for start_t, end_t, period_label in validation_periods:
        week_timesteps = range(start_t, end_t)
        hour_range = [t / 4 for t in week_timesteps]

        print(f"\nProcessing visual matrices for: {period_label}")
        print(f" -> Timesteps {start_t} to {end_t} (Hours {start_t / 4:.1f} to {end_t / 4:.1f})")

        # --- DATA EXTRACTION & POWER NORMALIZATION (kW to MW) ---
        v_boiler_mw = [boiler.V_heat[t].X / 1000 for t in week_timesteps]  # <--- Corrected
        v_chp_mw = [chp.V_heat[t].X / 1000 for t in week_timesteps]  # <--- Corrected
        v_lshp_da_mw = [lshp.V_heat_DA[t].X / 1000 for t in week_timesteps]  # <--- Corrected
        v_lshp_bal_mw = [lshp.V_heat_bal_down[t, target_scenario].X / 1000 for t in week_timesteps]

        heat_demand_mw = [config3.HEAT_DEMAND_15MIN[t] / 0.25 / 1000 for t in week_timesteps]
        v_cool_mw = [lshp.V_cool[t].X / 1000 for t in week_timesteps]  # <--- Corrected
        cooling_demand_mw = [config3.COOLING_DEMAND_15MIN[t] / 0.25 / 1000 for t in week_timesteps]

        charge_vals_mw = [-tes.U_charge[t, target_scenario].X / 1000 for t in week_timesteps]
        disch_vals_mw = [tes.V_disch[t, target_scenario].X / 1000 for t in week_timesteps]
        tes_capacity_mwh = tes.E_cap / 1000
        soc_percent_vals = [(tes.E_state[t, target_scenario].X / 1000 / tes_capacity_mwh) * 100 for t in week_timesteps]

        # --- THERMAL HEATING DISPATCH STACK ---
        plt.figure(figsize=(13, 5.5))
        plt.stackplot(hour_range,
                      v_boiler_mw, v_chp_mw, v_lshp_da_mw, v_lshp_bal_mw,
                      labels=['Biomass Boiler', 'CHP', 'Heat Pump (Day-Ahead)', 'Heat Pump (Balancing Down)'],
                      colors=['#2ecc71', '#3498db', '#e74c3c', '#9b59b6'], alpha=0.8)
        plt.plot(hour_range, heat_demand_mw, color='black', linestyle='--', linewidth=2, label='Town Heat Demand')

        plt.title(f'Zurich District Heating Dispatch Stack — {period_label} [Scenario: {target_scenario}]', fontsize=12,
                  fontweight='bold')
        plt.xlabel('Time Horizon (Hours of the Year)', fontsize=11)
        plt.ylabel('Thermal Power Level (MW)', fontsize=11)
        plt.xlim(start_t / 4, end_t / 4)
        plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='none')
        plt.grid(axis='y', linestyle=':', alpha=0.5)
        plt.tight_layout()
        plt.show(block=False)

        # --- TES POWER FLOWS & INVENTORY LEVEL ---
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8.5), sharex=True)

        ax1.fill_between(hour_range, disch_vals_mw, label='Storage Discharging (+)', color='orange', alpha=0.7)
        ax1.fill_between(hour_range, charge_vals_mw, label='Storage Charging (-)', color='navy', alpha=0.7)
        ax1.axhline(0, color='black', linewidth=1)
        ax1.set_ylabel('Thermal Flow (MW)', fontsize=11)
        ax1.set_title(f'TES Operation & State of Charge Tracking — {period_label}', fontsize=12, fontweight='bold')
        ax1.legend(loc='upper right')
        ax1.grid(linestyle=':', alpha=0.5)

        ax2.plot(hour_range, soc_percent_vals, color='green', linewidth=1.5, label='Stored Inventory')
        ax2.fill_between(hour_range, soc_percent_vals, color='green', alpha=0.1)
        ax2.set_ylabel('State of Charge (%)', fontsize=11)
        ax2.set_xlabel('Time Horizon (Hours of the Year)', fontsize=11)
        ax2.set_ylim(-5, 105)
        ax2.legend(loc='upper right')
        ax2.grid(linestyle=':', alpha=0.5)

        plt.xlim(start_t / 4, end_t / 4)
        plt.tight_layout()
        plt.show(block=False)

        # --- COOLING NET DISPATCH STACK ---
        plt.figure(figsize=(13, 4.5))
        plt.stackplot(hour_range, v_cool_mw, labels=['Heat Pump Cooling Stream'], colors=['#e67e22'], alpha=0.8)
        plt.plot(hour_range, cooling_demand_mw, color='black', linestyle='--', linewidth=1.8,
                 label='Town Cooling Demand')

        plt.title(f'Zurich District Cooling Network Dispatch — {period_label} [Scenario: {target_scenario}]',
                  fontsize=12, fontweight='bold')
        plt.xlabel('Time Horizon (Hours of the Year)', fontsize=11)
        plt.ylabel('Cooling Power Level (MW)', fontsize=11)
        plt.xlim(start_t / 4, end_t / 4)
        plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='none')
        plt.grid(axis='y', linestyle=':', alpha=0.5)
        plt.tight_layout()
        plt.show(block=False)

    print("\nAll interactive loops compiled. Close all active figures to exit the Python thread process completely.")
    plt.show(block=True)

else:
    print("Optimization terminated with status code:", model.Status)
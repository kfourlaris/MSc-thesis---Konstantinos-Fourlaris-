import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from Stochastic_DA_running import config4
from Stochastic_DA_running.BiomassBoilerTest import BiomassBoilerTest
from Stochastic_DA_running.CHPTest import CHPTest
from Stochastic_DA_running.LSHPTest import LargeScaleHeatPumpTest
from Stochastic_DA_running.TESTest import PitThermalEnergyStorageTest

# --- STEP 0: PRE-CHECK CONFIGURATION FLOW ---
print(f"--- Running Stage 2 Joint 25-Scenario Market Optimization for: {config4.SELECTED_CITY} ---")
print(f"Locked Annuity Factor (CRF): {config4.ANNUITY_FACTOR:.4f}")
print(f"DAM Scenarios Loaded: {len(config4.SCENARIOS_DA)} ({config4.SCENARIOS_DA})")
print(f"Balancing Scenarios Loaded: {len(config4.SCENARIOS_BAL)} ({config4.SCENARIOS_BAL})")
print(f"Total 15-Minute Timesteps: {len(config4.HEAT_DEMAND_15MIN)} intervals")
print(f"Average Heating COP: {sum(config4.COP_VEC_15MIN) / 35040:.2f}")
print(f"Average Cooling COP: {sum(config4.COP_COOL_VEC_15MIN) / 35040:.2f}")

# --- STEP 1: INITIALIZE GUROBI MULTI-SCENARIO ENVIRONMENT ---
model = gp.Model("Stage2_15Min_Joint_Stochastic_Optimization")
model.setParam('MIPGap', 0.1)  # Set to a robust 4% gap to accommodate 25 scenarios smoothly

timesteps_15min = range(35040)  # High-resolution time horizon (8760 * 4)

# --- STEP 2: INSTANTIATE TECHNOLOGIES ---
boiler = BiomassBoilerTest("BB")
chp = CHPTest("CHP")
lshp = LargeScaleHeatPumpTest("HP")
tes = PitThermalEnergyStorageTest("TES")

technologies = [boiler, chp, lshp]

# --- STEP 3: LOOP 25 JOINT SCENARIOS TO BUILD VARIABLES & CONSTRAINTS ---
print("\nBuilding matrix decision layers across 25 joint scenario states...")
heat_demand_np = np.array(config4.HEAT_DEMAND_15MIN)
cool_demand_np = np.array(config4.COOLING_DEMAND_15MIN)

for s_da in config4.SCENARIOS_DA:
    for s_bal in config4.SCENARIOS_BAL:
        s_joint = f"{s_da}_{s_bal}"

        # 1. Variables and structural limits (Instant execution)
        for tech in technologies:
            tech.add_variables(model, timesteps_15min, joint_scenario=s_joint)
        tes.add_variables(model, timesteps_15min, joint_scenario=s_joint)

        boiler.add_constraints(model, timesteps_15min, joint_scenario=s_joint)
        chp.add_constraints(model, timesteps_15min, joint_scenario=s_joint)
        lshp.add_constraints(model, timesteps_15min, config4.COP_VEC_15MIN, config4.COP_COOL_VEC_15MIN,
                             joint_scenario=s_joint)
        tes.add_constraints(model, timesteps_15min, lshp, config4.PEAK_DEMAND_KW, joint_scenario=s_joint)

        # 2. Vectorized Network Demand Equations (Instant matrix creation)
        model.addConstr((boiler.V_heat[s_joint] + chp.V_heat[s_joint] + lshp.V_heat_DA[s_joint] + tes.V_disch[s_joint] -
                         tes.U_charge[s_joint]) * 0.25 == heat_demand_np, name=f"Heat_Balance_{s_joint}")
        model.addConstr(lshp.V_cool[s_joint] * 0.25 == cool_demand_np, name=f"Cool_Balance_{s_joint}")

# --- STEP 4: OBJECTIVE FUNCTION MATRIX DOT PRODUCTS ---
expected_operational_cost = 0

for s_da in config4.SCENARIOS_DA:
    prob_da = config4.PROBABILITY_DA[s_da]
    dam_prices = np.array(config4.DYNAMIC_ELEC_PRICES_15MIN_SCENARIO[s_da])

    for s_bal in config4.SCENARIOS_BAL:
        prob_bal = config4.PROBABILITY_BAL[s_bal]
        joint_prob = prob_da * prob_bal
        s_joint = f"{s_da}_{s_bal}"

        # Matrix dot products using `@` operator (Extremely fast, handles all loops inside C)
        biomass_spending = boiler.U_biomass[s_joint].sum() * (0.25 * config4.FUEL_PRICES["biomass"])
        gas_spending = chp.U_gas[s_joint] @ np.array(config4.FUEL_PRICES["gas"]) * 0.25
        elec_spending = lshp.U_elec[s_joint] @ dam_prices * 0.25

        baseline_revenue = chp.V_elec[s_joint].sum() * (0.25 * config4.ELEC_REVENUE)
        bal_revenue_up = lshp.V_balancing_up[s_joint] @ np.array(config4.BAL_PRICE_UP[s_bal]) * 0.25
        bal_cost_down = lshp.V_balancing_down[s_joint] @ np.array(config4.BAL_PRICE_DOWN[s_bal]) * 0.25

        expected_operational_cost += joint_prob * (
                    biomass_spending + gas_spending + elec_spending - baseline_revenue - bal_revenue_up + bal_cost_down)

model.setObjective(total_fixed_annual_investment + expected_operational_cost, GRB.MINIMIZE)

# --- STEP 5: SOLVE MODEL & REPORT STOCHASTIC SUMMARY ---
print("\nInvoking Gurobi Optimizer for Joint System Network...")
model.optimize()

if model.Status == GRB.OPTIMAL:

    # Post-process probability-weighted balancing arbitrage results across all 25 joint scenario states
    total_expected_bal_up = 0
    total_expected_bal_down = 0

    for s_da in config4.SCENARIOS_DA:
        prob_da = config4.PROBABILITY_DA[s_da]
        for s_bal in config4.SCENARIOS_BAL:
            prob_bal = config4.PROBABILITY_BAL[s_bal]
            joint_prob = prob_da * prob_bal
            s_joint = f"{s_da}_{s_bal}"

            # Extract values per joint scenario block
            val_up = sum(
                lshp.V_balancing_up[t, s_joint].X * config4.BAL_PRICE_UP[s_bal][t] for t in timesteps_15min) * 0.25
            val_down = sum(
                lshp.V_balancing_down[t, s_joint].X * config4.BAL_PRICE_DOWN[s_bal][t] for t in timesteps_15min) * 0.25

            total_expected_bal_up += joint_prob * val_up
            total_expected_bal_down += joint_prob * val_down

    calculated_baseline_cost = model.ObjVal - total_fixed_annual_investment + total_expected_bal_up - total_expected_bal_down
    net_balancing_opex = - total_expected_bal_up + total_expected_bal_down

    print("\n" + "=" * 65)
    print("        OPTIMIZATION SUCCESSFUL - STAGE 2 JOINT BREAKDOWN RESULTS")
    print("=" * 65)
    print(f"Unified Expected Total Annual Cost (TAC):      {model.ObjVal:15,.2f} Euro")
    print("-" * 65)
    print(f" -> Fixed Capital & Maintenance Overhead:      {total_fixed_annual_investment:15,.2f} Euro")
    print(f" -> Expected Multi-Scenario Baseline Cost:     {calculated_baseline_cost:15,.2f} Euro")
    print(f" -> Balancing Participation Net Opex:          {net_balancing_opex:15,.2f} Euro")
    print("=" * 65)

    # =========================================================================
    # --- LEVELIZED COST OF DHCN ENERGY ---
    # =========================================================================
    print("\n" + "=" * 55)
    print("  FINANCIAL ANALYSIS: LEVELIZED COST OF DHCN ENERGY")
    print("=" * 55)

    nominator_annual_cost_eur = model.ObjVal
    annual_heat_demand_kwh = sum(config4.HEAT_DEMAND_15MIN)
    annual_cool_demand_kwh = sum(config4.COOLING_DEMAND_15MIN)
    total_annual_energy_demand_kwh = annual_heat_demand_kwh + annual_cool_demand_kwh
    total_annual_energy_demand_mwh = total_annual_energy_demand_kwh / 1000

    lcoe_dhcn_eur_kwh = nominator_annual_cost_eur / total_annual_energy_demand_kwh
    lcoe_dhcn_eur_mwh = nominator_annual_cost_eur / total_annual_energy_demand_mwh

    print(f"Total Net Annual Cost (Nominator):     {nominator_annual_cost_eur:,.2f} EUR/year")
    print(f"Annual Network Thermal Demand Met:     {total_annual_energy_demand_mwh:,.2f} MWh/year")
    print("-" * 55)
    print(f"Levelized Cost of DHCN Energy:")
    print(f" -> {lcoe_dhcn_eur_kwh:.6f} EUR/kWh")
    print(f" -> {lcoe_dhcn_eur_mwh:.2f} EUR/MWh")
    print("=" * 55 + "\n")

    # =========================================================================
    # --- STEP 6: PLOTTING FOR RESULTS VALIDATION (ZOOMED TO ONE SPECIFIC WEEK) ---
    # =========================================================================
    # Track the exact requested intersection intersection: S1 from DAM vs S1 from Balancing
    target_scenario = 'S1_S1'
    start_t = 1152
    end_t = 2496
    week_timesteps = range(start_t, end_t)

    print(f"\nExtracting and rendering LSHP operational curves for Joint Intersection: {target_scenario}...")
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

    # --- PRINT QUANTITATIVE VALUES FOR EXAMINED WEEK ---
    print("\n" + "=" * 95)
    print(f"      QUARTERLY OPERATIONAL DISPATCH DATA FOR LSHP (JOINT SCENARIO {target_scenario})")
    print("=" * 95)
    print(
        f"{'Timestep':<10} | {'Day of Year':<12} | {'Hour':<8} | {'Baseline (kW)':<15} | {'Bal_Up (kW)':<12} | {'Bal_Down (kW)':<13} | {'Net_Import (kW)':<15}")
    print("-" * 95)

    for idx, row in df_plot.iterrows():
        t_val = int(row['Timestep'])
        total_hours_passed = t_val / 4
        day_of_year = int(total_hours_passed // 24) + 1
        hour_of_day = int(total_hours_passed % 24)
        minute_of_hour = int((t_val % 4) * 15)
        time_str = f"{hour_of_day:02d}:{minute_of_hour:02d}"

        print(
            f"{t_val:<10} | Day {day_of_year:<8} | {time_str:<8} | {row['Baseline_Import']:<15,.2f} | {row['Balancing_Up']:<12,.2f} | {row['Balancing_Down']:<13,.2f} | {row['Net_Electrical_Import']:<15,.2f}")
    print("=" * 95 + "\n")

    plt.figure(figsize=(15, 6))
    plt.plot(df_plot['Timestep'], df_plot['Baseline_Import'], label='Baseline Import ($U_{elec}$)',
             color='gray', linestyle='--', alpha=0.7, linewidth=1.5)
    plt.plot(df_plot['Timestep'], df_plot['Balancing_Down'], label='Balancing Down ($V_{bal,down}$ - Consuming More)',
             color='darkred', alpha=0.8, linewidth=1.5)
    plt.plot(df_plot['Timestep'], df_plot['Balancing_Up'], label='Balancing Up ($V_{bal,up}$ - Consuming Less)',
             color='darkgreen', alpha=0.8, linewidth=1.5)
    plt.plot(df_plot['Timestep'], df_plot['Net_Electrical_Import'], label='Net Physical Grid Import',
             color='blue', linewidth=2.0, linestyle='-')

    plt.title(f'LSHP Electrical Dispatch Validation | Joint Scenario {target_scenario} (Timesteps {start_t} - {end_t})',
              fontsize=13, fontweight='bold')
    plt.xlabel('15-Minute Operational Intervals', fontsize=11)
    plt.ylabel('Electrical Power Demand (kW)', fontsize=11)
    plt.xlim(start_t, end_t)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='none')
    plt.tight_layout()
    plt.show(block=False)

    # =========================================================================
    # --- STEP 7: PLOTTING FOR RESULTS VALIDATION (MULTI-WEEK COMPARISON) ---
    # =========================================================================
    validation_periods = [
        (1152, 2496, "Winter Week (Jan)"),
        (20640, 21984, "Summer Week (Jul)")
    ]

    print(f"\n" + "=" * 60)
    print(f" GENERATING STAGE 2 MULTI-PERIOD SYSTEM DISPATCH FIGURES")
    print(f" Isolated Joint Scenario Profile: {target_scenario}")
    print("=" * 60)

    for start_t, end_t, period_label in validation_periods:
        week_timesteps = range(start_t, end_t)
        hour_range = [t / 4 for t in week_timesteps]

        print(f"\nProcessing visual matrices for: {period_label}")

        # --- DATA EXTRACTION & POWER NORMALIZATION (kW to MW) ---
        v_boiler_mw = [boiler.V_heat[t, target_scenario].X / 1000 for t in week_timesteps]
        v_chp_mw = [chp.V_heat[t, target_scenario].X / 1000 for t in week_timesteps]
        v_lshp_da_mw = [lshp.V_heat_DA[t, target_scenario].X / 1000 for t in week_timesteps]
        v_lshp_bal_mw = [lshp.V_heat_bal_down[t, target_scenario].X / 1000 for t in week_timesteps]

        heat_demand_mw = [config4.HEAT_DEMAND_15MIN[t] / 0.25 / 1000 for t in week_timesteps]
        v_cool_mw = [lshp.V_cool[t, target_scenario].X / 1000 for t in week_timesteps]
        cooling_demand_mw = [config4.COOLING_DEMAND_15MIN[t] / 0.25 / 1000 for t in week_timesteps]

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

        plt.title(f'District Heating Dispatch Stack — {period_label} [Joint Scenario: {target_scenario}]', fontsize=12,
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
        ax1.set_title(f'TES Operation & State of Charge Tracking — {period_label} [Joint Scenario: {target_scenario}]',
                      fontsize=12, fontweight='bold')
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
        plt.title(f'District Cooling Network Dispatch — {period_label} [Joint Scenario: {target_scenario}]',
                  fontsize=12, fontweight='bold')
        plt.xlabel('Time Horizon (Hours of the Year)', fontsize=11)
        plt.ylabel('Cooling Power Level (MW)', fontsize=11)
        plt.xlim(start_t / 4, end_t / 4)
        plt.legend(loc='upper right', frameon=True, facecolor='white', edgecolor='none')
        plt.grid(axis='y', linestyle=':', alpha=0.5)
        plt.tight_layout()
        plt.show(block=False)

    print("\nAll interactive loops compiled. Close all active figures to exit the process completely.")
    plt.show(block=True)

else:
    print("Optimization terminated with status code:", model.Status)
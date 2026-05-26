import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd

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
model.setParam('MIPGap', 0.05)  # Maintain identical performance gap target

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
else:
    print("Optimization terminated with status code:", model.Status)
from gurobipy import GRB
import config2
from second_stage_optimization.config2 import HEAT_DEMAND_15MIN


class CHP15Min:
    def __init__(self, name, efficiency_el=0.35, efficiency_th=0.65, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Combined Heat and Power (CHP) plant.
        Reads installed footprint and financial overhead directly from config.py

        Note: self.P_cap tracks the installed ELECTRICAL capacity (kW_el).
        """
        self.name = name
        self.eta_el = efficiency_el
        self.eta_th = efficiency_th
        self.delta = min_load_fraction

        # Pull technical details from the config file
        tech_data = config2.INSTALLED_TECH["CHP"]
        self.P_cap = tech_data["P_cap"]  # Fixed electrical size (kW_el)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config2.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, scenario)
        self.y_on = {}  # Binary ON/OFF scheduling marker
        self.V_elec = {}  # Output baseline electricity generation rate (kW)
        self.V_heat = {}  # Output baseline thermal generation rate (kW)
        self.U_gas = {}  # Input natural gas fuel consumption rate (kW)

    def add_variables(self, model, timesteps_15min, scenario):
        """
        Populates the operational variables for a single specified scenario block.
        """
        for t in timesteps_15min:
            self.y_on[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_{self.name}_t{t}_{scenario}"
            )
            self.V_elec[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_E_{self.name}_t{t}_{scenario}"
            )
            self.V_heat[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_{self.name}_t{t}_{scenario}"
            )
            self.U_gas[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_G_{self.name}_t{t}_{scenario}"
            )

    def add_constraints(self, model, timesteps_15min, heat_demand_15min, scenario):
        """
        Enforces 15-minute constraints like in the first stage optimization.
        """
        for t in timesteps_15min:
            # 1. Performance Constraints (Dual Output)
            model.addConstr(
                self.V_elec[t, scenario] == self.U_gas[t, scenario] * self.eta_el,
                name=f"perf_el_{self.name}_t{t}_{scenario}"
            )
            model.addConstr(
                self.V_heat[t, scenario] == self.U_gas[t, scenario] * self.eta_th,
                name=f"perf_th_{self.name}_t{t}_{scenario}"
            )

            # 2. UPPER BOUND BASED ON HEAT PRODUCTION
            model.addConstr(
                self.V_heat[t, scenario] <= self.P_cap * self.y_on[t, scenario],
                name=f"up_bound_fixed_P_{self.name}_t{t}_{scenario}"
            )

            # 3. LOWER BOUND BASED ON HEAT PRODUCTION
            model.addConstr(
                self.V_heat[t, scenario] >= self.delta * self.P_cap * self.y_on[t, scenario],
                name=f"low_bound_fixed_P_{self.name}_t{t}_{scenario}"
            )

            # 4. Last CONSTRAINT: CAP CHP HEAT PRODUCTION TO TOWN DEMAND
            demand_kw = heat_demand_15min[t] / 0.25
            model.addConstr(
                self.V_heat[t, scenario] <= demand_kw,
                name=f"chp_heat_cap_demand_{self.name}_t{t}_{scenario}",
            )
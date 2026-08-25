from gurobipy import GRB
import config3


class CHP15Min2:
    def __init__(self, name, efficiency_el=0.35, efficiency_th=0.65, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Combined Heat and Power (CHP) plant.
        All variables here are scenario-independent (First-Stage / Day-Ahead).
        """
        self.name = name
        self.eta_el = efficiency_el
        self.eta_th = efficiency_th
        self.delta = min_load_fraction

        tech_data = config3.INSTALLED_TECH["CHP"]
        self.P_cap = tech_data["P_cap"]
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config3.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Baseline 15-min dictionaries tracked strictly by timestep 't'
        self.y_on = {}
        self.V_elec = {}
        self.V_heat = {}
        self.U_gas = {}

    def add_variables(self, model, timesteps_15min):
        """
        Populates the operational baseline variables once.
        """
        for t in timesteps_15min:
            self.y_on[t] = model.addVar(vtype=GRB.BINARY, name=f"y_{self.name}_t{t}")
            self.V_elec[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"V_E_{self.name}_t{t}")
            self.V_heat[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}_t{t}")
            self.U_gas[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"U_G_{self.name}_t{t}")

    def add_constraints(self, model, timesteps_15min, heat_demand_15min):
        """
        Enforces 15-minute structural baseline constraints once.
        """
        for t in timesteps_15min:
            # 1. Performance Constraints (Dual Output)
            model.addConstr(self.V_elec[t] == self.U_gas[t] * self.eta_el, name=f"perf_el_{self.name}_t{t}")
            model.addConstr(self.V_heat[t] == self.U_gas[t] * self.eta_th, name=f"perf_th_{self.name}_t{t}")

            # 2. Upper and Lower Bounds
            model.addConstr(self.V_heat[t] <= self.P_cap * self.y_on[t], name=f"up_bound_fixed_P_{self.name}_t{t}")
            model.addConstr(self.V_heat[t] >= self.delta * self.P_cap * self.y_on[t], name=f"low_bound_fixed_P_{self.name}_t{t}")

            # 3. Last CONSTRAINT: CAP CHP HEAT PRODUCTION TO TOWN DEMAND
            demand_kw = heat_demand_15min[t] / 0.25
            model.addConstr(
                self.V_heat[t] <= demand_kw,
                name=f"chp_heat_cap_demand_{self.name}_t{t}",
            )
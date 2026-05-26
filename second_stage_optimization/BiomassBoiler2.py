from gurobipy import GRB
import config2


class BiomassBoiler15Min:
    def __init__(self, name, efficiency=0.86, min_load_fraction=0.10):
        self.name = name
        self.eta = efficiency
        self.delta = min_load_fraction

        # Pull the data structures from the new config file
        tech_data = config2.INSTALLED_TECH["BiomassBoiler"]
        self.P_cap = tech_data["P_cap"]
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the absolute annualized investment/maintenance cost for this unit
        self.fixed_annual_cost = self.P_cap * (self.capex_per_kw * config2.ANNUITY_FACTOR + self.opex_per_kw)

        # Operational decision variables
        self.y_on = {}
        self.V_heat = {}
        self.U_biomass = {}

    def add_variables(self, model, timesteps_15min, scenario):
        """
        Addition of scenarios for stochasticity
        """
        for t in timesteps_15min:
            self.y_on[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_{self.name}_t{t}_{scenario}"
            )
            self.V_heat[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_{self.name}_t{t}_{scenario}"
            )
            self.U_biomass[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_B_{self.name}_t{t}_{scenario}"
            )

    def add_constraints(self, model, timesteps_15min, scenario):
        """
        Enforces 15-minute constraints like in the first stage optimization
        """
        for t in timesteps_15min:
            # 1. Performance: V_heat = U_biomass * eta (Instantaneous kW power conversion)
            model.addConstr(
                self.V_heat[t, scenario] == self.U_biomass[t, scenario] * self.eta,
                name=f"perf_{self.name}_t{t}_{scenario}"
            )

            # 2. UPPER BOUND: Bound operational generation by the locked plant parameter (P_cap)
            model.addConstr(
                self.V_heat[t, scenario] <= self.P_cap * self.y_on[t, scenario],
                name=f"up_bound_fixed_P_{self.name}_t{t}_{scenario}"
            )

            # 3. LOWER BOUND: Force minimum technical load restriction when active
            model.addConstr(
                self.V_heat[t, scenario] >= self.delta * self.P_cap * self.y_on[t, scenario],
                name=f"low_bound_fixed_P_{self.name}_t{t}_{scenario}"
            )
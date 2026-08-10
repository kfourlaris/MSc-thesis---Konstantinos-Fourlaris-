from gurobipy import GRB
import config3


class BiomassBoiler15Min2:
    def __init__(self, name, efficiency=0.86, min_load_fraction=0.10):
        self.name = name
        self.eta = efficiency
        self.delta = min_load_fraction

        # Pull the data structures from the new config file
        tech_data = config3.INSTALLED_TECH["BiomassBoiler"]
        self.P_cap = tech_data["P_cap"]
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the absolute annualized investment/maintenance cost for this unit
        self.fixed_annual_cost = self.P_cap * (self.capex_per_kw * config3.ANNUITY_FACTOR + self.opex_per_kw)

        # Operational decision variables (Scenario index removed)
        self.y_on = {}
        self.V_heat = {}
        self.U_biomass = {}

    def add_variables(self, model, timesteps_15min):
        """
        Populates the first-stage, scenario-independent baseline variables once.
        """
        for t in timesteps_15min:
            self.y_on[t] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_{self.name}_t{t}"
            )
            self.V_heat[t] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_{self.name}_t{t}"
            )
            self.U_biomass[t] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_B_{self.name}_t{t}"
            )

    def add_constraints(self, model, timesteps_15min, heat_demand_15min):
        """
        Enforces structural baseline constraints invariant to scenarios.
        """
        for t in timesteps_15min:
            # 1. Performance: V_heat = U_biomass * eta (Instantaneous kW power conversion)
            model.addConstr(
                self.V_heat[t] == self.U_biomass[t] * self.eta,
                name=f"perf_{self.name}_t{t}"
            )

            # 2. UPPER BOUND: Bound operational generation by the locked plant parameter (P_cap)
            model.addConstr(
                self.V_heat[t] <= self.P_cap * self.y_on[t],
                name=f"up_bound_fixed_P_{self.name}_t{t}"
            )

            # 3. LOWER BOUND: Force minimum technical load restriction when active
            model.addConstr(
                self.V_heat[t] >= self.delta * self.P_cap * self.y_on[t],
                name=f"low_bound_fixed_P_{self.name}_t{t}"
            )

            # 4. Last CONSTRAINT: CAP BIOMASS HEAT PRODUCTION TO TOWN DEMAND
            demand_kw = heat_demand_15min[t] / 0.25
            model.addConstr(
                self.V_heat[t] <= demand_kw,
                name=f"chp_heat_bb_demand_{self.name}_t{t}",
            )

from Stochastic_DA_running import config4
from gurobipy import GRB

class BiomassBoilerTest:
    def __init__(self, name, efficiency=0.86, min_load_fraction=0.10):
        self.name = name
        self.eta = efficiency
        self.delta = min_load_fraction

        # Pull the data structures from the new config file
        tech_data = config4.INSTALLED_TECH["BiomassBoiler"]
        self.P_cap = tech_data["P_cap"]
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the absolute annualized investment/maintenance cost for this unit
        self.fixed_annual_cost = self.P_cap * (self.capex_per_kw * config4.ANNUITY_FACTOR + self.opex_per_kw)

        # Operational decision variables mapped to a joint scenario tracking tuple/string
        self.y_on = {}
        self.V_heat = {}
        self.U_biomass = {}

    def add_variables(self, model, timesteps_15min, joint_scenario):
        # Allocates all 35,040 variables instantly in one shot
        self.y_on[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY, name=f"y_{self.name}_{joint_scenario}")
        self.V_heat[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"V_H_{self.name}_{joint_scenario}")
        self.U_biomass[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                       name=f"U_B_{self.name}_{joint_scenario}")

    def add_constraints(self, model, timesteps_15min, joint_scenario):
        # Vectorized array math replaces 35,040 individual constraint lines
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.U_biomass[joint_scenario] * self.eta), '=', 0.0,
                         name=f"perf_{self.name}_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.P_cap * self.y_on[joint_scenario]), '<=', 0.0,
                         name=f"up_{self.name}_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.delta * self.P_cap * self.y_on[joint_scenario]),
                         '>=', 0.0, name=f"low_{self.name}_{joint_scenario}")
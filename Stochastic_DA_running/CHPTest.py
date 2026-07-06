from Stochastic_DA_running import config4
from gurobipy import GRB


class CHPTest:
    def __init__(self, name, efficiency_el=0.35, efficiency_th=0.65, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Combined Heat and Power (CHP) plant.
        Reads installed footprint and financial overhead directly from config.py

        Note: self.P_cap tracks the installed THERMAL capacity (kW_th) used as the upper bound for heat production.
        """
        self.name = name
        self.eta_el = efficiency_el
        self.eta_th = efficiency_th
        self.delta = min_load_fraction

        # Pull technical details from your configuration dictionary
        tech_data = config4.INSTALLED_TECH["CHP"]
        self.P_cap = tech_data["P_cap"]  # Fixed capacity size (kW)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config4.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, joint_scenario)
        self.y_on = {}  # Binary ON/OFF scheduling marker
        self.V_elec = {}  # Output baseline electricity generation rate (kW)
        self.V_heat = {}  # Output baseline thermal generation rate (kW)
        self.U_gas = {}  # Input natural gas fuel consumption rate (kW)

    def add_variables(self, model, timesteps_15min, joint_scenario):
        self.y_on[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY, name=f"y_{self.name}_{joint_scenario}")
        self.V_elec[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"V_E_{self.name}_{joint_scenario}")
        self.V_heat[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"V_H_{self.name}_{joint_scenario}")
        self.U_gas[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                   name=f"U_G_{self.name}_{joint_scenario}")

    def add_constraints(self, model, timesteps_15min, joint_scenario):
        model.addMConstr(None, self.V_elec[joint_scenario] - (self.U_gas[joint_scenario] * self.eta_el), '=', 0.0,
                         name=f"perf_el_{self.name}_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.U_gas[joint_scenario] * self.eta_th), '=', 0.0,
                         name=f"perf_th_{self.name}_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.P_cap * self.y_on[joint_scenario]), '<=', 0.0,
                         name=f"up_{self.name}_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.delta * self.P_cap * self.y_on[joint_scenario]),
                         '>=', 0.0, name=f"low_{self.name}_{joint_scenario}")
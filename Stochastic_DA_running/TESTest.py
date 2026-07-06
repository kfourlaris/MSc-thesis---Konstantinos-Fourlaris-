from Stochastic_DA_running import config4
from gurobipy import GRB


class PitThermalEnergyStorageTest:
    def __init__(self, name, loss_rate=0.0005, eta_charge=0.9, eta_disch=0.9):
        """
        Second-Stage 15-Minute Operational Class for Pit Thermal Energy Storage (TES).
        Reads installed footprint and financial overhead directly from config.py
        """
        self.name = name
        self.eta_c = eta_charge
        self.eta_d = eta_disch

        # Scale the hourly self-discharge loss rate to a 15-minute resolution
        # (1 - loss_rate_15min) = (1 - loss_rate_hourly)^(1/4)
        self.lam_15min = 1 - ((1 - loss_rate) ** 0.25)

        # Pull technical details from your configuration dictionary
        tech_data = config4.INSTALLED_TECH["TES"]
        self.E_cap = tech_data["E_cap"]  # Fixed energy capacity size (kWh)
        self.capex_per_kwh = tech_data["capex_per_kwh"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.E_cap * (
                self.capex_per_kwh * config4.ANNUITY_FACTOR
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, joint_scenario)
        self.E_state = {}  # Stored Energy level inventory (kWh)
        self.U_charge = {}  # Charging thermal power rate (kW)
        self.V_disch = {}  # Discharging thermal power rate (kW)
        self.C_tech = {}  # Binary marker: 1 if charging, 0 if discharging

    def add_variables(self, model, timesteps_15min, joint_scenario):
        self.E_state[joint_scenario] = model.addMVar(shape=35040, lb=0.0, ub=self.E_cap, vtype=GRB.CONTINUOUS,
                                                     name=f"E_state_{self.name}_{joint_scenario}")
        self.U_charge[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                      name=f"U_charge_{self.name}_{joint_scenario}")
        self.V_disch[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                     name=f"V_disch_{self.name}_{joint_scenario}")
        self.C_tech[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY,
                                                    name=f"C_tech_{self.name}_{joint_scenario}")

    def add_constraints(self, model, timesteps_15min, hp_15min_instance, peak_demand_kw, joint_scenario):
        # 1. Immediate array limits
        model.addMConstr(None, self.U_charge[joint_scenario] - hp_15min_instance.V_heat_bal_down[joint_scenario] -
                         hp_15min_instance.V_heat_DA[joint_scenario], '<=', 0.0, name=f"chg_src_{joint_scenario}")
        model.addMConstr(None, self.U_charge[joint_scenario] - (hp_15min_instance.P_cap * self.C_tech[joint_scenario]),
                         '<=', 0.0, name=f"chg_lim_{joint_scenario}")
        model.addMConstr(None, self.V_disch[joint_scenario] - (peak_demand_kw * (1 - self.C_tech[joint_scenario])),
                         '<=', 0.0, name=f"dis_lim_{joint_scenario}")

        # 2. Sequential Inventory loop (Fast execution on matrix slices)
        # Periodicity link
        model.addConstr(self.E_state[joint_scenario][0] == self.E_state[joint_scenario][35039],
                        name=f"periodicity_{self.name}_{joint_scenario}")

        # State dynamics tracking
        for t in range(1, 35040):
            model.addConstr(
                self.E_state[joint_scenario][t] == (1 - self.lam_15min) * self.E_state[joint_scenario][t - 1] +
                (self.eta_c * self.U_charge[joint_scenario][t] * 0.25) -
                ((self.V_disch[joint_scenario][t] / self.eta_d) * 0.25),
                name=f"inv_balance_{self.name}_t{t}_{joint_scenario}"
            )
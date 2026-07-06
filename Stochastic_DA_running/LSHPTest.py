from Stochastic_DA_running import config4
from gurobipy import GRB
import numpy as np

class LargeScaleHeatPumpTest:
    def __init__(self, name, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Large-Scale Heat Pump.
        Reads installed footprint and financial overhead directly from config.py

        Note: self.P_cap tracks the installed THERMAL capacity (kW_th).
        """
        self.name = name
        self.delta = min_load_fraction

        # Pull technical details from your configuration dictionary
        tech_data = config4.INSTALLED_TECH["LargeScaleHeatPump"]
        self.P_cap = tech_data["P_cap"]  # Fixed thermal size (kW_th)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config4.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, joint_scenario)
        self.y_on = {}  # Binary operational state
        self.y_heat = {}  # Binary active heating mode
        self.y_cool = {}  # Binary active cooling mode
        self.V_heat = {}  # Output heat power rate (kW_th)
        self.V_heat_DA = {} # Output heat based on the electricity bought in the DAM
        self.V_heat_bal_down = {} # Output heat based on the electricity bought in the BM
        self.V_cool = {}  # Output cooling power rate (kW_cool)
        self.U_elec = {}  # Baseline input electricity power rate (kW_el)

        # Separate Up and Down capacity tracking variables (kW)
        self.V_balancing_up = {} # LSHP consumes less
        self.V_balancing_down = {} # LSHP consumes more
        self.b_market_dir = {} # 1 if bidding Downward, 0 if bidding Upward

    def add_variables(self, model, timesteps_15min, joint_scenario):
        # Allocating all 35,040 steps simultaneously in C
        self.y_on[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY, name=f"y_{self.name}_{joint_scenario}")
        self.y_heat[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY,
                                                    name=f"y_heat_{self.name}_{joint_scenario}")
        self.y_cool[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY,
                                                    name=f"y_cool_{self.name}_{joint_scenario}")

        self.V_heat[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"V_H_{self.name}_{joint_scenario}")
        self.V_heat_DA[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                       name=f"V_H_DA_{self.name}_{joint_scenario}")
        self.V_heat_bal_down[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                             name=f"V_H_bal_down_{self.name}_{joint_scenario}")
        self.V_cool[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"V_C_{self.name}_{joint_scenario}")
        self.U_elec[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                    name=f"U_E_{self.name}_{joint_scenario}")

        self.V_balancing_up[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                            name=f"V_bal_up_{self.name}_{joint_scenario}")
        self.V_balancing_down[joint_scenario] = model.addMVar(shape=35040, lb=0.0, vtype=GRB.CONTINUOUS,
                                                              name=f"V_bal_down_{self.name}_{joint_scenario}")
        self.b_market_dir[joint_scenario] = model.addMVar(shape=35040, vtype=GRB.BINARY,
                                                          name=f"b_market_dir_{self.name}_{joint_scenario}")

    def add_constraints(self, model, timesteps_15min, cop_vector_15min, cop_cool_vector_15min, joint_scenario):
        cop_h = np.array(cop_vector_15min)
        cop_c = np.array(cop_cool_vector_15min)
        max_elec_input = self.P_cap / cop_h

        # Vectorized linear constraints (Replaces 35,040 loop cycles with single array lines!)
        model.addMConstr(None, self.y_heat[joint_scenario] + self.y_cool[joint_scenario] - self.y_on[joint_scenario],
                         '<=', 0.0, name=f"exclusive_thermal_{joint_scenario}")

        # Net electrical bridge equation
        model.addMConstr(None,
                         (self.V_heat[joint_scenario] / cop_h) + (self.V_cool[joint_scenario] / cop_c) - self.U_elec[
                             joint_scenario] - self.V_balancing_down[joint_scenario] + self.V_balancing_up[
                             joint_scenario], '=', 0.0, name=f"bridge_{joint_scenario}")

        model.addMConstr(None, self.V_heat[joint_scenario] - self.V_heat_DA[joint_scenario] - self.V_heat_bal_down[
            joint_scenario], '=', 0.0, name=f"sum_heat_{joint_scenario}")
        model.addMConstr(None, self.V_heat_DA[joint_scenario] - (self.U_elec[joint_scenario] * cop_h), '<=', 0.0,
                         name=f"da_cap_{joint_scenario}")
        model.addMConstr(None, self.V_heat_bal_down[joint_scenario] - (self.V_balancing_down[joint_scenario] * cop_h),
                         '<=', 0.0, name=f"bal_down_cap_{joint_scenario}")

        # Market limitations
        model.addMConstr(None, self.V_balancing_up[joint_scenario] - self.U_elec[joint_scenario], '<=', 0.0,
                         name=f"bal_up_limit_{joint_scenario}")
        model.addMConstr(None, self.V_balancing_up[joint_scenario] - (self.V_heat_DA[joint_scenario] / cop_h), '<=',
                         0.0, name=f"bal_up_heat_{joint_scenario}")
        model.addMConstr(None, self.U_elec[joint_scenario] + self.V_balancing_down[joint_scenario] - (
                    max_elec_input * self.y_on[joint_scenario]), '<=', 0.0, name=f"bal_down_limit_{joint_scenario}")
        model.addMConstr(None, self.V_balancing_down[joint_scenario] - (2 * self.U_elec[joint_scenario]), '<=', 0.0,
                         name=f"proportional_cap_{joint_scenario}")

        # Directional Lockouts
        model.addMConstr(None,
                         self.V_balancing_down[joint_scenario] - (max_elec_input * self.b_market_dir[joint_scenario]),
                         '<=', 0.0, name=f"gate_down_{joint_scenario}")
        model.addMConstr(None, self.V_balancing_up[joint_scenario] - (
                    max_elec_input * (1 - self.b_market_dir[joint_scenario])), '<=', 0.0,
                         name=f"gate_up_{joint_scenario}")

        # Operational Bounds
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.P_cap * self.y_heat[joint_scenario]), '<=', 0.0,
                         name=f"up_heat_{joint_scenario}")
        model.addMConstr(None, self.V_heat[joint_scenario] - (self.delta * self.P_cap * self.y_heat[joint_scenario]),
                         '>=', 0.0, name=f"low_heat_{joint_scenario}")
        model.addMConstr(None, self.V_cool[joint_scenario] - (self.P_cap * self.y_cool[joint_scenario]), '<=', 0.0,
                         name=f"up_cool_{joint_scenario}")
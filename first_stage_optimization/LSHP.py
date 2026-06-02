from gurobipy import GRB

class LargeScaleHeatPump:
    def __init__(self, name, p_min_market=500, p_max_market=500000,
                 min_load_fraction=0.15, capex_per_kw_th=1700, opex_per_kw_th=34):
        """
        Args:
            p_min_market: Smallest available capacity (kW_th)
            p_max_market: Largest available capacity (kW_th)
            min_load_fraction: delta_k (e.g., 0.15 for 15% minimum thermal output)
            capex_per_kw_th: Investment cost per unit of thermal capacity (P_k) (Danish Energy Agency - Technology Data - Generation of Electricity and District Heating)
            opex_per_kw_th: Annual fixed maintenance cost per unit of capacity
        """
        self.name = name
        self.p_min = p_min_market
        self.p_max = p_max_market
        self.delta = min_load_fraction
        self.capex_per_kw = capex_per_kw_th
        self.opex_per_kw = opex_per_kw_th

        # Placeholders for Variables (Matching my proposal)
        self.P_cap = None      # Design size (P_k)
        self.b_select = None   # Tech selection (b_k)
        self.y_on = {}         # Hourly ON/OFF scheduling (y_k,t)
        self.y_heat = {}       # Hourly ON/OFF scheduling heat (y_k,H,t)
        self.y_cool = {}       # Hourly ON/OFF scheduling cool (y_k,C,t)
        self.V_heat = {}       # Output Heat (V_H,HP,t)
        self.V_cool = {}       # Output Cooling (V_C,HP,t)
        self.U_elec = {}       # Input Electricity (U_E,HP,t)

    def add_variables(self, model, timesteps):
        # Design Variables (Z)
        self.P_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"P_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables (X)
        self.y_on = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_{self.name}")
        self.y_heat = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_heat_{self.name}")
        self.y_cool = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_cool_{self.name}")
        self.V_heat = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}")
        self.V_cool = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_C_{self.name}")
        self.U_elec = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_E_{self.name}")

    def add_constraints(self, model, timesteps, cop_vector, cop_cool_vector):
        """
        Args:
            cop_vector: A list or dictionary of 8760 pre-calculated hourly COP values.
        """
        # 1. Market Size Limits (P_k,min <= P_k <= P_k,max)
        model.addConstr(self.P_cap >= self.b_select * self.p_min, name=f"market_min_{self.name}")
        model.addConstr(self.P_cap <= self.b_select * self.p_max, name=f"market_max_{self.name}")

        # Combined Loop for all hourly constraints
        for t in timesteps:
            # 2.a Ensure that unit is on if either mode is active
            model.addConstr(self.y_heat[t] <= self.y_on[t], name=f"on_heat_{t}")
            model.addConstr(self.y_cool[t] <= self.y_on[t], name=f"on_cool_{t}")

            # 2.b THE NEW LOGIC
            model.addConstr(
                self.V_heat[t] <= 40000 * self.y_cool[t] + self.P_cap * (1 - self.y_cool[t]),
                name=f"simultaneous_limit_{self.name}_{t}"
            )

            # 3. Performance constraint (The Electricity Bridge)
            # No generator expression here; we handle it one hour at a time
            model.addConstr(
                self.U_elec[t] == (self.V_heat[t] / cop_vector[t]) + (self.V_cool[t] / cop_cool_vector[t]),
                name=f"elec_balance_{self.name}_{t}"
            )

            # 3.1 HEATING: Upper & Lower Bounds
            model.addConstr(self.V_heat[t] <= self.y_heat[t] * self.p_max, name=f"up_bound_y_heat_{self.name}_{t}")
            model.addConstr(
                self.V_heat[t] >= self.delta * self.P_cap - (1 - self.y_heat[t]) * self.p_max,
                name=f"low_bound_heat_{self.name}_{t}"
            )

            # 3.2 COOLING: Upper & Lower Bounds
            model.addConstr(self.V_cool[t] <= self.P_cap, name=f"up_bound_P_cool_{self.name}_{t}")
            model.addConstr(self.V_cool[t] <= self.y_cool[t] * self.p_max, name=f"up_bound_y_cool_{self.name}_{t}")



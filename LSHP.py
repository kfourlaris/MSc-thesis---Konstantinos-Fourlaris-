from gurobipy import GRB

class LargeScaleHeatPump:
    def __init__(self, name, p_min_market=500, p_max_market=50000,
                 min_load_fraction=0.25, capex_per_kw_th=600, opex_per_kw_th=15):
        """
        Args:
            p_min_market: Smallest available capacity (kW_th)
            p_max_market: Largest available capacity (kW_th)
            min_load_fraction: delta_k (e.g., 0.15 for 15% minimum thermal output)
            capex_per_kw_th: Investment cost per unit of thermal capacity (P_k)
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
        self.V_heat = {}       # Output Heat (V_H,HP,t)
        self.U_elec = {}       # Input Electricity (U_E,HP,t)

    def add_variables(self, model, timesteps):
        # Design Variables (Z)
        self.P_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"P_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables (X)
        self.y_on = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_{self.name}")
        self.V_heat = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}")
        self.U_elec = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_E_{self.name}")

    def add_constraints(self, model, timesteps, cop_vector):
        """
        Args:
            cop_vector: A list or dictionary of 8760 pre-calculated hourly COP values.
        """
        # 1. Market Size Limits (P_k,min <= P_k <= P_k,max)
        model.addConstr(self.P_cap >= self.b_select * self.p_min, name=f"market_min_{self.name}")
        model.addConstr(self.P_cap <= self.b_select * self.p_max, name=f"market_max_{self.name}")

        # 2. Performance: V_H(t) = U_E(t) * COP(t)
        # Using the COP defined in cofig.py
        model.addConstrs(
            (self.V_heat[t] == self.U_elec[t] * cop_vector[t] for t in timesteps),
            name=f"perf_regression_cop_{self.name}"
        )

        # 3. Minimum & Maximum Operating Power (Linearized Big-M logic)
        for t in timesteps:
            # UPPER BOUND: Thermal output limited by design size and ON status
            model.addConstr(self.V_heat[t] <= self.P_cap, name=f"up_bound_P_{self.name}_{t}")
            model.addConstr(self.V_heat[t] <= self.y_on[t] * self.p_max, name=f"up_bound_y_{self.name}_{t}")

            # LOWER BOUND: Minimum load fraction delta
            # Enforces V_heat >= delta * P_cap when y=1
            model.addConstr(self.V_heat[t] >= self.delta * self.P_cap - (1 - self.y_on[t]) * self.p_max,
                            name=f"low_bound_{self.name}_{t}")


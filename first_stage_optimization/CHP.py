from gurobipy import GRB

class CHP:
    def __init__(self, name, efficiency_el=0.35, efficiency_th=0.65,
                 p_min_market=50, p_max_market=1000000,
                 min_load_fraction=0.15, capex_per_kw_el=0, opex_per_kw_el=60):
        """
        Args:
            efficiency_el: Electrical efficiency (eta_el) (https://www.futuremarketinsights.com/reports/combined-heat-and-power-chp-systems-market)
            efficiency_th: Thermal efficiency (eta_th) (https://www.futuremarketinsights.com/reports/combined-heat-and-power-chp-systems-market)
            p_min_market: Smallest capacity based on electrical output (kW_el) 50 KW
            p_max_market: Largest capacity based on electrical output (kW_el) 1 GW
            min_load_fraction: delta_k (fraction of rated electrical power)
        """
        self.name = name
        self.eta_el = efficiency_el
        self.eta_th = efficiency_th
        self.p_min = p_min_market
        self.p_max = p_max_market
        self.delta = min_load_fraction
        self.capex_per_kw = capex_per_kw_el #1400 EUR/KW
        self.opex_per_kw = opex_per_kw_el   #60 EUR/KW

        # Placeholders for Variables (Matching what is defined in my proposal)
        self.P_cap = None      # Design size in kW_el (P_k)
        self.b_select = None   # Tech selection (b_k)
        self.y_on = {}         # Hourly ON/OFF scheduling (y_k,t)
        self.V_elec = {}       # Output Electricity (V_E,k,t)
        self.V_heat = {}       # Output Heat (V_H,k,t)
        self.U_gas = {}        # Input Natural Gas (U_NG,k,t)

    def add_variables(self, model, timesteps):
        # Design Variables (Z)
        self.P_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"P_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables (X)
        self.y_on = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_{self.name}")
        self.V_elec = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_E_{self.name}")
        self.V_heat = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}")
        self.U_gas = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_G_{self.name}")

    def add_constraints(self, model, timesteps):
        # 1. Market Size Limits (P_k,min <= P_k <= P_k,max)
        model.addConstr(self.P_cap >= self.b_select * self.p_min, name=f"market_min_{self.name}")
        model.addConstr(self.P_cap <= self.b_select * self.p_max, name=f"market_max_{self.name}")

        # 2. Performance Constraints (Dual Output)
        # V_E = U_G * eta_el and V_H = U_G * eta_th
        model.addConstrs(
            (self.V_elec[t] == self.U_gas[t] * self.eta_el for t in timesteps),
            name=f"perf_el_{self.name}"
        )
        model.addConstrs(
            (self.V_heat[t] == self.U_gas[t] * self.eta_th for t in timesteps),
            name=f"perf_th_{self.name}"
        )

        # 3. Minimum & Maximum Operating Power (Based on Electrical Capacity)
        for t in timesteps:
            # UPPER BOUNDS
            # Heat output capped by installed capacity and ON status
            model.addConstr(self.V_heat[t] <= self.P_cap, name=f"up_bound_P_{self.name}_{t}")
            model.addConstr(self.V_heat[t] <= self.y_on[t] * self.p_max, name=f"up_bound_y_{self.name}_{t}")

            # LOWER BOUND (Minimum load fraction delta)
            # If y=1, V_elec >= delta * P_cap. If y=0, V_elec >= 0 (via Big-M)
            model.addConstr(self.V_heat[t] >= self.delta * self.P_cap - (1 - self.y_on[t]) * self.p_max,
                            name=f"low_bound_{self.name}_{t}")

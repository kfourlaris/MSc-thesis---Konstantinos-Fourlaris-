from gurobipy import GRB


class BiomassBoiler:
    def __init__(self, name, efficiency=0.85,
                 p_min_market=100, p_max_market=50000,
                 min_load_fraction=0.10, capex_per_kw=250, opex_per_kw=5):
        """
        Args:
            p_min_market: Smallest available boiler size (e.g., 100 kW)
            p_max_market: Largest available boiler size (e.g., 50 MW)
            min_load_fraction: delta_k (e.g., 0.10 for 10% idle/max load)
            capex_per_kw: Investment cost per unit of capacity
            opex_per_kw: Annual maintenance cost per unit of capacity
        """
        self.name = name
        self.eta = efficiency
        self.p_min = p_min_market
        self.p_max = p_max_market
        self.delta = min_load_fraction
        self.capex_per_kw = capex_per_kw
        self.opex_per_kw = opex_per_kw

        # Placeholders for Variables
        self.P_cap = None  # Design size (P_k)
        self.b_select = None  # Tech selection (b_k)
        self.y_on = {}  # Hourly ON/OFF scheduling (y_k,t)
        self.V_heat = {}  # Output (V,k,t)
        self.U_biomass = {}  # Input (U,k,t)

    def add_variables(self, model, timesteps):
        # Design Variables
        self.P_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"P_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables
        # y_on is the binary for: is the boiler running at hour t?
        self.y_on = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_{self.name}")
        self.V_heat = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}")
        self.U_biomass = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_B_{self.name}")

    def add_constraints(self, model, timesteps):
        # 1. Market Size Limits (P_k,min <= P_k <= P_k,max)
        # Only applies if the technology is selected (b_k = 1)
        model.addConstr(self.P_cap >= self.b_select * self.p_min, name=f"market_min_{self.name}")
        model.addConstr(self.P_cap <= self.b_select * self.p_max, name=f"market_max_{self.name}")

        # 2. Performance: V = U * eta
        model.addConstrs(
            (self.V_heat[t] == self.U_biomass[t] * self.eta for t in timesteps),
            name=f"perf_{self.name}"
        )

        # 3. Minimum & Maximum Operating Power (The core constraint)
        # delta_k * P_k <= U_t <= P_k (multiplied by y_t for ON/OFF)
        # Note: Because P_cap * y_on is non-linear, we use the proposed Gurobi's linearization
        for t in timesteps:
            # 1. UPPER BOUND: If y=1, V_heat <= P_cap. If y=0, V_heat <= 0.
            # This uses a Big-M (p_max_market) to handle the bilinear y * P_cap
            model.addConstr(self.V_heat[t] <= self.P_cap, name=f"up_bound_P_{self.name}_{t}")
            model.addConstr(self.V_heat[t] <= self.y_on[t] * self.p_max, name=f"up_bound_y_{self.name}_{t}")

            # 2. LOWER BOUND: If y=1, V_heat >= 0.1 * P_cap. If y=0, V_heat >= 0.
            # We use another Big-M to "turn off" the 10% requirement when y=0
            model.addConstr(self.V_heat[t] >= self.delta * self.P_cap - (1 - self.y_on[t]) * self.p_max,
                            name=f"low_bound_{self.name}_{t}")

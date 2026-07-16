from gurobipy import GRB


class LargeScaleChiller:
    def __init__(self, name, p_min_market=500, p_max_market=50000,
                 min_load_fraction=0, capex_per_kw_c=1700, opex_per_kw_c=34):
        """
        Args:
            p_min_market: Smallest available capacity (kW_cool)
            p_max_market: Largest available capacity (kW_cool)
            min_load_fraction: delta_k (0 in order to meet minimum cooling demand)
            capex_per_kw_c: Investment cost per unit of cooling capacity => Source: (https://latestcost.com/chiller-cost-per-ton-price-ranges-drivers/)
            opex_per_kw_c: Annual fixed maintenance cost per unit of cooling capacity
        """
        self.name = name
        self.p_min = p_min_market
        self.p_max = p_max_market
        self.delta = min_load_fraction
        self.capex_per_kw = capex_per_kw_c
        self.opex_per_kw = opex_per_kw_c

        # Placeholders for Variables
        self.P_cap = None  # Design cooling capacity (kW_cool)
        self.b_select = None  # Tech selection binary
        self.y_on = {}  # Hourly ON/OFF scheduling binary
        self.V_cool = {}  # Output Cooling (V_C,CH,t)
        self.U_elec = {}  # Input Electricity (U_E,CH,t)

    def add_variables(self, model, timesteps):
        # Design Variables
        self.P_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"P_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables
        self.y_on = model.addVars(timesteps, vtype=GRB.BINARY, name=f"y_on_{self.name}")
        self.V_cool = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_C_{self.name}")
        self.U_elec = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_E_{self.name}")

    def add_constraints(self, model, timesteps, cop_cool_vector):
        """
        Args:
            cop_cool_vector: A list or dictionary of 8760 pre-calculated hourly cooling COP values from the config file
        """
        # 1. Market Size Limits (P_min <= P_cap <= P_max)
        model.addConstr(self.P_cap >= self.b_select * self.p_min, name=f"market_min_{self.name}")
        model.addConstr(self.P_cap <= self.b_select * self.p_max, name=f"market_max_{self.name}")

        # Combined Loop for hourly operational constraints
        for t in timesteps:
            # 2. Performance constraint (Electricity consumption based on Cooling COP)
            model.addConstr(
                self.U_elec[t] == self.V_cool[t] / cop_cool_vector[t],
                name=f"elec_balance_{self.name}_{t}"
            )

            # 3. COOLING: Upper & Lower Bounds

            # Absolute maximum upper bound dictated by the chosen design capacity
            model.addConstr(self.V_cool[t] <= self.P_cap, name=f"up_bound_P_cool_{self.name}_{t}")

            # Operational upper bound link to the hourly ON/OFF state (Big-M approach using maximum market capacity)
            model.addConstr(self.V_cool[t] <= self.y_on[t] * self.p_max, name=f"up_bound_y_cool_{self.name}_{t}")

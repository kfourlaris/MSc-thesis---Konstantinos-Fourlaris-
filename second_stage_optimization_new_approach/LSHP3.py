class LargeScaleHeatPump15Min_new:
    def __init__(self, name, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Large-Scale Heat Pump.
        Reads installed footprint and financial overhead directly from config_installed.py

        Note: self.P_cap tracks the installed THERMAL capacity (kW_th).
        """
        self.name = name
        self.delta = min_load_fraction

        # Pull technical details from your configuration dictionary
        tech_data = config2.INSTALLED_TECH["LargeScaleHeatPump"]
        self.P_cap = tech_data["P_cap"]  # Fixed thermal size (kW_th)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config2.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, scenario)
        self.y_on = {}  # Binary operational state
        self.y_heat = {}  # Binary active heating mode
        self.y_cool = {}  # Binary active cooling mode
        self.V_heat = {}  # Output heat power rate (kW_th)
        self.V_heat_DA = {}
        self.V_heat_bal_down = {}
        self.V_cool = {}  # Output cooling power rate (kW_cool)
        self.U_elec = {}  # Baseline input electricity power rate (kW_el)

        # Separate Up and Down capacity tracking variables (kW)
        self.V_balancing_up = {} #LSHP consumes less
        self.V_balancing_down = {} #LSHP consumes more
        self.b_market_dir = {} # 1 if bidding Downward, 0 if bidding Upward

    def add_variables(self, model, timesteps_15min, scenario):
        """
        Populates the operational variables.
        Notice that DA/Baseline variables are now created outside the scenario loop,
        or checked so they are only created ONCE.
        """
        for t in timesteps_15min:
            # --- FIRST-STAGE VARIABLES (Independent of Scenario) ---
            # We use a try/except or an if-check to ensure these are only added ONCE,
            # not repeated for every scenario.
            if (t, "DA") not in self.U_elec:
                self.y_on[t] = model.addVar(vtype=GRB.BINARY, name=f"y_{self.name}_t{t}")
                self.y_heat[t] = model.addVar(vtype=GRB.BINARY, name=f"y_heat_{self.name}_t{t}")
                self.y_cool[t] = model.addVar(vtype=GRB.BINARY, name=f"y_cool_{self.name}_t{t}")
                self.U_elec[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"U_E_{self.name}_t{t}")
                self.V_heat_DA[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_DA_{self.name}_t{t}")
                self.V_cool[t] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"V_C_{self.name}_t{t}")

                # Marker so we know DA is built
                self.U_elec[t, "DA"] = True

                # --- SECOND-STAGE VARIABLES (Dependent on Scenario) ---
            self.V_heat[t, scenario] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"V_H_{self.name}_t{t}_{scenario}")
            self.V_heat_bal_down[t, scenario] = model.addVar(lb=0, vtype=GRB.CONTINUOUS,
                                                             name=f"V_H_bal_down_{self.name}_t{t}_{scenario}")
            self.V_balancing_up[t, scenario] = model.addVar(lb=0, vtype=GRB.CONTINUOUS,
                                                            name=f"V_bal_up_{self.name}_t{t}_{scenario}")
            self.V_balancing_down[t, scenario] = model.addVar(lb=0, vtype=GRB.CONTINUOUS,
                                                              name=f"V_bal_down_{self.name}_t{t}_{scenario}")
            self.b_market_dir[t, scenario] = model.addVar(vtype=GRB.BINARY,
                                                          name=f"b_market_dir_{self.name}_t{t}_{scenario}")

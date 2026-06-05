from gurobipy import GRB
import config2

class LargeScaleHeatPump15Min:
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
        Populates the operational variables for a single specified scenario block.
        """
        for t in timesteps_15min:
            self.y_on[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_{self.name}_t{t}_{scenario}"
            )
            self.y_heat[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_heat_{self.name}_t{t}_{scenario}"
            )
            self.y_cool[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_cool_{self.name}_t{t}_{scenario}"
            )
            self.V_heat[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_{self.name}_t{t}_{scenario}"
            )

            self.V_heat_DA[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_DA_{self.name}_t{t}_{scenario}"
            )

            self.V_heat_bal_down[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_bal_down_{self.name}_t{t}_{scenario}"
            )

            self.V_cool[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_C_{self.name}_t{t}_{scenario}"
            )
            self.U_elec[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_E_{self.name}_t{t}_{scenario}"
            )

            self.V_balancing_up[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_bal_up_{self.name}_t{t}_{scenario}"
            )

            self.V_balancing_down[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_bal_down_{self.name}_t{t}_{scenario}"
            )

            self.b_market_dir[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"b_market_dir_{self.name}_t{t}_{scenario}"
            )


    def add_constraints(self, model, timesteps_15min, cop_vector_15min, cop_cool_vector_15min, scenario):
        """
        Enforces 15-minute technology constraints with strict directional binary market lockout rules.
        """
        for t in timesteps_15min:
            # --- 0. COMMITMENT AND SCHEDULING MODE SWITCHES ---
            model.addConstr(self.y_heat[t, scenario] + self.y_cool[t, scenario] <= self.y_on[t, scenario],
                            name=f"exclusive_thermal_mode_{self.name}_t{t}_{scenario}")

            # --- 1. THE NET ELECTRICAL REAL-TIME IMPORT DEFINITION ---
            net_electrical_input = self.U_elec[t, scenario] + self.V_balancing_down[t, scenario] - self.V_balancing_up[
                t, scenario]

            # --- 2. PERFORMANCE CONSTRAINTS (THE TRUE THERMODYNAMIC BRIDGE) ---
            model.addConstr(self.V_heat[t, scenario] == net_electrical_input * cop_vector_15min[t],
                            name=f"net_electrical_thermal_bridge_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_heat[t, scenario] == self.V_heat_DA[t, scenario] + self.V_heat_bal_down[t, scenario],
                            name=f"thermal_output_summation_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_heat_DA[t, scenario] <= self.U_elec[t, scenario] * cop_vector_15min[t],
                            name=f"da_heat_volume_cap_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_heat_bal_down[t, scenario] <= self.V_balancing_down[t, scenario] * cop_vector_15min[t],
                            name=f"bal_down_heat_volume_cap_{self.name}_t{t}_{scenario}")

            # --- 3. MARKET BIDDING CAPACITY FRACTION BOUNDS ---
            max_elec_input = self.P_cap / cop_vector_15min[t]

            # 3.1. UPWARD BALANCING BIDS BOUNDS
            model.addConstr(self.V_balancing_up[t, scenario] <= self.U_elec[t, scenario],
                            name=f"bal_up_electrical_limit_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_balancing_up[t, scenario] <= (self.V_heat_DA[t, scenario] / cop_vector_15min[t]),
                            name=f"bal_up_backed_by_physical_heat_{self.name}_t{t}_{scenario}")

            # 3.2. DOWNWARD BALANCING BIDS BOUNDS
            model.addConstr(
                self.U_elec[t, scenario] + self.V_balancing_down[t, scenario] <= max_elec_input * self.y_on[t, scenario],
                name=f"bal_down_physical_limit_{self.name}_t{t}_{scenario}")

            # --- NEW PROPORTIONAL BID RATIO LIMIT ---
            # Forces Balancing Down to scale realistically with your cleared baseline footprint.
            # Max real-time increase is capped at 50% (0.5) of your current U_elec baseline.
            model.addConstr(
                self.V_balancing_down[t, scenario] <= 2 * self.U_elec[t, scenario],
                name=f"bal_down_proportional_baseline_cap_{self.name}_t{t}_{scenario}"
            )

            # 3.3. BINARY MUTUAL EXCLUSION REGULATION GATES
            model.addConstr(self.V_balancing_down[t, scenario] <= max_elec_input * self.b_market_dir[t, scenario],
                            name=f"bal_down_binary_gate_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_balancing_up[t, scenario] <= max_elec_input * (1 - self.b_market_dir[t, scenario]),
                            name=f"bal_up_binary_gate_{self.name}_t{t}_{scenario}")

            # --- 4. ABSOLUTE PHYSICAL ASSET BOUNDARIES ---
            model.addConstr(self.V_heat[t, scenario] <= self.P_cap * self.y_heat[t, scenario],
                            name=f"up_bound_fixed_P_heat_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_heat[t, scenario] >= self.delta * self.P_cap * self.y_heat[t, scenario],
                            name=f"low_bound_fixed_P_heat_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_cool[t, scenario] <= self.P_cap * self.y_cool[t, scenario],
                            name=f"up_bound_fixed_P_cool_{self.name}_t{t}_{scenario}")
from gurobipy import GRB
import config3


class LargeScaleHeatPump15Min2:
    def __init__(self, name, min_load_fraction=0.15):
        """
        Second-Stage 15-Minute Operational Class for a Large-Scale Heat Pump.
        Corrected: V_heat_DA is now strictly First-Stage (Scenario-Independent).
        """
        self.name = name
        self.delta = min_load_fraction

        # Pull technical details from your configuration dictionary
        tech_data = config3.INSTALLED_TECH["LargeScaleHeatPump"]
        self.P_cap = tech_data["P_cap"]  # Fixed thermal size (kW_th)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config3.ANNUITY_FACTOR + self.opex_per_kw
        )

        # First-Stage Variables: Scenario-Independent (Tracked strictly by timestep 't')
        self.y_on = {}        # Binary operational state
        self.y_heat = {}      # Binary active heating mode
        self.y_cool = {}      # Binary active cooling mode
        self.U_elec = {}      # Baseline input electricity power rate (kW_el)
        self.V_heat_DA = {}   # Output day-ahead dedicated heat power (kW_th)
        self.V_cool = {}      # Output cooling power rate (kW_cool)

        # Second-Stage Variables: Scenario-Dependent (Tracked by timestep 't' and 'scenario')
        self.V_heat = {}              # Output real-time heat power rate (kW_th)
        self.V_heat_bal_down = {}     # Output thermal heat from balancing down energy (kW_th)
        self.V_balancing_up = {}      # aFRR Upward electrical regulation capacity (kW)
        self.V_balancing_down = {}    # aFRR Downward electrical regulation capacity (kW)
        self.b_market_dir = {}        # Binary directional gate (1: Downward, 0: Upward)

    def add_variables(self, model, timesteps_15min):
        """
        Populates the first-stage, scenario-independent baseline variables once.
        """
        for t in timesteps_15min:
            self.y_on[t] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_{self.name}_t{t}"
            )
            self.y_heat[t] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_heat_{self.name}_t{t}"
            )
            self.y_cool[t] = model.addVar(
                vtype=GRB.BINARY,
                name=f"y_cool_{self.name}_t{t}"
            )
            self.U_elec[t] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_E_{self.name}_t{t}"
            )
            self.V_heat_DA[t] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_DA_{self.name}_t{t}"
            )
            self.V_cool[t] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_C_{self.name}_t{t}"
            )

    def add_scenario_variables(self, model, timesteps_15min, scenario):
        """
        Populates only the second-stage, scenario-dependent balancing market variables.
        """
        for t in timesteps_15min:
            self.V_heat[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_{self.name}_t{t}_{scenario}"
            )
            self.V_heat_bal_down[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_H_bal_down_{self.name}_t{t}_{scenario}"
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
        Enforces 15-minute technology constraints linking the fixed baseline schedule
        with the scenario-dependent real-time balancing variables.
        """
        for t in timesteps_15min:
            # --- 0. COMMITMENT AND SCHEDULING MODE SWITCHES ---
            model.addConstr(self.y_heat[t] + self.y_cool[t] <= self.y_on[t],
                            name=f"exclusive_thermal_mode_{self.name}_t{t}_{scenario}")

            # --- 1. THE NET ELECTRICAL REAL-TIME IMPORT DEFINITION ---
            net_electrical_input = self.U_elec[t] + self.V_balancing_down[t, scenario] - self.V_balancing_up[t, scenario]

            # --- 2. PERFORMANCE CONSTRAINTS (THE TRUE THERMODYNAMIC BRIDGE) ---
            model.addConstr((self.V_heat[t, scenario] / cop_vector_15min[t]) + (
                        self.V_cool[t] / cop_cool_vector_15min[t]) == net_electrical_input,
                            name=f"net_electrical_thermal_bridge_{self.name}_t{t}_{scenario}")

            model.addConstr(self.V_heat[t, scenario] == self.V_heat_DA[t] + self.V_heat_bal_down[t, scenario],
                            name=f"thermal_output_summation_{self.name}_t{t}_{scenario}")

            model.addConstr(self.V_heat_DA[t] <= self.U_elec[t] * cop_vector_15min[t],
                            name=f"da_heat_volume_cap_{self.name}_t{t}_{scenario}")

            model.addConstr(self.V_heat_bal_down[t, scenario] <= self.V_balancing_down[t, scenario] * cop_vector_15min[t],
                            name=f"bal_down_heat_volume_cap_{self.name}_t{t}_{scenario}")

            # --- 3. MARKET BIDDING CAPACITY FRACTION BOUNDS ---
            max_elec_input = self.P_cap / cop_vector_15min[t]

            # 3.1. UPWARD BALANCING BIDS BOUNDS
            model.addConstr(self.V_balancing_up[t, scenario] <= self.U_elec[t],
                            name=f"bal_up_electrical_limit_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_balancing_up[t, scenario] <= (self.V_heat_DA[t] / cop_vector_15min[t]),
                            name=f"bal_up_backed_by_physical_heat_{self.name}_t{t}_{scenario}")

            # 3.2. DOWNWARD BALANCING BIDS BOUNDS
            model.addConstr(
                self.U_elec[t] + self.V_balancing_down[t, scenario] <= max_elec_input * self.y_on[t],
                name=f"bal_down_physical_limit_{self.name}_t{t}_{scenario}")

            # --- NEW PROPORTIONAL BID RATIO LIMIT ---
            model.addConstr(
                self.V_balancing_down[t, scenario] <= 2 * self.U_elec[t],
                name=f"bal_down_proportional_baseline_cap_{self.name}_t{t}_{scenario}"
            )

            # 3.3. BINARY MUTUAL EXCLUSION REGULATION GATES
            model.addConstr(self.V_balancing_down[t, scenario] <= max_elec_input * self.b_market_dir[t, scenario],
                            name=f"bal_down_binary_gate_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_balancing_up[t, scenario] <= max_elec_input * (1 - self.b_market_dir[t, scenario]),
                            name=f"bal_up_binary_gate_{self.name}_t{t}_{scenario}")

            # --- 4. ABSOLUTE PHYSICAL ASSET BOUNDARIES ---
            model.addConstr(self.V_heat[t, scenario] <= self.P_cap * self.y_heat[t],
                            name=f"up_bound_fixed_P_heat_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_heat[t, scenario] >= self.delta * self.P_cap * self.y_heat[t],
                            name=f"low_bound_fixed_P_heat_{self.name}_t{t}_{scenario}")
            model.addConstr(self.V_cool[t] <= self.P_cap * self.y_cool[t],
                            name=f"up_bound_fixed_P_cool_{self.name}_t{t}_{scenario}")
from gurobipy import GRB
import config_installed


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
        tech_data = config_installed.INSTALLED_TECH["LargeScaleHeatPump"]
        self.P_cap = tech_data["P_cap"]  # Fixed thermal size (kW_th)
        self.capex_per_kw = tech_data["capex_per_kw"]
        self.opex_per_kw = tech_data["opex_per_kw"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.P_cap * (
                self.capex_per_kw * config_installed.ANNUITY_FACTOR + self.opex_per_kw
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, scenario)
        self.y_on = {}  # Binary operational state
        self.y_heat = {}  # Binary active heating mode
        self.y_cool = {}  # Binary active cooling mode
        self.V_heat = {}  # Output heat power rate (kW_th)
        self.V_cool = {}  # Output cooling power rate (kW_cool)
        self.U_elec = {}  # Baseline input electricity power rate (kW_el)

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

    def add_constraints(self, model, timesteps_15min, cop_vector_15min, cop_cool_vector_15min, scenario):
        """
        Enforces 15-minute constraints like in the first stage optimization.
        Expects 15-minute resolved COP arrays containing 35,040 elements.
        """
        for t in timesteps_15min:
            # 1. Mode Scheduling Rules
            model.addConstr(
                self.y_heat[t, scenario] <= self.y_on[t, scenario],
                name=f"on_heat_{self.name}_t{t}_{scenario}"
            )
            model.addConstr(
                self.y_cool[t, scenario] <= self.y_on[t, scenario],
                name=f"on_cool_{self.name}_t{t}_{scenario}"
            )

            # 2. Performance Constraint (The Electricity Bridge)
            model.addConstr(
                self.U_elec[t, scenario] == (self.V_heat[t, scenario] / cop_vector_15min[t]) +
                (self.V_cool[t, scenario] / cop_cool_vector_15min[t]),
                name=f"elec_balance_{self.name}_t{t}_{scenario}"
            )

            # 3. Balancing Market Physical Capacity Cap
            # Total electrical footprint (baseline electricity + balancing market commitments)
            # cannot exceed the equivalent electrical maximum input of the machine.
            # Max thermal output is self.P_cap, so max baseline electrical input is (self.P_cap / COP).

            # 4. Heating Operational Bounds
            model.addConstr(
                self.V_heat[t, scenario] <= self.P_cap * self.y_heat[t, scenario],
                name=f"up_bound_fixed_P_heat_{self.name}_t{t}_{scenario}"
            )
            model.addConstr(
                self.V_heat[t, scenario] >= self.delta * self.P_cap * self.y_heat[t, scenario],
                name=f"low_bound_fixed_P_heat_{self.name}_t{t}_{scenario}"
            )

            # 5. Cooling Operational Bounds
            model.addConstr(
                self.V_cool[t, scenario] <= self.P_cap * self.y_cool[t, scenario],
                name=f"up_bound_fixed_P_cool_{self.name}_t{t}_{scenario}"
            )
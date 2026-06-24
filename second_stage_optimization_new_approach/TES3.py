from gurobipy import GRB
import config3



class PitThermalEnergyStorage15Min2:
    def __init__(self, name, loss_rate=0.0005, eta_charge=0.9, eta_disch=0.9):
        """
        Second-Stage 15-Minute Operational Class for Pit Thermal Energy Storage (TES).
        Reads installed footprint and financial overhead directly from config_installed.py
        """
        self.name = name
        self.eta_c = eta_charge
        self.eta_d = eta_disch

        # Scale the hourly self-discharge loss rate to a 15-minute resolution
        # (1 - loss_rate_15min) = (1 - loss_rate_hourly)^(1/4)
        self.lam_15min = 1 - ((1 - loss_rate) ** 0.25)

        # Pull technical details from your configuration dictionary
        tech_data = config3.INSTALLED_TECH["TES"]
        self.E_cap = tech_data["E_cap"]  # Fixed energy capacity size (kWh)
        self.capex_per_kwh = tech_data["capex_per_kwh"]

        # Pre-calculate the fixed annualized investment/maintenance cost overhead
        self.fixed_annual_cost = self.E_cap * (
                self.capex_per_kwh * config3.ANNUITY_FACTOR
        )

        # Multi-Scenario, 15-min dictionaries for tracking variables (timestep, scenario)
        self.E_state = {}  # Hourly Stored Energy level inventory (kWh)
        self.U_charge = {}  # Hourly Charging thermal power rate (kW)
        self.V_disch = {}  # Hourly Discharging thermal power rate (kW)
        self.C_tech = {}  # Binary marker: 1 if charging, 0 if discharging

    def add_variables(self, model, timesteps_15min, scenario):
        """
        Populates the operational variables for a single specified scenario block.
        """
        for t in timesteps_15min:
            self.E_state[t, scenario] = model.addVar(
                lb=0,
                ub=self.E_cap,  # Secure absolute bound directly at variable creation
                vtype=GRB.CONTINUOUS,
                name=f"E_state_{self.name}_t{t}_{scenario}"
            )
            self.U_charge[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"U_charge_{self.name}_t{t}_{scenario}"
            )
            self.V_disch[t, scenario] = model.addVar(
                lb=0,
                vtype=GRB.CONTINUOUS,
                name=f"V_disch_{self.name}_t{t}_{scenario}"
            )
            self.C_tech[t, scenario] = model.addVar(
                vtype=GRB.BINARY,
                name=f"C_tech_{self.name}_t{t}_{scenario}"
            )

    def add_constraints(self, model, timesteps_15min, hp_15min_instance, peak_demand_kw, scenario):
        """
        Enforces 15-minute storage constraints and inventory energy balances.
        """
        hp_max_thermal_capacity = hp_15min_instance.P_cap

        for t in timesteps_15min:
            # 1. Charging Limits: Storage can charge from balancing down heat
            # OR any excess day-ahead heat pump production capacity
            model.addConstr(
                self.U_charge[t, scenario] <= hp_15min_instance.V_heat_bal_down[t, scenario] +
                hp_15min_instance.V_heat_DA[t],
                name=f"charge_source_gate_{self.name}_t{t}_{scenario}"
            )

            # Simultaneous operation binary lockout protection
            model.addConstr(
                self.U_charge[t, scenario] <= hp_max_thermal_capacity * self.C_tech[t, scenario],
                name=f"charge_limit_{self.name}_t{t}_{scenario}"
            )
            model.addConstr(
                self.V_disch[t, scenario] <= peak_demand_kw * (1 - self.C_tech[t, scenario]),
                name=f"disch_limit_{self.name}_t{t}_{scenario}"
            )

            # 2. Sequential Inventory Continuity Equations
            if t == 0:
                model.addConstr(
                    self.E_state[t, scenario] == self.E_state[timesteps_15min[-1], scenario],
                    name=f"periodicity_{self.name}_{scenario}"
                )
            else:
                model.addConstr(
                    self.E_state[t, scenario] == (1 - self.lam_15min) * self.E_state[t - 1, scenario] +
                    (self.eta_c * self.U_charge[t, scenario] * 0.25) -
                    ((self.V_disch[t, scenario] / self.eta_d) * 0.25),
                    name=f"energy_balance_{self.name}_t{t}_{scenario}"
                )
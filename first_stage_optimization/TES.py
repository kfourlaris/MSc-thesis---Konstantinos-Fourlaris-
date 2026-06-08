from gurobipy import GRB


class PitThermalEnergyStorage:
    def __init__(self, name, e_min_market=50, e_max_market=2788800,
                 capex_per_kwh=8, loss_rate=0.0005, eta_charge=0.9, eta_disch=0.9):
        """
        Args:
            e_min_market: Minimum installable energy capacity (KWh)
            e_max_market: Maximum installable energy capacity (KWh) 60000m3
            capex_per_kwh: Investment cost per unit of energy capacity (https://doi.org/10.1016/j.solener.2022.12.046) + land costs
            loss_rate: Hourly self-discharge rate (lambda)
            eta_charge: Charging efficiency (eta^c)
            eta_disch: Discharging efficiency (eta^d)
        """
        self.name = name
        self.e_min = e_min_market
        self.e_max = e_max_market
        self.capex_per_kwh = capex_per_kwh
        self.lam = loss_rate
        self.eta_c = eta_charge
        self.eta_d = eta_disch

        # Placeholders for Variables
        self.E_cap = None      # Design size: Total Energy Capacity (P_k)
        self.b_select = None   # Tech selection (b_k)
        self.E_state = {}      # Hourly Stored Energy (E_h,hp,t)
        self.U_charge = {}     # Hourly Charging Energy (U_h,hp,t)
        self.V_disch = {}      # Hourly Discharging Energy
        self.C_tech = None     # Added a binary variable to prevent charging/discharging at the same time

    def add_variables(self, model, timesteps):
        # Design Variables (Z)
        self.E_cap = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"E_cap_{self.name}")
        self.b_select = model.addVar(vtype=GRB.BINARY, name=f"b_{self.name}")

        # Operational Variables (X)
        self.E_state = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"E_state_{self.name}")
        self.U_charge = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"U_charge_{self.name}")
        self.V_disch = model.addVars(timesteps, lb=0, vtype=GRB.CONTINUOUS, name=f"V_disch_{self.name}")
        self.C_tech = model.addVars(timesteps, vtype=GRB.BINARY, name=f"C_tech_{self.name}")

    def add_constraints(self, model, timesteps, hp_instance, peak_demand_kw):
        # 1. Market Size Limits (P_k,min <= P_k <= P_k,max)
        model.addConstr(self.E_cap >= self.b_select * self.e_min, name=f"market_min_{self.name}")
        model.addConstr(self.E_cap <= self.b_select * self.e_max, name=f"market_max_{self.name}")

        # 2. Storage Update & Energy Balance
        for t in timesteps:
            # Capacity limit: Stored energy cannot exceed design size
            model.addConstr(self.E_state[t] <= self.E_cap, name=f"cap_limit_up{self.name}_{t}")
            model.addConstr(self.E_state[t] >= 0, name=f"cap_limit_down{self.name}_{t}")

            #charge and discharge constraints
            #The charging energy at time t cannot exceed the size of the LSHP
            model.addConstr(self.U_charge[t] <= hp_instance.V_heat[t], name=f"charging_constraint_one{self.name}_{t}")
            model.addConstr(self.U_charge[t] <= hp_instance.p_max * self.C_tech[t], name=f"charging_constraint_two{self.name}_{t}" )
            #The discharging energy at time t cannot exceed the heat peak demand power of the network
            model.addConstr(self.V_disch[t] <= peak_demand_kw * (1-self.C_tech[t]), name=f"discharging_constraint{self.name}_{t}")

            if t == 0:
                # Periodicity: E(0) = E(T) for seasonal consistency
                model.addConstr(self.E_state[t] == self.E_state[timesteps[-1]], name=f"periodicity_{self.name}")
            else:
                # Energy Balance: E(t) = E(t-1)*(1-lambda) + eta_c*U(t) - V(t)/eta_d
                model.addConstr(
                    self.E_state[t] == (1 - self.lam) * self.E_state[t-1] +
                    self.eta_c * self.U_charge[t] - (self.V_disch[t] / self.eta_d),
                    name=f"energy_balance_{self.name}_{t}"
                )
### # System-level optimization for the integration of heat pumps in district heating and cooling

**Author:** Konstantinos Fourlaris  
**Program:** Master in Energy Science and Technology (MEST)  
**Institution:** ETH Zurich, Chair of Energy Systems Analysis (ESA)  
**Supervising Professor:** Prof. Dr. Russell McKenna  
**Project Supervisors:** Dr. Tom Mike Terlouw, Dr. Tarek Alskaif  
**Repository:** [github.com/kfourlaris/MSc-thesis---Konstantinos-Fourlaris-](https://github.com/kfourlaris/MSc-thesis---Konstantinos-Fourlaris-)

---

## 📌 Project Overview
This repository implements a **two-stage optimization framework** to assess the techno-economic viability, operational flexibility, and decarbonization potential of integrating large-scale heat pump (LSHP) and thermal energy storage (TES) into transitioning 4th generation district heating and cooling networks (DHCNs) across Zurich and Amsterdam.

* **Stage 1 (Economic Deterministic MILP, 1-hour resolution):** Determines optimal asset sizing and baseline operational dispatch across greenfield and brownfield configurations, benchmarking against existing Combined Heat and Power (CHP) and Biomass Boiler (BB) infrastructure alongside a complete post-optimization GHG emissions Life Cycle Assessment (LCA).
* **Stage 2 (Economic Stochastic MILP, 15-minute resolution):** Models operation heating and cooling dispatch co-optimization between Day-Ahead Market (DAM) energy procurement and secondary Balancing Market (BM) participation—offering automatic Frequency Restoration Reserve (aFRR) flexibility using 10-year historical balancing price clustering through K-Medoids.
* **Key Findings:** Coupling LSHP with TES cuts total annualized costs by **11–16%** (brownfield) and reduces lifecycle GHG emissions by up to **57%** (greenfield). Active aFRR market participation unlocks an additional **9–13%** cost reduction through remunerative downward/upward balancing flexibility enabled by TES presence in the MES.

## 🧭 How to Read This Codebase

The codebase is organized into dedicated modules for exogenous data preprocessing, stage-one optimization formulation, and stage-two stochastic operational co-optimization formulation.

### 1. Data Preprocessing & Exogenous Parameter Scripts
Before running optimization models, these standalone scripts process raw climatic, demand, and market data into model-ready time series:
* `generate_meteo_data.py`: Extracts hourly 2025 ambient temperatures for Zurich and Amsterdam.
* `Filter_generic_heating_and_cooling_profiles.py`: Filters raw [Hotmaps](https://www.hotmaps-project.eu/) profiles for space heating (SH), space cooling (SC), and domestic hot water (DHW) across residential and tertiary sectors for the Zurich and Amsterdam regions of ineterst.
* `generate_normalized_profiles.py`: Matches and normalizes Hotmaps generic load shapes based on season, day type, hour, and local ambient temperatures.
* `generate_heating_and_cooling_demand.py`: Scales normalized profiles into hourly energy demand time series ($MWh/h$) for each target city.
* `generate_electricity_prices.py`: Processes historical 2025 ENTSO-E Day-Ahead Market (DAM) wholesale energy prices and applies local grid tariffs to construct total hourly electricity procurement costs.
* `EU_ETS_emissions_prices.py`: Retrieves and aligns daily 2025 EU ETS carbon allowance prices ($€/tCO_2$).
* `Price_clusters_balancing_Netherlands.py` & `Price_clusters_balancing_Switzerland.py`: Implements K-Medoids scenario clustering on a 10-year historical dataset of 15-minute aFRR balancing market activation prices for Amsterdam and Zurich, respectively.

---

### 2. Core Optimization Modules

* **`First Stage Optimization/`**:
  * `config.py`: Acts as the primary control panel. Sets global financial parameters, technical parameters, dataset paths, city selection (`Zurich` vs. `Amsterdam`), and **technology activation switches** (`True`/`False`).
  * `Technology Classes (`BB.py`, `CHP.py`, `LSHP.py`, `Chiller.py`, `TES.py`)`: Define component-level decision variables, operational domains, and technical constraints (e.g., capacity bounds, efficiencies, output energy constraints).
  * `main.py` (or execution script): Formulates global energy balancing constraints, multi-energy network coupling, emissions accounting, and the deterministic multi-period objective function (TAC minimization).
* **`Second Stage Optimization/`**:
  * `config2.py`: Stage-two control panel receiving the optimal asset capacities determined in Stage 1, alongside 15-minute operational and market parameters.
  * `Technology Clases`: They function like the first stage optimization but now with added decision variables and constraints regarding the participation in BM.
  * `main2.py` (or execution script): Formulates the stochastic MILP co-optimization with the same objective function as the first stage optimization for optimal heating and cooling dispatch of the MES through Day-Ahead and Balancing Market (aFRR energy flexibility) participation over representative historical clusters.
* **`Second Stage Optimization Sequential Approach/`**:
  * Implements a benchmark literature formulation where DAM electricity, natural gas, and biomass procurement decisions are fixed scenario-independently before balancing activations occur.
* *Note on Repository Legacy:* The `stochastic DA running/` folder represents an exploratory branch for joint DAM/BM stochasticity and can be disregarded.

---

## 💾 Input Data

The primary raw and processed time-series data are stored in the **`Input Data/`** directory. These key datasets include:
* **Electricity Price Market Data:** Hourly Day-Ahead Market (DAM) energy prices and 15-minute secondary Balancing Market (aFRR) energy prices and activation directions.
* **Thermal Demands:** Raw and normalized generic SH, SC, and DHW hourly demand profiles derived from the EU Hotmaps project.
* **Climatic & Environmental Data:** Local ambient temperature series (2025) and daily EU ETS carbon allowance prices.

---

## 🔬 Running Scenario Experiments

To evaluate different network layouts, examined networks and investment pathways:

1. **City Selection:** Set the `city` switch to `"Zurich"` or `"Amsterdam"` identically across both `First Stage Optimization/config.py` and `Second Stage Optimization/config2.py`.
2. **System Configurations:** Toggle the boolean technology flags in `config.py` to compare alternative generation mixes.
3. **Greenfield vs. Brownfield Pathway:** The repository defaults to a **Brownfield** setup ($CAPEX = 0$ for legacy CHP and BB). To simulate a **Greenfield** setup, enter the specific capital investment costs for `CHP` and `BB` in their respective class files in Stage 1 and within `config2.py` for Stage 2.
4. **Execution Pipeline:** Always solve Stage 1 first to determine optimal asset sizing, verify capacity hand-offs in `config2.py`, and execute Stage 2 to optimize 15-minute aFRR balancing market participation.
5. **Local Dataset Paths:** If running the scripts locally and adjusting absolute or relative directory paths in the configuration files, inspect the **final component of each path** (the target filename and subfolder in `Input Data/`) to identify which exact dataset or profile is being ingested.
6. **Baseline Fossil Configuration Adjustment:** When simulating the baseline fossil fuel-based system configuration, adjust the minimum load fraction of the CHP unit to **9.5%** (`0.095`) within the CHP class parameters to prevent mathematical solver infeasibilities during low-demand periods.
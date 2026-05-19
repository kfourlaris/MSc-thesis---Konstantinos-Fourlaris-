import numpy as np
import pandas as pd

# =============================================================================
# INSTALLED FOOTPRINT & TECHNO-ECONOMIC CONSTANTS (STAGE 2)
# =============================================================================

# Annuity factor/CRF should match your Stage 1 assumptions
ANNUITY_FACTOR = 0.0804

INSTALLED_TECH = {
    "BiomassBoiler": {
        "P_cap": 1250.50,       # kW
        "capex_per_kw": 350,    # Euro/kW
        "opex_per_kw": 7        # Euro/kW/year
    },
    "LargeScaleHeatPump": {
        "P_cap": 1850.75,       # kW
        "capex_per_kw": 600,    # Euro/kW
        "opex_per_kw": 12       # Euro/kW/year
    },
    "TES": {
        "E_cap": 4500.00,       # kWh
        "capex_per_kwh": 30,    # Euro/kWh
        "opex_per_kwh": 0.5     # Euro/kWh/year
    }
}
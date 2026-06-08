import meteostat
import pandas as pd
print(meteostat.__file__)
print(dir(meteostat))
import pandas as pd

from meteostat import Point, stations, hourly, config
from datetime import datetime

config.block_large_requests = False

# Zurich coordinates
zurich = Point(47.3769, 8.5417)

# --- STATION SELECTION LOGIC ---
station_list = stations.nearby(zurich) #It is Zurich Fluntern
station_id = station_list.index[0]
print("Using station:", station_id)

# Time period
start = datetime(2025, 1, 1)
end = datetime(2025, 12, 31, 23)

# Fetch hourly data
data = hourly(station_id, start, end).fetch()  # only Hourly still needs .fetch()


# Check the data
print(data.head())

data.to_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Zurich_meteo_raw_data.csv", index=True, encoding="utf-8")
print("Data saved to Zurich.csv")

config.block_large_requests = False

# Amsterdam location
amsterdam = Point(52.3676, 4.9041)  # latitude, longitude

#Get nearest station (returns DataFrame directly)
station_list = stations.nearby(amsterdam)  #gives Amsterdam airport
station_id = station_list.index[0]
print("Using station:", station_id)

# Time period
start = datetime(2025, 1, 1)
end = datetime(2025, 12, 31, 23)

# Fetch hourly data
data = hourly(station_id, start, end).fetch()

# DISREGARD FEBRUARY 29th ONLY
# we remove the extra day from leap years but keep the rest of the year's data for the same reason as above
data = data[~((data.index.month == 2) & (data.index.day == 29))]

#Check the data
print(data.head())

# Save to CSV for Numbers
data.to_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Amsterdam_meteo_raw_data.csv", index=True, encoding="utf-8")
print("Data saved to Amsterdam.csv")

# =====================================================================
# Hours above 25.5 oC to calculate share of cooling demand
# =====================================================================

# 1. Read the saved CSV files back into memory
df_zurich = pd.read_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Zurich_meteo_raw_data.csv")
df_amsterdam = pd.read_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/Amsterdam_meteo_raw_data.csv")

# 2. Count how many hours are strictly above 30 degrees for each city
zurich_hot_hours = len(df_zurich[df_zurich['temp'] >= 25.5])
amsterdam_hot_hours = len(df_amsterdam[df_amsterdam['temp'] >= 25.5])

print("\n" + "="*50)
print("ANNUAL HOURS ABOVE 25.5°C PER CITY (2025)")
print("="*50)
print(f"Zurich:    {zurich_hot_hours} hours")
print(f"Amsterdam: {amsterdam_hot_hours} hours")
print("="*50)


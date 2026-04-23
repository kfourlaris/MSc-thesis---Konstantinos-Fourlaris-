import meteostat
import pandas as pd
print(meteostat.__file__)
print(dir(meteostat))

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
start = datetime(2005, 1, 1)
end = datetime(2025, 12, 31, 23)

# Fetch hourly data
data = hourly(station_id, start, end).fetch()  # only Hourly still needs .fetch()

# DISREGARD FEBRUARY 29th ONLY
# we remove the extra day from leap years but keep the rest of the year's data in order to be alligned
data = data[~((data.index.month == 2) & (data.index.day == 29))]

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
start = datetime(2005, 1, 1)
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



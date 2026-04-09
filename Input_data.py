import meteostat
print(meteostat.__file__)
print(dir(meteostat))

from meteostat import Point, stations, hourly
from datetime import datetime

# Zurich coordinates
zurich = Point(47.3769, 8.5417)

# Get nearest station (returns DataFrame directly)
station_list = stations.nearby(zurich)
station_id = station_list.index[0]  # take the first station
print("Using station:", station_id)

# Time period
start = datetime(2025, 1, 1)
end = datetime(2025, 12, 31, 23)

# Fetch hourly data
data = hourly(station_id, start, end).fetch()  # only Hourly still needs .fetch()

# Check the data
print(data.head())

data.to_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Zurich_meteo_data_2025.csv", index=True, encoding="utf-8")


# Amsterdam location
amsterdam = Point(52.3676, 4.9041)  # latitude, longitude

#Get nearest station (returns DataFrame directly)
station_list = stations.nearby(amsterdam)
station_id = station_list.index[0]
print("Using station:", station_id)

# Time period
start = datetime(2025, 1, 1)
end = datetime(2025, 12, 31, 23)

# Fetch hourly data
data = hourly(station_id, start, end).fetch()

#Check the data
print(data.head())

# Save to CSV for Numbers
data.to_csv("/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Amsterdam_meteo_data_2025.csv", index=True, encoding="utf-8")
print("Data saved to Amsterdam_2025.csv")



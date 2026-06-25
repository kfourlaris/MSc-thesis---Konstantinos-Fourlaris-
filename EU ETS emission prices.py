import pandas as pd
import yfinance as yf  # Run 'pip install yfinance' if you don't have it

# Ticker for ICE EUA Carbon Futures on Yahoo Finance is 'CFI2Y00'
# or we use the front-month Dec contract tracking. Let's pull the official proxy.
ticker = "CO2.MI"

print("Fetching daily 2025 EU ETS carbon prices...")
data = yf.download(ticker, start="2025-01-01", end="2025-12-31")

# Clean the dataframe
df_clean = data[['Close']].copy()
df_clean.reset_index(inplace=True)
df_clean.columns = ['date', 'price']

# Fill weekend/holiday gaps (forward fill) so every calendar day has a price
df_clean['date'] = pd.to_datetime(df_clean['date'])
df_clean.set_index('date', inplace=True)
df_full_year = df_clean.resample('D').ffill()
df_full_year.reset_index(inplace=True)

# Save it directly into your project directory
output_path = '/Users/kostf/Library/CloudStorage/OneDrive-Προσωπικό/Έγγραφα/ETH Zurich/4th semester/system-level-optimization/Input data/eu_ets_2025.csv'
df_full_year.to_csv(output_path, index=False)

print(f"Success! Saved {len(df_full_year)} days of carbon data to: {output_path}")
print(f"Calculated 2025 Average: {df_full_year['price'].mean():.2f} EUR/tonne")
"""
inspect_merged_dataset.py
--------------------------
One-off diagnostic: confirms merged_dataset.parquet's actual columns,
district value format, date range, and whether it has the raw fields
prediction_engine needs (dewpoint_2m, cape, wind_gusts_10m, rain, snowfall).

Run from project root:
    python inspect_merged_dataset.py
"""

import pandas as pd

PATH = "datasets/merged_dataset/merged_dataset.parquet"

df = pd.read_parquet(PATH)

print("Shape:", df.shape)
print()
print("Columns:", list(df.columns))
print()

# Try to find the district-like column
for candidate in ["district", "District", "location", "region"]:
    if candidate in df.columns:
        print(f"Unique values in '{candidate}':", df[candidate].unique())
        break
else:
    print("No obvious district column found among:", [c for c in df.columns if "dist" in c.lower() or "loc" in c.lower()])

print()

# Try to find timestamp column
for candidate in ["timestamp", "datetime", "date", "time"]:
    if candidate in df.columns:
        print(f"'{candidate}' range:", df[candidate].min(), "to", df[candidate].max())
        break

print()
print("Sample row:")
print(df.iloc[0].to_dict())

print()
needed = ["dewpoint_2m", "relative_humidity", "wind_gusts_10m", "cape",
          "precipitation_openmeteo", "rain_openmeteo", "snowfall", "imd_rainfall_mm"]
print("Presence of fields prediction_engine needs:")
for col in needed:
    print(f"  {col}: {'FOUND' if col in df.columns else 'MISSING'}")

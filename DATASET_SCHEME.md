# DATASET_SCHEMA.md

Dataset

Merged Weather Dataset

Rows

24073

Frequency

Hourly

Time Range

2022-01-01

to

2024-09-30

---

Input Features

Meteorological

temperature_2m

dewpoint_2m

relative_humidity

surface_pressure

mean_sea_level_pressure

wind_speed_10m

wind_direction_10m

wind_gusts_10m

cloud_cover

precipitation

rain

snowfall

cape

lifted_index

weather_code

u_wind

v_wind

NASA precipitation

IMD rainfall

---

Engineered Features

hour

month

day

season

is_monsoon

hour_sin

hour_cos

month_sin

month_cos

precip_lag_1h

precip_lag_3h

precip_lag_6h

rolling_3h

rolling_6h

rolling_24h

rolling_72h

pressure_tendency

precip_acceleration

wet_bulb_temperature

vpd

wind_speed_squared

rain_streak

precipitation_ratio

---

Target Variables

imd_rainfall_mm

Regression

----------------

rain_intensity_class

Multi-Class

0 No Rain

1 Light

2 Moderate

3 Heavy

4 Very Heavy

----------------

cloudburst_flag

Binary

0 No

1 Yes

Definition

Rainfall ≥100 mm within 3 hours

----------------

landslide_risk

Binary

0 Safe

1 Risk

Generated using rainfall thresholds and engineered weather variables.
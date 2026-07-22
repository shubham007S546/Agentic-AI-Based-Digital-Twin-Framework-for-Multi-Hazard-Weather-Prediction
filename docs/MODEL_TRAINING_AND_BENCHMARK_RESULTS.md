# Model Training, Tuning, and Benchmark Infrastructure

## Project Context & Architecture Overview

This project implements an **Agentic AI-Based Digital Twin Framework for Rainfall Prediction and Extreme Weather Intelligence in Himachal Pradesh** (specifically focusing on Mandi, Kullu, and Chamba districts).

---

## 1. Machine Learning Dataset Pipeline (`ml_ready/`)

The data pipeline aggregates multi-source hydro-meteorological, satellite, and terrain spatial data into a time-aligned master matrix.

### Core Datasets & Split Sizes
- **Master Train Dataset**: `train_ready_master.csv` (106,664+ rows)
- **Features (`X_train.csv`)**: 35 engineered spatial-temporal features
- **Validation Set (`X_val.csv`, `y_val.csv`)**: Untouched, out-of-time evaluation block
- **Test Set (`X_test.csv`, `y_test.csv`)**: Out-of-time test set for final verification

### Engineered Feature Sets
1. **Atmospheric & Thermal**: `temperature_2m`, `dewpoint_2m`, `relative_humidity`, `surface_pressure`, `temp_dewpoint_spread`
2. **Wind Vectors & Dynamics**: `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`, `wind_u_10m`, `wind_v_10m`, `wind_gust_ratio`
3. **Convective & Satellite Indicators**: `cape`, `cloud_cover`, `humidity_cape_interact`
4. **Precipitation Lags & Rolling Accumulations**: `precipitation_openmeteo`, `rain_openmeteo`, `rolling_precip_3h`, `rolling_precip_6h`, `rolling_precip_24h`, `rolling_precip_72h`, `precip_lag_1h`, `precip_lag_3h`, `precip_lag_6h`, `precip_acceleration`, `rolling_ratio_3_24`
5. **Cyclic Temporal Features**: `hour_sin`, `hour_cos`, `month_sin`, `month_cos`, `hour`, `month`, `day_of_year`, `season`, `is_monsoon`

---

## 2. Training Strategy & Advanced ML Techniques

To model extreme weather events (such as cloudbursts and landslides) without suffering from severe class imbalance or temporal data leakage, 4 core techniques are wired into the pipeline:

### Technique 1: Weighted Temporal Cross-Validation
- Blocked, expanding-window CV splits derived from `temporal_cv_folds.csv`.
- Never shuffles time-series data to prevent future information leakage into past training folds.

### Technique 2: Class Weighting
- Per-row sample weights for multiclass rainfall intensity (`sw_rain_intensity_class`).
- `scale_pos_weight` re-derived dynamically from positive/negative class frequencies.

### Technique 3: Time-Block Undersampling
- Rare-event targets (`cloudburst_flag` and `landslide_risk`) use whole time-block undersampled datasets (`X_train_<target>_balanced.csv`).
- Preserves local temporal structure during training while keeping the untouched `X_val` / `y_val` intact for realistic evaluation.

### Technique 4: Two-Stage Regression Strategy for Rainfall Amount
- **Stage A**: Binary classifier for rain detection (rain vs. no-rain).
- **Stage B**: Log-amount regressor (`log1p(imd_rainfall_mm)`) fitted exclusively on rainy timesteps.
- Final output: zero for non-rain predictions, `expm1(Stage B prediction)` for rainy timesteps.

---

## 3. Evaluated Tasks & Benchmark Metrics

1. **Task 1: Rainfall Amount Regression (`imd_rainfall_mm`)**
   - Metrics: MAE, RMSE, R² (evaluated on original millimeter scale).
2. **Task 2: Rainfall Intensity Classification (`rain_intensity_class`)**
   - Metrics: F1-Macro, Accuracy, Multiclass Log Loss.
3. **Task 3: Cloudburst Risk Detection (`cloudburst_flag`)**
   - Metrics: AUC-PR (Primary metric for imbalanced binary tasks), F1 Score, ROC-AUC.
4. **Task 4: Landslide Risk Prediction (`landslide_risk`)**
   - Metrics: AUC-PR, F1 Score, ROC-AUC.

---

## 4. Full-Stack Digital Twin Integration

- **FastAPI Backend (`backend/`)**: Exposes prediction endpoints, station data APIs, and risk alert notifications.
- **Next.js Dashboard (`frontend/`)**: Renders dynamic map layers (rainfall intensity, landslide risk, cloudburst alerts) and analytics dashboards.
- **Agentic AI Orchestrator (`orchestrator_agent/`, `prediction_agent/`, `alert_risk_agent/`)**: Powered by LangGraph agents for automated reasoning, anomaly detection, and early warning generation.

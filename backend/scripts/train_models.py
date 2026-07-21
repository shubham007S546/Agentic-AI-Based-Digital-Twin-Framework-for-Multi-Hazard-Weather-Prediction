import os
import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
import joblib

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "ml_models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DISTRICTS = {
    "Mandi": {"lat": 31.5892, "lon": 76.9182},
    "Kullu": {"lat": 31.9578, "lon": 77.1095},
    "Chamba": {"lat": 32.5534, "lon": 76.1258},
}

async def fetch_historical_weather(district_name: str, coords: dict, days: int = 90) -> pd.DataFrame:
    """Fetch historical weather data from Open-Meteo archive API."""
    logger.info(f"Fetching {days} days of historical data for {district_name}...")
    
    end_date = datetime.now(timezone.utc) - timedelta(days=2) # Archive data is usually delayed by a couple days
    start_date = end_date - timedelta(days=days)
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,surface_pressure,cloud_cover,wind_speed_10m",
        "timezone": "UTC"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            hourly = data.get("hourly", {})
            if not hourly:
                logger.warning(f"No hourly data found for {district_name}")
                return pd.DataFrame()
                
            df = pd.DataFrame(hourly)
            df['time'] = pd.to_datetime(df['time'])
            df['district'] = district_name
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {district_name}: {e}")
            return pd.DataFrame()

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add engineered features for training."""
    logger.info("Engineering features...")
    df = df.copy()
    
    # Time-based features
    df['hour'] = df['time'].dt.hour
    df['day_of_year'] = df['time'].dt.dayofyear
    df['month'] = df['time'].dt.month
    
    # Sort for rolling operations
    df = df.sort_values(by=['district', 'time']).reset_index(drop=True)
    
    # Shift targets to predict future (e.g., predict next hour's precipitation)
    # This is a simplified approach. We'll predict precipitation based on current/past states.
    df['target_precipitation'] = df.groupby('district')['precipitation'].shift(-1)
    
    # Lag features
    df['temp_lag1'] = df.groupby('district')['temperature_2m'].shift(1)
    df['humidity_lag1'] = df.groupby('district')['relative_humidity_2m'].shift(1)
    df['precip_lag1'] = df.groupby('district')['precipitation'].shift(1)
    
    # Rolling stats
    df['precip_roll_3h'] = df.groupby('district')['precipitation'].transform(lambda x: x.rolling(3, min_periods=1).sum())
    
    # Drop rows with NaNs caused by shifting/rolling
    df = df.dropna().reset_index(drop=True)
    
    return df

def train_and_evaluate_models(X_train, X_test, y_train, y_test):
    """Train multiple models and evaluate them."""
    logger.info("Training models...")
    
    models = {
        "LinearRegression": LinearRegression(),
        "DecisionTree": DecisionTreeRegressor(max_depth=10, random_state=42),
        "RandomForest": RandomForestRegressor(n_estimators=50, max_depth=10, random_state=42, n_jobs=-1),
        "XGBoost": xgb.XGBRegressor(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42, n_jobs=-1),
        "LightGBM": lgb.LGBMRegressor(n_estimators=100, max_depth=6, learning_rate=0.1, random_state=42, n_jobs=-1, verbose=-1),
        "CatBoost": CatBoostRegressor(iterations=100, depth=6, learning_rate=0.1, random_state=42, verbose=0)
    }
    
    results = {}
    trained_models = {}
    
    for name, model in models.items():
        logger.info(f"  Training {name}...")
        model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        
        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        r2 = r2_score(y_test, preds)
        
        # Simple MAPE approximation (avoiding division by zero)
        mape = np.mean(np.abs((y_test - preds) / (y_test + 1e-8))) * 100
        
        results[name] = {
            "mae": float(mae),
            "rmse": float(rmse),
            "r2": float(r2),
            "mape": float(mape)
        }
        trained_models[name] = model
        
    return trained_models, results

async def main():
    logger.info("Starting model training pipeline...")
    
    # 1. Fetch data
    tasks = [fetch_historical_weather(name, coords, days=90) for name, coords in DISTRICTS.items()]
    dfs = await asyncio.gather(*tasks)
    
    raw_df = pd.concat([d for d in dfs if not d.empty], ignore_index=True)
    if raw_df.empty:
        logger.error("Failed to collect any historical data. Exiting.")
        return
        
    logger.info(f"Collected {len(raw_df)} rows of historical data.")
    
    # 2. Engineer features
    processed_df = engineer_features(raw_df)
    logger.info(f"Engineered features. Usable rows: {len(processed_df)}")
    
    # Define features and target
    features = [
        'temperature_2m', 'relative_humidity_2m', 'surface_pressure', 
        'cloud_cover', 'wind_speed_10m', 'hour', 'day_of_year', 'month',
        'temp_lag1', 'humidity_lag1', 'precip_lag1', 'precip_roll_3h'
    ]
    target = 'target_precipitation'
    
    X = processed_df[features]
    y = processed_df[target]
    
    # Split data (using simple random split for this demo, though time-series split is better for real prod)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # 3. Train models
    models, metrics = train_and_evaluate_models(X_train, X_test, y_train, y_test)
    
    # 4. Save models and metrics
    logger.info("Saving models and metrics...")
    
    metrics_path = MODELS_DIR / "training_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
        
    for name, model in models.items():
        model_path = MODELS_DIR / f"rainfall_{name.lower()}.pkl"
        joblib.dump(model, model_path)
        
    logger.info(f"Pipeline completed successfully. Models saved to {MODELS_DIR}")
    
    # Print summary
    print("\nTraining Results Summary:")
    print("-" * 50)
    for name, m in metrics.items():
        print(f"{name:16} | MAE: {m['mae']:.4f} | R2: {m['r2']:.4f}")
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.main import lifespan, create_application
from app.agents.agent_registry import get_agent_registry
from app.api.v1.routers.prediction_router import get_rainfall_predictions, get_landslide_predictions
from app.api.v1.routers.weather_router import get_current_weather, get_forecast

async def main():
    app = create_application()
    print("--- TESTING LIFESPAN & AGENT REGISTRATION ---")
    async with lifespan(app):
        mgr = get_agent_registry()
        agents = mgr.list_agents()
        print(f"Total Registered Agents: {len(agents)}")
        for a in agents:
            print(f"  - Agent: {a.get('name')} | Desc: {a.get('description', '')[:40]}...")
        
        print("\n--- TESTING WEATHER ENDPOINTS ---")
        curr = await get_current_weather("Mandi")
        print("Mandi Current Weather:", curr["data"]["condition"], f"Temp: {curr['data']['temperature']}°C")
        
        fc = await get_forecast("Mandi", days=3)
        print("Mandi Forecast Days Count:", len(fc["data"]))

        print("\n--- TESTING PREDICTION ENDPOINTS ---")
        rain_pred = await get_rainfall_predictions()
        print("Rainfall Predictions Districts Count:", len(rain_pred["data"]))
        
        landslide_pred = await get_landslide_predictions()
        print("Landslide Predictions Slope Zones Count:", len(landslide_pred["slope_zones"]))

if __name__ == "__main__":
    asyncio.run(main())

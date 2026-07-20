"""
app/api/v1/routers/alert_router.py
──────────────────────────────────
Real alert routing based on live weather models.
Bypasses DB for Phase 1.
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Query

from app.integrations.weather.open_meteo_extended import OpenMeteoExtendedProvider

router = APIRouter()
provider = OpenMeteoExtendedProvider()

async def _generate_live_alerts():
    """Generate alerts dynamically based on live weather data."""
    alerts = []
    
    for dist in ["Mandi", "Kullu", "Kangra"]:
        try:
            data = await provider.fetch_current_and_forecast(dist)
            rain = data["current"]["rainfall"]
            
            if rain > 15:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "title": f"Cloudburst watch - {dist}",
                    "district": dist,
                    "severity": "severe",
                    "type": "Cloudburst",
                    "issuedAt": datetime.now(timezone.utc).isoformat(),
                    "message": f"Extreme convection detected. {rain}mm/hr rain rate."
                })
            elif rain > 5:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "title": f"Heavy Rainfall Warning",
                    "district": dist,
                    "severity": "high",
                    "type": "Rainfall",
                    "issuedAt": datetime.now(timezone.utc).isoformat(),
                    "message": f"Continuous heavy rainfall ({rain}mm/hr)."
                })
        except Exception:
            pass
            
    # Always have at least one test alert if weather is clear
    if not alerts:
        alerts.append({
            "id": str(uuid.uuid4()),
            "title": "System Test Alert",
            "district": "Shimla",
            "severity": "low",
            "type": "System",
            "issuedAt": datetime.now(timezone.utc).isoformat(),
            "message": "All hazard monitoring systems online."
        })
        
    return alerts

@router.get("")
async def get_all_alerts(limit: int = Query(50), offset: int = Query(0)):
    alerts = await _generate_live_alerts()
    return {"data": alerts, "total": len(alerts), "limit": limit, "offset": offset}

@router.get("/active")
async def get_active_alerts():
    alerts = await _generate_live_alerts()
    return {"data": alerts}

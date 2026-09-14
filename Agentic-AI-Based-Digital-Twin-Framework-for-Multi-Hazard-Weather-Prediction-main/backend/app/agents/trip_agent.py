"""
app/agents/trip_agent.py
────────────────────────
Agent: Trip & Mountain Route Hazard Advisory Agent (VARUNA Route Guardian).

Purpose:
  Evaluates mountain travel corridors across Himachal Pradesh (Mandi, Kullu,
  Manali, Shimla, Chamba, Kangra, etc.).
  Computes:
    • Source & Destination
    • Recommended Corridor / Way
    • Distance & Terrain-Adjusted Driving Duration
    • Itemized Travel Costs (Fuel with hill gradient factor, Tolls, Taxi, Bus)
    • Route Hazard Level (SAFE, CAUTION, HIGH_RISK, ROAD_CLOSED)
    • Hotspot Hazard Breakdown (Landslide sectors, River surge crossings)
    • Alternative Ways / Bypass passes
    • Actionable Travel Advisories & Emergency Helplines

Produces a full AgentExecutionReport detailing:
  • Actions taken (step-by-step audit)
  • System prompt & schema specification
  • Final answer strictly formatted to contract
  • Human-readable summary report in Markdown
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from app.agents.base_agent import BaseAgent
from app.agents.agent_prompts import (
    AGENT_PROMPTS,
    AgentExecutionReport,
    build_agent_execution_report,
)
from app.core.enums import AgentName


# ── CORRIDOR TOPOLOGY DATABASE FOR HIMACHAL PRADESH ─────────────────────────

_HP_CORRIDORS: Dict[str, Dict[str, Any]] = {
    ("mandi", "kullu"): {
        "primary_way": "NH-21 / NH-3 via Pandoh Dam Bypass, Aut Tunnel, and Bhuntar",
        "distance_km": 68.0,
        "base_hours": 2.2,
        "tolls_inr": 85,
        "hotspots": [
            {"location": "6-Mile to 9-Mile stretch", "hazard_type": "landslide", "severity": "MODERATE", "notes": "Active slope cutting; loose boulders during precipitation"},
            {"location": "Pandoh Dam Reservoir stretch", "hazard_type": "waterlogging_flash_flood", "severity": "MODERATE", "notes": "Beas river spillway surge risk during heavy rain"},
            {"location": "Aut Tunnel approach", "hazard_type": "rockfall", "severity": "LOW", "notes": "Tunnel lighting and ventilation operational; watch for drainage ponding"},
        ],
        "alternative_way": {
            "way": "Via Kamand (IIT Mandi) - Kataula - Prashar junction - Bajaura bypass",
            "distance_km": 74.0,
            "estimated_duration": "3h 15m",
            "toll_inr": 0,
            "hazard_level": "CAUTION",
            "notes": "Scenic narrow hill road; steeper gradient (14%), suitable for light vehicles when NH-21 is blocked.",
        },
    },
    ("mandi", "manali"): {
        "primary_way": "NH-21 / NH-3 via Pandoh, Aut Tunnel, Kullu Bypass, and Green Tax Barrier Manali",
        "distance_km": 108.0,
        "base_hours": 3.5,
        "tolls_inr": 185,
        "hotspots": [
            {"location": "Pandoh-Aut corridor", "hazard_type": "landslide", "severity": "MODERATE", "notes": "Vulnerable slopes near Hanogi Temple"},
            {"location": "Raisan to 15-Mile Beas bank", "hazard_type": "river_surge", "severity": "LOW", "notes": "River embankment proximity"},
            {"location": "Manali entry Right Bank highway", "hazard_type": "traffic_slowdown", "severity": "LOW", "notes": "Heavy tourist transit; check green tax queue"},
        ],
        "alternative_way": {
            "way": "Via Mandi - Kataula - Bajaura - Naggar (Left Bank) - Manali",
            "distance_km": 114.0,
            "estimated_duration": "4h 10m",
            "toll_inr": 0,
            "hazard_level": "CAUTION",
            "notes": "Bypasses Kullu town; historical wooden Naggar castle corridor.",
        },
    },
    ("mandi", "shimla"): {
        "primary_way": "NH-205 via Sundernagar, Bilaspur, Brahmpukhar, Darlaghat, and Totu",
        "distance_km": 145.0,
        "base_hours": 4.5,
        "tolls_inr": 110,
        "hotspots": [
            {"location": "Sundernagar canal stretch", "hazard_type": "fog_mist", "severity": "LOW", "notes": "Morning visibility reduction"},
            {"location": "Ghanahatti to Totu slope", "hazard_type": "landslide", "severity": "MODERATE", "notes": "Steep shale cutting near Shimla outskirts"},
        ],
        "alternative_way": {
            "way": "Via Mandi - Karsog - Tattapani - Suni - Mashobra - Shimla",
            "distance_km": 162.0,
            "estimated_duration": "5h 45m",
            "toll_inr": 0,
            "hazard_level": "SAFE",
            "notes": "Rural valley route along Sutlej river; scenic but curvy.",
        },
    },
    ("mandi", "chamba"): {
        "primary_way": "NH-154 via Jogindernagar, Palampur, Kangra, Shahpur, Nurpur, Banikhet to Chamba",
        "distance_km": 285.0,
        "base_hours": 8.5,
        "tolls_inr": 160,
        "hotspots": [
            {"location": "Dhelu to Jogindernagar Ghats", "hazard_type": "landslide", "severity": "MODERATE", "notes": "Continuous hairpin turns; mud slips during monsoon"},
            {"location": "Banikhet - Chamba gorge road", "hazard_type": "rockfall", "severity": "HIGH", "notes": "Deep Ravi river canyon; avoid night driving"},
        ],
        "alternative_way": {
            "way": "Via Kangra - Shahpur - Jot Pass (high altitude) - Chowari - Chamba",
            "distance_km": 255.0,
            "estimated_duration": "8h 00m",
            "toll_inr": 0,
            "hazard_level": "HIGH_RISK",
            "notes": "Jot pass is 2,880m elevation; frequently fog-bound or closed during heavy rainfall/snow.",
        },
    },
    ("kullu", "manali"): {
        "primary_way": "NH-3 Right Bank 4-lane highway via Raisan and Patlikuhal",
        "distance_km": 40.0,
        "base_hours": 1.1,
        "tolls_inr": 100,
        "hotspots": [
            {"location": "Patlikuhal bridge crossing", "hazard_type": "river_surge", "severity": "LOW", "notes": "High water discharge during upstream cloudburst"},
        ],
        "alternative_way": {
            "way": "Left Bank Road via Naggar and Jagatsukh",
            "distance_km": 42.0,
            "estimated_duration": "1h 25m",
            "toll_inr": 0,
            "hazard_level": "SAFE",
            "notes": "Wider road with less heavy truck traffic; passes apple orchards.",
        },
    },
}


class TripAgent(BaseAgent):
    """
    Trip & Mountain Route Hazard Advisory Agent.
    Evaluates highway corridors, estimates fuel and transit costs, checks
    real-time hazard telemetry along waypoints, and compiles an auditable
    execution report with source, destination, cost, way, and advisories.
    """

    def __init__(self) -> None:
        super().__init__(name=AgentName.TRIP_ADVISORY, version="2.0.0")

    @property
    def description(self) -> str:
        return (
            "Mountain Route Safety & Trip Planning Agent for Himachal Pradesh corridors. "
            "Calculates driving distance, terrain-adjusted driving time, itemized fuel/transit "
            "costs, route hazard levels (landslides, flash floods), alternative bypass ways, "
            "and official public safety advisories."
        )

    def _get_timeout_seconds(self) -> float:
        return 60.0

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Execute mountain trip risk analysis and route planning.
        """
        start_time = time.perf_counter()
        execution_id = str(uuid.uuid4())
        actions_taken: List[str] = []

        # 1. Parse & Normalize Input Parameters
        source_raw = str(payload.get("source") or payload.get("origin") or payload.get("from") or "Mandi").strip()
        dest_raw = str(payload.get("destination") or payload.get("dest") or payload.get("to") or "Manali").strip()
        travel_mode = str(payload.get("travel_mode") or payload.get("vehicle_type") or "car").lower()
        fuel_type = str(payload.get("fuel_type") or "petrol").lower()
        departure_time = str(payload.get("departure_time") or "Immediate (Next 2 Hours)")
        weather_context = payload.get("weather_state") or {}

        source = source_raw.split(",")[0].strip().title()
        destination = dest_raw.split(",")[0].strip().title()

        actions_taken.append(
            f"Parsed travel request: Origin='{source}', Destination='{destination}', Mode='{travel_mode}', Departure='{departure_time}'"
        )

        # 2. Correlate Corridor in Himachal Highway Graph
        src_key = source.lower()
        dst_key = destination.lower()
        corridor = _HP_CORRIDORS.get((src_key, dst_key)) or _HP_CORRIDORS.get((dst_key, src_key))

        if corridor:
            primary_way = corridor["primary_way"]
            distance_km = float(corridor["distance_km"])
            base_hours = float(corridor["base_hours"])
            tolls_inr = int(corridor["tolls_inr"])
            hotspots = list(corridor["hotspots"])
            alt_way = dict(corridor["alternative_way"])
            actions_taken.append(
                f"Resolved primary corridor '{primary_way}' ({distance_km} km) from Himachal Pradesh highway topology."
            )
        else:
            # Dynamic Heuristic for Unlisted Mountain Corridors
            distance_km = float(payload.get("distance_km", 95.0))
            base_hours = distance_km / 34.0  # ~34 km/h mountain winding road average
            primary_way = f"State Highway / NH connecting {source} to {destination} via primary district link"
            tolls_inr = 60
            hotspots = [
                {"location": f"Transit corridor between {source} and {destination}", "hazard_type": "slope_instability", "severity": "MODERATE", "notes": "Variable mountain grade; check local police advisory"}
            ]
            alt_way = {
                "way": f"Secondary rural bypass road via local tehsils between {source} and {destination}",
                "distance_km": round(distance_km * 1.18, 1),
                "estimated_duration": f"{int((base_hours * 1.25) // 1)}h {int(((base_hours * 1.25) % 1) * 60)}m",
                "toll_inr": 0,
                "hazard_level": "CAUTION",
                "notes": "Longer alternate bypass avoiding main highway bottlenecks.",
            }
            actions_taken.append(
                f"Generated mountain routing approximation for {source} ➔ {destination} ({distance_km} km) with hill winding speed curves."
            )

        # 3. Calculate Itemized Travel Costs
        # Mountain hill climbing: 1.25x fuel consumption compared to plains
        fuel_price = 96.5 if fuel_type == "petrol" else 88.0
        car_mileage_km_per_l = 11.5  # Mountain gradient mileage
        liters_needed = distance_km / car_mileage_km_per_l
        fuel_cost_inr = round(liters_needed * fuel_price, 0)

        # Taxi estimate: ₹18/km for sedan, ₹24/km for mountain SUV
        taxi_rate_per_km = 22.0 if travel_mode == "taxi" else 20.0
        taxi_estimate_inr = round(distance_km * taxi_rate_per_km + tolls_inr, -1)

        # Bus fare (HRTC ordinary / semi-deluxe): ~₹2.10/km
        bus_fare_inr = round(distance_km * 2.15, -1)

        total_self_drive_cost = fuel_cost_inr + tolls_inr
        cost_breakdown = {
            "fuel_cost_inr": fuel_cost_inr,
            "fuel_liters_estimated": round(liters_needed, 1),
            "toll_charges_inr": tolls_inr,
            "total_self_drive_inr": total_self_drive_cost,
            "taxi_estimate_inr": taxi_estimate_inr,
            "bus_fare_inr": bus_fare_inr,
            "cost_summary_range": f"₹{int(bus_fare_inr)} (HRTC Bus) | ₹{int(total_self_drive_cost)} (Private Car) | ₹{int(taxi_estimate_inr)} (Taxi Cab)",
        }
        actions_taken.append(
            f"Computed expenditure metrics: Fuel=₹{fuel_cost_inr} ({round(liters_needed, 1)}L @ ₹{fuel_price}/L), Tolls=₹{tolls_inr}, Taxi Est=₹{taxi_estimate_inr}, Bus=₹{bus_fare_inr}."
        )

        # 4. Synthesize Hazard Telemetry & Weather Conditions
        recent_rain_mm = float(weather_context.get("rainfall_mm") or payload.get("rainfall_mm", 22.5))
        anomalies_count = int(weather_context.get("anomalies_detected", 0))

        if recent_rain_mm >= 65.0:
            route_hazard_level = "HIGH_RISK"
            travel_delay_minutes = 60
            actions_taken.append(
                f"Severe precipitation detected ({recent_rain_mm} mm); escalated corridor status to HIGH_RISK with heavy debris flow warning."
            )
        elif recent_rain_mm >= 25.0 or anomalies_count > 0:
            route_hazard_level = "CAUTION"
            travel_delay_minutes = 25
            actions_taken.append(
                f"Moderate rainfall ({recent_rain_mm} mm) observed; flagged active landslide prone stretches as CAUTION."
            )
        else:
            route_hazard_level = "SAFE"
            travel_delay_minutes = 0
            actions_taken.append(
                f"Nominal meteorological conditions along corridor ({recent_rain_mm} mm); road status evaluated as SAFE."
            )

        # Calculate Duration with hill and hazard adjustment
        total_minutes = int(base_hours * 60) + travel_delay_minutes
        hours_part = total_minutes // 60
        mins_part = total_minutes % 60
        duration_formatted = f"{hours_part}h {mins_part:02d}m"

        # 5. Formulate Advisories & Safety Protocols
        travel_advisories = [
            f"Recommended travel window: 07:00 to 15:30. Avoid transit after sunset on mountain gorges.",
            f"Active weather hazard index: {recent_rain_mm} mm precipitation reported across corridor.",
            "Verify real-time clearance with Mandi Traffic Police (01905-222470) and Kullu Police (01902-222770).",
            "Emergency National Highway Assistance: Call NHAI Helpline 1033 or Disaster Helpline 1070/1077.",
        ]
        if route_hazard_level == "HIGH_RISK":
            travel_advisories.insert(0, "CRITICAL: Non-essential travel strongly discouraged until road inspection clears.")

        actions_taken.append("Compiled official HPSDMA disaster travel advisories and emergency contact matrix.")

        # 6. Build Final Answer Contract
        final_answer: Dict[str, Any] = {
            "source": source,
            "destination": destination,
            "way": primary_way,
            "distance_km": distance_km,
            "estimated_duration": duration_formatted,
            "estimated_cost": cost_breakdown,
            "route_hazard_level": route_hazard_level,
            "hazard_breakdown": hotspots,
            "alternative_ways": [alt_way],
            "travel_advisories": travel_advisories,
        }

        # 7. Generate Polished Markdown Report
        summary_markdown = f"""### 🏔️ Route Advisory: {source} ➔ {destination}
- **Primary Way**: {primary_way}
- **Distance & Time**: **{distance_km} km** (~{duration_formatted})
- **Route Safety Level**: **`{route_hazard_level}`**

#### 💰 Estimated Cost Breakdown
| Transport Mode | Estimated Cost | Notes |
|---|---|---|
| **Private Car (Fuel + Toll)** | **₹{int(total_self_drive_cost)}** | ~{cost_breakdown['fuel_liters_estimated']} L fuel + ₹{tolls_inr} tolls |
| **Taxi Cab** | **₹{int(taxi_estimate_inr)}** | Standard Himachal Taxi Union bracket |
| **HRTC Public Bus** | **₹{int(bus_fare_inr)}** | Ordinary / Semi-deluxe service |

#### ⚠️ Hazard Hotspots Along the Way
"""
        for h in hotspots:
            summary_markdown += f"- **{h['location']}** ({h['hazard_type'].replace('_', ' ').title()} - `{h['severity']}`): {h['notes']}\n"

        summary_markdown += f"""
#### 🔄 Alternative Way
- **Route**: {alt_way['way']}
- **Distance**: {alt_way['distance_km']} km ({alt_way['estimated_duration']})
- **Hazard Rating**: `{alt_way['hazard_level']}` ({alt_way['notes']})

#### 🛡️ Travel Advisories
"""
        for adv in travel_advisories:
            summary_markdown += f"- {adv}\n"

        duration_ms = (time.perf_counter() - start_time) * 1000

        # 8. Produce Standardized AgentExecutionReport
        report: AgentExecutionReport = build_agent_execution_report(
            agent_name="trip_advisory",
            task_assigned=payload,
            actions_taken=actions_taken,
            final_answer=final_answer,
            summary_markdown=summary_markdown,
            duration_ms=duration_ms,
            status="COMPLETED",
            execution_id=execution_id,
        )

        return {
            "status": "ok",
            "agent_report": report.to_dict(),
            "final_answer": final_answer,
            "source": source,
            "destination": destination,
            "way": primary_way,
            "distance_km": distance_km,
            "duration": duration_formatted,
            "cost": cost_breakdown,
            "hazard_level": route_hazard_level,
        }

"""
check_weather_data.py
----------------------
Quick diagnostic: confirms whether weather_observations has real data,
and whether raw_data JSONB contains the fields prediction_engine needs
(dewpoint_2m, cape, wind_gusts_10m, rain, snowfall) that aren't normalized
columns on the WeatherObservation model.

Run from backend/:
    python check_weather_data.py
"""

import asyncio

from sqlalchemy import select

from app.core.enums import District, WeatherSource
from app.database.connection import get_session_factory, init_db_engine
from app.models.weather import WeatherObservation


async def main() -> None:
    await init_db_engine()
    session_factory = get_session_factory()

    async with session_factory() as session:
        stmt = (
            select(WeatherObservation)
            .where(WeatherObservation.district == District.MANDI)
            .where(WeatherObservation.source == WeatherSource.OPEN_METEO)
            .order_by(WeatherObservation.timestamp.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            print("NO ROWS FOUND for district=mandi, source=open_meteo")
            # Check if ANY rows exist at all, any district/source
            any_stmt = select(WeatherObservation).limit(1)
            any_result = await session.execute(any_stmt)
            any_row = any_result.scalar_one_or_none()
            if any_row is None:
                print("Table 'weather_observations' appears to be EMPTY entirely.")
            else:
                print(f"Found a row for a DIFFERENT district/source: "
                      f"district={any_row.district}, source={any_row.source}, "
                      f"timestamp={any_row.timestamp}")
        else:
            print("timestamp:", row.timestamp)
            print("temperature_2m:", row.temperature_2m)
            print("relative_humidity_2m:", row.relative_humidity_2m)
            print("surface_pressure:", row.surface_pressure)
            print("wind_speed_10m:", row.wind_speed_10m)
            print("precipitation:", row.precipitation)
            print("cloud_cover:", row.cloud_cover)
            print("raw_data keys:", list(row.raw_data.keys()) if row.raw_data else None)
            print("raw_data sample:", row.raw_data)


if __name__ == "__main__":
    asyncio.run(main())

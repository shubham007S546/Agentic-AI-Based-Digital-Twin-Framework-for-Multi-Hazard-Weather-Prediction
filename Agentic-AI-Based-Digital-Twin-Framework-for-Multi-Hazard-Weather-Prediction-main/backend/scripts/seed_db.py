"""
scripts/seed_db.py
──────────────────
Populate the PostgreSQL database with initial real/mock seed data
(Admin users, sample weather stations, active alerts).
"""

import asyncio
import sys
import os

# Append project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database.connection import init_db_engine, get_session_factory
from app.models.user import User
from app.models.weather import WeatherObservation
from app.models.alert import Alert
from app.core.enums import UserRole, HazardType, AlertSeverity, AlertStatus
from app.security.authentication.passwords import get_password_hash


async def seed():
    admin_email = os.environ.get("SEED_ADMIN_EMAIL")
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not admin_email or not admin_password or len(admin_password) < 12:
        raise RuntimeError("SEED_ADMIN_EMAIL and a 12+ character SEED_ADMIN_PASSWORD are required")
    print("Connecting to database...")
    await init_db_engine()
    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Seed Admin User
        stmt = select(User).where(User.email == admin_email)
        res = await session.execute(stmt)
        admin = res.scalar_one_or_none()
        if not admin:
            admin = User(
                email=admin_email,
                hashed_password=get_password_hash(admin_password),
                full_name="Dr. Rajat Sharma",
                role=UserRole.ADMIN,
                organization="IIT Mandi",
                department="SCEE",
                is_active=True,
                is_verified=True,
            )
            session.add(admin)
            print(f"Seeding: Created Admin User ({admin_email})")
        else:
            admin.hashed_password = get_password_hash(admin_password)
            print("Admin user updated with fresh password hash.")
        await session.commit()

        # 2. Seed Weather Observations (to populate stations)
        obs_stmt = select(WeatherObservation).limit(1)
        obs_res = await session.execute(obs_stmt)
        if not obs_res.scalar_one_or_none():
            # Add some sample observations
            obs1 = WeatherObservation(
                station_id="AWS-MND-01",
                district="mandi",
                latitude=31.7087,
                longitude=76.9320,
                temperature=24.5,
                humidity=82.0,
                rainfall_1h=4.2,
                rainfall_24h=18.5,
                wind_speed=12.4,
                pressure=910.2,
            )
            obs2 = WeatherObservation(
                station_id="AWS-KUL-02",
                district="kullu",
                latitude=31.9578,
                longitude=77.1095,
                temperature=19.2,
                humidity=88.0,
                rainfall_1h=12.8,
                rainfall_24h=42.0,
                wind_speed=8.5,
                pressure=880.4,
            )
            session.add_all([obs1, obs2])
            print("Seeding: Created initial Weather Observations")
        else:
            print("Weather observations already exist.")

        # 3. Seed Active Alerts
        alert_stmt = select(Alert).limit(1)
        alert_res = await session.execute(alert_stmt)
        if not alert_res.scalar_one_or_none():
            alert1 = Alert(
                title="Heavy Rainfall Warning",
                message="Heavy rainfall warning issued for Mandi district over the next 24 hours. Possibility of minor floods in low-lying areas.",
                severity=AlertSeverity.HIGH,
                status=AlertStatus.ACTIVE,
                hazard_type=HazardType.RAINFALL,
                district="mandi",
            )
            alert2 = Alert(
                title="Landslide Risk Warning",
                message="High landslide vulnerability detected along Mandi-Kullu national highway. Travelers are advised to avoid travel during night hours.",
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.ACTIVE,
                hazard_type=HazardType.LANDSLIDE,
                district="mandi",
            )
            session.add_all([alert1, alert2])
            print("Seeding: Created initial active Alerts")
        else:
            print("Alerts already exist.")

        await session.commit()
    print("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())

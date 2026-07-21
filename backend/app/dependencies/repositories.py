"""
app/dependencies/repositories.py
────────────────────────────────
FastAPI dependencies for injecting repositories.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.repositories.interfaces.user_repo import IUserRepository
from app.repositories.user_repo_impl import UserRepositoryImpl
from app.repositories.interfaces.weather_repo import IWeatherRepository
from app.repositories.weather_repo_impl import WeatherRepositoryImpl
from app.repositories.interfaces.prediction_repo import IPredictionRepository
from app.repositories.prediction_repo_impl import PredictionRepositoryImpl
from app.repositories.interfaces.twin_repo import ITwinRepository
from app.repositories.twin_repo_impl import TwinRepositoryImpl
from app.repositories.interfaces.alert_repo import IAlertRepository
from app.repositories.alert_repo_impl import AlertRepositoryImpl
from app.repositories.interfaces.report_repo import IReportRepository
from app.repositories.report_repo_impl import ReportRepositoryImpl


def get_user_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> IUserRepository:
    """Provides a UserRepository bound to the current database session."""
    return UserRepositoryImpl(session)


def get_weather_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> IWeatherRepository:
    """Provides a WeatherRepository bound to the current database session."""
    return WeatherRepositoryImpl(session)


def get_prediction_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> IPredictionRepository:
    """Provides a PredictionRepository bound to the current database session."""
    return PredictionRepositoryImpl(session)


def get_twin_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> ITwinRepository:
    """Provides a TwinRepository bound to the current database session."""
    return TwinRepositoryImpl(session)


def get_alert_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> IAlertRepository:
    """Provides an AlertRepository bound to the current database session."""
    return AlertRepositoryImpl(session)


def get_report_repository(session: Annotated[AsyncSession, Depends(get_async_db)]) -> IReportRepository:
    """Provides a ReportRepository bound to the current database session."""
    return ReportRepositoryImpl(session)




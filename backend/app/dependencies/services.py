"""
app/dependencies/services.py
────────────────────────────
FastAPI dependencies for injecting services.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.database.session import get_async_db

from app.cache.redis_client import get_cache_client
from app.dependencies.repositories import (
    get_user_repository,
    get_weather_repository,
    get_prediction_repository,
    get_twin_repository,
    get_alert_repository,
    get_report_repository,
)
from app.repositories.interfaces.user_repo import IUserRepository
from app.repositories.interfaces.weather_repo import IWeatherRepository
from app.services.auth_service import AuthService
from app.services.interfaces.auth_service import IAuthService
from app.services.interfaces.user_service import IUserService
from app.services.user_service_impl import UserServiceImpl
from app.services.interfaces.weather_service import IWeatherService
from app.services.weather_service_impl import WeatherServiceImpl
from app.integrations.weather.open_meteo import OpenMeteoProvider
from app.repositories.interfaces.prediction_repo import IPredictionRepository
from app.services.interfaces.prediction_service import IPredictionService
from app.services.prediction_service_impl import PredictionServiceImpl
from app.ml.inference.rainfall_model import DummyRainfallPredictor
from app.core.enums import HazardType

from app.repositories.interfaces.twin_repo import ITwinRepository
from app.services.interfaces.twin_service import ITwinService
from app.services.twin_service_impl import TwinServiceImpl

from app.repositories.interfaces.alert_repo import IAlertRepository
from app.services.interfaces.alert_service import IAlertService
from app.services.alert_service_impl import AlertServiceImpl

from app.repositories.interfaces.report_repo import IReportRepository
from app.services.interfaces.report_service import IReportService
from app.services.report_service_impl import ReportServiceImpl



def get_auth_service(
    db: Annotated[AsyncSession, Depends(get_async_db)],
    redis: Annotated[Redis, Depends(get_cache_client)],
) -> IAuthService:
    """Provides the Authentication Service."""
    return AuthService(db=db, redis=redis)


def get_user_service(
    user_repo: Annotated[IUserRepository, Depends(get_user_repository)],
) -> IUserService:
    """Provides the User Service."""
    return UserServiceImpl(user_repo=user_repo)


def get_weather_service(
    weather_repo: Annotated[IWeatherRepository, Depends(get_weather_repository)],
) -> IWeatherService:
    """Provides the Weather Service, with pre-configured providers."""
    providers = [OpenMeteoProvider()]
    return WeatherServiceImpl(weather_repo=weather_repo, providers=providers)


def get_prediction_service(
    prediction_repo: Annotated[IPredictionRepository, Depends(get_prediction_repository)],
    weather_service: Annotated[IWeatherService, Depends(get_weather_service)],
) -> IPredictionService:
    """Provides the Prediction Service backed by the global ModelRegistry."""
    from app.ml.models_registry.registry import get_model_registry
    registry = get_model_registry()
    return PredictionServiceImpl(
        prediction_repo=prediction_repo,
        weather_service=weather_service,
        model_registry=registry,
    )


def get_twin_service(
    twin_repo: Annotated[ITwinRepository, Depends(get_twin_repository)],
    weather_service: Annotated[IWeatherService, Depends(get_weather_service)],
) -> ITwinService:
    """Provides the Digital Twin Service."""
    return TwinServiceImpl(
        twin_repo=twin_repo,
        weather_service=weather_service,
    )


def get_alert_service(
    alert_repo: Annotated[IAlertRepository, Depends(get_alert_repository)],
) -> IAlertService:
    """Provides the Alert Service."""
    return AlertServiceImpl(
        alert_repo=alert_repo,
    )


def get_report_service(
    report_repo: Annotated[IReportRepository, Depends(get_report_repository)],
) -> IReportService:
    """Provides the Report Service."""
    return ReportServiceImpl(
        report_repo=report_repo,
    )





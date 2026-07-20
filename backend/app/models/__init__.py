"""
app/models/__init__.py
──────────────────────
Central registry for all SQLAlchemy models.

IMPORTANT: All models MUST be imported here so that Alembic's env.py
can detect them when autogenerating migrations. If a model is not imported
here, Alembic will think the table was deleted and create a drop table migration.
"""

from app.database.base import Base

# Domain models
from app.models.agent import AgentExecution
from app.models.alert import Alert, AlertNotification
from app.models.auth import BlacklistedToken, EmailVerificationToken, PasswordResetToken, RefreshToken
from app.models.digital_twin import Simulation, TwinState
from app.models.prediction import PredictionRequest
from app.models.report import Report
from app.models.user import User
from app.models.weather import WeatherObservation

# Expose everything to external modules
__all__ = [
    "Base",
    "AgentExecution",
    "Alert",
    "AlertNotification",
    "BlacklistedToken",
    "EmailVerificationToken",
    "PasswordResetToken",
    "PredictionRequest",
    "RefreshToken",
    "Report",
    "Simulation",
    "TwinState",
    "User",
    "WeatherObservation",
]

"""
tests/conftest.py
─────────────────
Pytest configuration and fixtures.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from app.core.config import get_settings


@pytest.fixture(scope="session")
def app():
    """Create a FastAPI application instance for testing."""
    return create_application()


@pytest.fixture(scope="session")
def client(app):
    """Create a TestClient for making HTTP requests."""
    return TestClient(app)


@pytest.fixture(scope="session")
def settings():
    """Access the application settings."""
    return get_settings()

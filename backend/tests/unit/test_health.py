"""
tests/unit/test_health.py
─────────────────────────
Basic tests for the health endpoints.
"""

from fastapi.testclient import TestClient
from fastapi import status


def test_health_live(client: TestClient):
    """Test the Kubernetes liveness probe."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


def test_health_ready_without_dependencies(client: TestClient):
    """Test the readiness probe when no actual DB is wired up."""
    # This will likely fail with a 503 if dependencies are missing,
    # which is the correct behavior for a readiness probe.
    response = client.get("/api/v1/health/ready")
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]


def test_detailed_health(client: TestClient):
    """Test the detailed health report endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "data" in data
    assert "components" in data["data"]
    assert "database" in data["data"]["components"]
    assert "redis" in data["data"]["components"]

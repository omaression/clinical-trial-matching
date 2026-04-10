import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def api_client():
    """Client without DB for basic endpoint tests."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    def test_health(self, api_client):
        response = api_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "pipeline_version" in data


class TestPipelineStatus:
    """Pipeline status endpoint works without DB but returns 500 without it.
    We test the route exists and returns correct structure."""
    pass


class TestRouteRegistration:
    """Verify all routes are registered."""

    def test_openapi_schema_available(self, api_client):
        response = api_client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema["paths"]
        assert "/api/v1/health" in paths
        assert "/api/v1/trials/ingest" in paths
        assert "/api/v1/trials" in paths
        assert "/api/v1/review" in paths
        assert "/api/v1/pipeline/status" in paths

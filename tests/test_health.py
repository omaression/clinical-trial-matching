import docker
import pytest

from app.main import app


def _docker_available():
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    data = response.json()
    assert data["status"] == "healthy"
    assert "pipeline_version" in data
    assert "database" in data
    assert data["database"] == "connected"
    assert "spacy_model" in data


@pytest.mark.skipif(not _docker_available(), reason="Docker not available")
def test_health_endpoint_returns_503_when_pipeline_unavailable(client, monkeypatch):
    monkeypatch.setattr(app.state, "spacy_model", "unavailable")
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.headers["X-Request-ID"]
    assert response.json()["status"] == "degraded"

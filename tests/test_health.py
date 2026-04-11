import docker
import pytest


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
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "pipeline_version" in data
    assert "database" in data
    assert data["database"] == "connected"
    assert "spacy_model" in data

def test_health_endpoint(client_no_db):
    response = client_no_db.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "pipeline_version" in data

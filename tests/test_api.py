import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_analyze_endpoint_no_file():
    response = client.post(
        "/api/v1/pdf/analyze",
        headers={"x-forwarded-by": "auth-gateway", "x-user-id": "test-user-123"}
    )
    # Should fail with 422 Unprocessable Entity since file is missing
    assert response.status_code == 422

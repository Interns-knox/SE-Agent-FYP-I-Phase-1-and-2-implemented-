"""Integration tests: require live Ollama and PostgreSQL. Run with: pytest -m integration"""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SAMPLE_DESCRIPTION = (
    "A small e-commerce platform for selling handmade crafts online."
)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_project(client):
    resp = client.post(
        "/projects",
        json={"name": "Integration Test Project", "description": SAMPLE_DESCRIPTION},
    )
    assert resp.status_code == 201
    yield resp.json()


@pytest.mark.integration
def test_extract_real_model(client, sample_project):
    project_id = sample_project["id"]
    response = client.post(f"/projects/{project_id}/extract")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "features" in data
    assert len(data["features"]) > 0
    for feature in data["features"]:
        assert feature["name"], "Feature name should not be empty"
        assert feature["description"], "Feature description should not be empty"
        assert feature["status"] == "PENDING_REVIEW"

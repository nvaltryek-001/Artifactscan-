import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_optional_tools():
    response = client.get("/api/readiness")
    assert response.status_code == 200
    assert "colmap" in response.json()
    assert "classifier" in response.json()


def test_create_and_retrieve_artifact():
    response = client.post("/api/artifacts", json={
        "title": "Test pottery",
        "category": "Pottery",
        "description": "Automated test record",
        "provenance": "Test fixture",
        "rights": "Test only",
    })
    assert response.status_code == 200
    artifact_id = response.json()["id"]
    detail = client.get(f"/api/artifacts/{artifact_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Test pottery"


def test_missing_artifact_is_404():
    response = client.get("/api/artifacts/not-a-real-id")
    assert response.status_code == 404


def test_csv_export():
    response = client.get("/api/reports/artifacts.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "title" in response.text
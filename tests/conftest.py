import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolate every test run: storage, database and dataset point at a temp dir
# BEFORE the app is imported, so real user data is never touched.
_TMP = Path(tempfile.mkdtemp(prefix="artifactscan-tests-"))
os.environ["ARTIFACTSCAN_STORAGE"] = str(_TMP / "storage")
os.environ["ARTIFACTSCAN_DATASET"] = str(_TMP / "dataset")
os.environ["ARTIFACTSCAN_MODEL_DIR"] = str(_TMP / "models")
os.environ.setdefault("ARTIFACTSCAN_RECON_ENGINE", "auto")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: runs a real reconstruction (about a minute)")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def artifact(client):
    r = client.post("/api/artifacts", json={"title": "Test amphora", "category": "Ceramics",
                                            "period": "c. 480 BCE", "material": "Terracotta"})
    assert r.status_code == 200
    return r.json()["id"]

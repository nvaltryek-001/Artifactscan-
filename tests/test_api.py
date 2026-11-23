import csv
import hashlib
import io
import json
import zipfile

from PIL import Image


def png_bytes(color=(180, 120, 60), size=(64, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def upload(client, artifact_id, n=3):
    files = [("files", (f"view_{i}.png", png_bytes((40 * i % 255, 90, 160)), "image/png")) for i in range(n)]
    return client.post(f"/api/artifacts/{artifact_id}/images", files=files)


# --------------------------------------------------------------- system
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_reports_optional_tools(client):
    body = client.get("/api/readiness").json()
    for key in ("colmap", "classifier", "reconstruction_engines", "reconstruction_engine_selected", "database"):
        assert key in body
    assert body["database"] is True
    assert body["classifier"] is False  # no checkpoint in the test model dir


def test_settings(client):
    body = client.get("/api/settings").json()
    assert body["min_reconstruction_images"] == 3
    assert "storage_bytes" in body


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "ArtifactScan" in r.text
    assert client.get("/static/viewer.js").status_code == 200


# --------------------------------------------------------------- artifacts
def test_create_and_retrieve_artifact(client):
    r = client.post("/api/artifacts", json={
        "title": "Test pottery", "category": "Pottery", "description": "Automated test record",
        "provenance": "Test fixture", "rights": "Test only",
    })
    assert r.status_code == 200
    artifact_id = r.json()["id"]
    detail = client.get(f"/api/artifacts/{artifact_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Test pottery"
    assert body["review_status"] == "draft"
    assert body["assets"] == [] and body["jobs"] == [] and body["predictions"] == []


def test_create_validation(client):
    assert client.post("/api/artifacts", json={"title": "", "category": "x"}).status_code == 422
    assert client.post("/api/artifacts", json={"category": "x"}).status_code == 422


def test_missing_artifact_is_404(client):
    assert client.get("/api/artifacts/not-a-real-id").status_code == 404
    assert client.get("/api/artifacts/00000000-0000-0000-0000-000000000000").status_code == 404


def test_patch_artifact(client, artifact):
    r = client.patch(f"/api/artifacts/{artifact}", json={"origin": "Attica", "review_status": "reviewed"})
    assert r.status_code == 200
    assert r.json()["origin"] == "Attica" and r.json()["review_status"] == "reviewed"
    assert client.patch(f"/api/artifacts/{artifact}", json={"review_status": "approved!"}).status_code == 422


def test_list_and_search(client, artifact):
    client.patch(f"/api/artifacts/{artifact}", json={"title": "Unique searchable lekythos"})
    rows = client.get("/api/artifacts", params={"q": "searchable lekythos"}).json()
    assert [r["id"] for r in rows] == [artifact]
    assert rows[0]["image_count"] == 0
    assert all(r["category"] == "Ceramics" for r in client.get("/api/artifacts", params={"category": "Ceramics"}).json())


def test_delete_artifact_removes_files(client, artifact):
    from backend import config

    assert upload(client, artifact, 1).status_code == 200
    assert (config.UPLOADS / artifact).is_dir()
    assert client.delete(f"/api/artifacts/{artifact}").status_code == 200
    assert client.get(f"/api/artifacts/{artifact}").status_code == 404
    assert not (config.UPLOADS / artifact).exists()


# --------------------------------------------------------------- images
def test_upload_images_and_checksums(client, artifact):
    r = upload(client, artifact, 3)
    assert r.status_code == 200 and r.json()["uploaded"] == 3
    asset = r.json()["assets"][0]
    images = client.get(f"/api/artifacts/{artifact}/images").json()
    assert len(images) == 3 and "path" not in images[0]
    raw = client.get(images[0]["url"])
    assert raw.status_code == 200
    assert hashlib.sha256(raw.content).hexdigest() == images[0]["checksum"] == asset["sha256"]
    assert client.get(images[0]["thumbnail_url"]).headers["content-type"] == "image/jpeg"


def test_upload_rejects_non_images(client, artifact):
    bad = [("files", ("notes.txt", b"definitely not an image", "text/plain"))]
    assert client.post(f"/api/artifacts/{artifact}/images", files=bad).status_code == 400
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "BMP")
    bmp = [("files", ("x.bmp", buf.getvalue(), "image/bmp"))]
    assert client.post(f"/api/artifacts/{artifact}/images", files=bmp).status_code == 400
    # A rejected batch must not leave partial files behind.
    assert client.get(f"/api/artifacts/{artifact}/images").json() == []


def test_delete_image(client, artifact):
    asset_id = upload(client, artifact, 1).json()["assets"][0]["id"]
    assert client.delete(f"/api/artifacts/{artifact}/images/{asset_id}").status_code == 200
    assert client.get(f"/api/artifacts/{artifact}/images").json() == []


# --------------------------------------------------------------- reconstruction
def test_reconstruction_needs_three_images(client, artifact):
    upload(client, artifact, 2)
    r = client.post(f"/api/artifacts/{artifact}/reconstructions")
    assert r.status_code == 400


def test_reconstruction_of_featureless_images_fails_honestly(client, artifact):
    upload(client, artifact, 3)
    r = client.post(f"/api/artifacts/{artifact}/reconstructions", json={"engine": "opencv"})
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    # Solid-colour images have no features: the job must fail, not fake a model.
    assert job["status"] == "failed"
    assert job["model_url"] is None
    assert client.get(f"/api/jobs/{job['id']}/model.ply").status_code == 404
    assert any("FAILED" in ln for ln in client.get(f"/api/jobs/{job['id']}/logs").json()["lines"])


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/jobs/../../etc/passwd").status_code == 404


# --------------------------------------------------------------- classification
def test_classification_never_fabricates(client, artifact):
    status = client.get(f"/api/artifacts/{artifact}/classification").json()
    assert status["status"] == "unavailable"
    assert "No prediction was fabricated" in status["message"]
    r = client.post(f"/api/artifacts/{artifact}/classifications")
    assert r.status_code == 503
    assert client.get(f"/api/artifacts/{artifact}").json()["predictions"] == []


# --------------------------------------------------------------- reports
def test_csv_export(client):
    response = client.get("/api/reports/artifacts.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "title" in response.text


def test_csv_neutralises_formula_injection(client):
    client.post("/api/artifacts", json={"title": "=HYPERLINK(\"http://x\")", "category": "Test"})
    rows = list(csv.DictReader(io.StringIO(client.get("/api/reports/artifacts.csv").text)))
    assert any(r["title"].startswith("'=") for r in rows)


def test_summary(client, artifact):
    s = client.get("/api/reports/summary").json()
    assert s["artifacts"] >= 1
    assert any(c["category"] == "Ceramics" for c in s["categories"])
    assert s["recent_events"]


def test_report_escapes_html(client):
    aid = client.post("/api/artifacts", json={"title": "<script>alert(1)</script>", "category": "Test"}).json()["id"]
    html = client.get(f"/api/artifacts/{aid}/report").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_preservation_package(client, artifact):
    upload(client, artifact, 3)
    r = client.get(f"/api/artifacts/{artifact}/package")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert {"bagit.txt", "manifest-sha256.txt", "data/record.json", "data/report.html"} <= set(names)
    for line in z.read("manifest-sha256.txt").decode().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256(z.read(name)).hexdigest() == digest
    record = json.loads(z.read("data/record.json"))
    assert all(i["status"] == "ok" for i in record["integrity_check"])
    assert len([n for n in names if n.startswith("data/originals/")]) == 3


# --------------------------------------------------------------- dataset
def test_dataset_unavailable_is_explicit(client):
    assert client.get("/api/dataset").status_code == 503
    assert client.get("/api/dataset", params={"split": "bad"}).status_code == 400
    assert client.get("/api/dataset/images/train/..%2Fsecret.jpg").status_code in (400, 404)

"""Reconstruction engine tests: PLY I/O and a real end-to-end SfM run on
synthetic turntable images (no COLMAP required)."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from backend.reconstruction import validate_ply
from backend.sfm import write_ply

ROOT = Path(__file__).resolve().parents[1]
cv2 = pytest.importorskip("cv2")


def test_ply_roundtrip(tmp_path):
    xyz = np.random.default_rng(0).normal(size=(500, 3)).astype(np.float32)
    rgb = np.full((500, 3), 128, np.uint8)
    write_ply(tmp_path / "p.ply", xyz, rgb)
    info = validate_ply(tmp_path / "p.ply")
    assert info["points"] == 500
    assert np.allclose(info["bbox_min"], xyz.min(axis=0), atol=1e-3)


def test_validate_rejects_garbage(tmp_path):
    (tmp_path / "bad.ply").write_bytes(b"not a ply" * 50)
    with pytest.raises(RuntimeError):
        validate_ply(tmp_path / "bad.ply")
    xyz = np.array([[0, 0, np.nan]] * 20, np.float32)
    write_ply(tmp_path / "nan.ply", xyz, np.zeros((20, 3), np.uint8))
    with pytest.raises(RuntimeError):
        validate_ply(tmp_path / "nan.ply")


def _render_views(out: Path, n=14, w=480, h=360):
    spec = importlib.util.spec_from_file_location("mk", ROOT / "scripts" / "make_sample_images.py")
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    from PIL import Image

    scene, focal, target = mk.build_scene(), 1.2 * max(w, h), np.array([0.0, 0.0, 0.75])
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in range(n):
        a = 2 * np.pi * k / n
        eye = target + 4.4 * np.array([np.cos(a) * np.cos(0.5), np.sin(a) * np.cos(0.5), np.sin(0.5)])
        p = out / f"v{k:02d}.jpg"
        Image.fromarray(mk.render(eye, target, w, h, focal, scene)).save(p, quality=93)
        paths.append(p)
    return paths


@pytest.mark.slow
def test_end_to_end_reconstruction_via_api(client, tmp_path):
    paths = _render_views(tmp_path / "views")
    aid = client.post("/api/artifacts", json={"title": "Synthetic turntable", "category": "Test"}).json()["id"]
    files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in paths]
    assert client.post(f"/api/artifacts/{aid}/images", files=files).status_code == 200

    r = client.post(f"/api/artifacts/{aid}/reconstructions", json={"engine": "opencv"})
    assert r.status_code == 200
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "completed", job["message"]
    stats = job["stats"]
    assert stats["images_registered"] >= 12
    assert stats["points"] > 2000
    assert stats["mean_reprojection_error_px"] < 1.5

    ply = client.get(job["model_url"])
    assert ply.status_code == 200 and ply.content.startswith(b"ply")
    cams = client.get(job["cameras_url"]).json()["cameras"]
    centers = np.array([c["center"] for c in cams])
    # Cameras were rendered on a circle: their distances to the centroid
    # should be nearly equal (up to the unknown global scale).
    d = np.linalg.norm(centers - centers.mean(axis=0), axis=1)
    assert d.std() / d.mean() < 0.1

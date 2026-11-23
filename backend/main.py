"""ArtifactScan AI — FastAPI application.

Run from the project root:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import threading
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from . import classifier, config, reconstruction
from .db import audit, connect, init_db, new_id, now
from .preservation import build_package, build_record, render_report

Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression bombs

app = FastAPI(
    title="ArtifactScan AI",
    version=config.VERSION,
    description="Digitise heritage artifacts: records, validated photographs, "
                "photo-to-3D reconstruction, AI-assisted classification and preservation exports.",
)
if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"])

init_db()

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ArtifactInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    creator: str = Field(default="", max_length=300)
    period: str = Field(default="", max_length=200)
    material: str = Field(default="", max_length=300)
    dimensions: str = Field(default="", max_length=200)
    origin: str = Field(default="", max_length=300)
    condition: str = Field(default="", max_length=500)
    provenance: str = Field(default="", max_length=2000)
    rights: str = Field(default="", max_length=1000)
    license_url: str = Field(default="", max_length=500)


class ArtifactPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    creator: str | None = Field(default=None, max_length=300)
    period: str | None = Field(default=None, max_length=200)
    material: str | None = Field(default=None, max_length=300)
    dimensions: str | None = Field(default=None, max_length=200)
    origin: str | None = Field(default=None, max_length=300)
    condition: str | None = Field(default=None, max_length=500)
    provenance: str | None = Field(default=None, max_length=2000)
    rights: str | None = Field(default=None, max_length=1000)
    license_url: str | None = Field(default=None, max_length=500)
    review_status: Literal["draft", "in_review", "reviewed"] | None = None


class ReconstructionRequest(BaseModel):
    engine: Literal["auto", "colmap", "docker", "opencv"] = "auto"


class ReviewInput(BaseModel):
    reviewer_label: str = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _check_id(value: str, what: str = "Artifact") -> str:
    if not UUID_RE.match(value):
        raise HTTPException(404, f"{what} not found")
    return value


def _artifact_or_404(con, artifact_id: str) -> dict:
    _check_id(artifact_id)
    row = con.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Artifact not found")
    return dict(row)


def _asset_public(row) -> dict:
    a = dict(row)
    a.pop("path", None)
    a["url"] = f"/api/artifacts/{a['artifact_id']}/images/{a['id']}"
    a["thumbnail_url"] = a["url"] + "?thumb=1"
    return a


def _job_public(row) -> dict:
    j = dict(row)
    out = j.pop("output_dir", "")
    j["stats"] = json.loads(j.pop("stats_json", "{}") or "{}")
    has_model = bool(out) and (Path(out) / "sparse_point_cloud.ply").is_file()
    j["model_url"] = f"/api/jobs/{j['id']}/model.ply" if has_model and j["status"] == "completed" else None
    j["cameras_url"] = f"/api/jobs/{j['id']}/cameras.json" if j["model_url"] else None
    return j


def _update_job(job_id: str, **fields) -> None:
    fields["updated_at"] = now()
    if "message" in fields:
        fields["message"] = str(fields["message"])[:3000]
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))


def _make_thumbnail(src: Path, artifact_id: str, asset_id: str) -> None:
    target = config.THUMBS / artifact_id
    target.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        img.thumbnail((480, 480))
        img.save(target / f"{asset_id}.jpg", quality=85)


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "service": "ArtifactScan AI API", "version": config.VERSION}


@app.get("/api/readiness", tags=["system"])
def readiness():
    engines = reconstruction.engines()
    clf = classifier.status()
    try:
        selected = reconstruction.choose_engine()
    except RuntimeError:
        selected = None
    return {
        "api": True,
        "database": config.DB_PATH.exists(),
        "colmap": engines["colmap"] or engines["docker"],
        "colmap_runtime": "native" if engines["colmap"] else ("docker" if engines["docker"] else None),
        "reconstruction": selected is not None,
        "reconstruction_engines": engines,
        "reconstruction_engine_selected": selected,
        "classifier": clf["available"],
        "classifier_note": clf["reason"] or f"Model {clf['model_version']} loaded on demand.",
        "dataset": (config.DATASET_ROOT / "train_metadata.csv").is_file(),
        "version": config.VERSION,
    }


@app.get("/api/settings", tags=["system"])
def settings():
    return {
        "version": config.VERSION,
        "reconstruction_engine_preference": config.RECON_ENGINE,
        "colmap_binary": config.COLMAP_BIN,
        "colmap_docker_image": config.COLMAP_DOCKER_IMAGE,
        "reconstruction_timeout_s": config.RECON_TIMEOUT_S,
        "max_upload_mb": config.MAX_UPLOAD_MB,
        "max_files_per_request": config.MAX_FILES_PER_REQUEST,
        "min_reconstruction_images": config.MIN_RECON_IMAGES,
        "cors_origins": config.CORS_ORIGINS,
        "storage_bytes": sum(f.stat().st_size for f in config.STORAGE.rglob("*") if f.is_file()),
    }


# --------------------------------------------------------------------------- #
# Artifacts
# --------------------------------------------------------------------------- #
@app.get("/api/artifacts", tags=["artifacts"])
def list_artifacts(q: str = "", category: str = "",
                   limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0)):
    sql = """SELECT a.*,
               (SELECT COUNT(*) FROM assets s WHERE s.artifact_id=a.id) AS image_count,
               (SELECT id FROM assets s WHERE s.artifact_id=a.id ORDER BY created_at LIMIT 1) AS cover_asset,
               (SELECT status FROM jobs j WHERE j.artifact_id=a.id ORDER BY created_at DESC LIMIT 1) AS latest_job_status
             FROM artifacts a WHERE 1=1"""
    args: list = []
    if q:
        sql += " AND (a.title LIKE ? OR a.category LIKE ? OR a.id LIKE ? OR a.material LIKE ? OR a.period LIKE ?)"
        args += [f"%{q}%"] * 5
    if category:
        sql += " AND a.category = ?"
        args.append(category)
    sql += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    with connect() as con:
        rows = [dict(r) for r in con.execute(sql, args)]
    for r in rows:
        cover = r.pop("cover_asset")
        r["thumbnail_url"] = f"/api/artifacts/{r['id']}/images/{cover}?thumb=1" if cover else None
    return rows


@app.post("/api/artifacts", status_code=200, tags=["artifacts"])
def create_artifact(data: ArtifactInput):
    artifact_id = new_id()
    values = data.model_dump()
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in values.items()}
    ts = now()
    cols = ["id", *values.keys(), "created_at", "updated_at", "review_status"]
    with connect() as con:
        con.execute(
            f"INSERT INTO artifacts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            (artifact_id, *values.values(), ts, ts, "draft"),
        )
        audit(con, "artifact", artifact_id, "created", title=values["title"])
    return {"id": artifact_id, "status": "created"}


@app.get("/api/artifacts/{artifact_id}", tags=["artifacts"])
def get_artifact(artifact_id: str):
    with connect() as con:
        item = _artifact_or_404(con, artifact_id)
        item["assets"] = [_asset_public(a) for a in con.execute(
            "SELECT * FROM assets WHERE artifact_id=? ORDER BY created_at", (artifact_id,))]
        item["jobs"] = [_job_public(j) for j in con.execute(
            "SELECT * FROM jobs WHERE artifact_id=? ORDER BY created_at DESC", (artifact_id,))]
        item["predictions"] = [
            {**dict(p), "scores": json.loads(p["scores_json"])} for p in con.execute(
                "SELECT * FROM predictions WHERE artifact_id=? ORDER BY created_at DESC", (artifact_id,))
        ]
        for p in item["predictions"]:
            p.pop("scores_json", None)
    return item


@app.patch("/api/artifacts/{artifact_id}", tags=["artifacts"])
def update_artifact(artifact_id: str, data: ArtifactPatch):
    changes = {k: (v.strip() if isinstance(v, str) else v)
               for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    with connect() as con:
        _artifact_or_404(con, artifact_id)
        if changes:
            changes["updated_at"] = now()
            con.execute(f"UPDATE artifacts SET {', '.join(f'{k}=?' for k in changes)} WHERE id=?",
                        (*changes.values(), artifact_id))
            audit(con, "artifact", artifact_id, "updated", fields=sorted(changes))
    return get_artifact(artifact_id)


@app.delete("/api/artifacts/{artifact_id}", tags=["artifacts"])
def delete_artifact(artifact_id: str):
    with connect() as con:
        art = _artifact_or_404(con, artifact_id)
        running = con.execute("SELECT COUNT(*) FROM jobs WHERE artifact_id=? AND status IN ('queued','running')",
                              (artifact_id,)).fetchone()[0]
        if running:
            raise HTTPException(409, "A reconstruction job is still running for this artifact")
        jobs = [r["id"] for r in con.execute("SELECT id FROM jobs WHERE artifact_id=?", (artifact_id,))]
        for table in ("predictions", "jobs", "assets"):
            con.execute(f"DELETE FROM {table} WHERE artifact_id=?", (artifact_id,))
        con.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))
        audit(con, "artifact", artifact_id, "deleted", title=art["title"])
    for folder in (config.UPLOADS / artifact_id, config.THUMBS / artifact_id,
                   *(config.RECON / j for j in jobs)):
        shutil.rmtree(folder, ignore_errors=True)
    return {"id": artifact_id, "status": "deleted"}


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
@app.post("/api/artifacts/{artifact_id}/images", tags=["images"])
async def upload_images(artifact_id: str, files: list[UploadFile] = File(...)):
    with connect() as con:
        _artifact_or_404(con, artifact_id)
    if not files or len(files) > config.MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"Upload between 1 and {config.MAX_FILES_PER_REQUEST} images per request")

    # Validate every file before writing anything, so a bad file never
    # leaves a half-saved batch behind.
    validated = []
    for upload in files:
        raw = await upload.read()
        if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Each image must be at most {config.MAX_UPLOAD_MB} MB")
        try:
            with Image.open(io.BytesIO(raw)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(raw)) as image:
                fmt = (image.format or "").upper()
                width, height = image.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(400, f"'{upload.filename}' is not a valid image")
        if fmt not in EXTENSIONS:
            raise HTTPException(400, "Only JPEG, PNG and WEBP images are supported")
        validated.append((upload, raw, fmt, width, height))

    target = config.UPLOADS / artifact_id
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    with connect() as con:
        for upload, raw, fmt, width, height in validated:
            checksum = hashlib.sha256(raw).hexdigest()
            asset_id = new_id()
            filename = asset_id + EXTENSIONS[fmt]
            path = target / filename
            path.write_bytes(raw)
            try:
                _make_thumbnail(path, artifact_id, asset_id)
            except OSError:
                pass
            original = Path(upload.filename or "").name[:255]
            con.execute(
                """INSERT INTO assets (id,artifact_id,filename,path,media_type,checksum,created_at,
                   original_filename,size_bytes,width,height) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (asset_id, artifact_id, filename, str(path), MEDIA_TYPES[EXTENSIONS[fmt]],
                 checksum, now(), original, len(raw), width, height),
            )
            saved.append({"id": asset_id, "filename": filename, "original_filename": original,
                          "sha256": checksum, "width": width, "height": height})
        audit(con, "artifact", artifact_id, "images_uploaded", count=len(saved))
    return {"uploaded": len(saved), "assets": saved}


@app.get("/api/artifacts/{artifact_id}/images", tags=["images"])
def list_images(artifact_id: str):
    with connect() as con:
        _artifact_or_404(con, artifact_id)
        return [_asset_public(a) for a in con.execute(
            "SELECT * FROM assets WHERE artifact_id=? ORDER BY created_at", (artifact_id,))]


@app.get("/api/artifacts/{artifact_id}/images/{asset_id}", tags=["images"])
def get_image(artifact_id: str, asset_id: str, thumb: bool = False):
    _check_id(artifact_id)
    _check_id(asset_id, "Image")
    with connect() as con:
        row = con.execute("SELECT * FROM assets WHERE id=? AND artifact_id=?",
                          (asset_id, artifact_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Image not found")
    if thumb:
        t = config.THUMBS / artifact_id / f"{asset_id}.jpg"
        if t.is_file():
            return FileResponse(t, media_type="image/jpeg")
    path = Path(row["path"])
    if not path.is_file():
        raise HTTPException(404, "Image file is missing from storage")
    return FileResponse(path, media_type=row["media_type"])


@app.delete("/api/artifacts/{artifact_id}/images/{asset_id}", tags=["images"])
def delete_image(artifact_id: str, asset_id: str):
    _check_id(artifact_id)
    _check_id(asset_id, "Image")
    with connect() as con:
        row = con.execute("SELECT * FROM assets WHERE id=? AND artifact_id=?",
                          (asset_id, artifact_id)).fetchone()
        if row is None:
            raise HTTPException(404, "Image not found")
        con.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        audit(con, "artifact", artifact_id, "image_deleted", asset_id=asset_id)
    Path(row["path"]).unlink(missing_ok=True)
    (config.THUMBS / artifact_id / f"{asset_id}.jpg").unlink(missing_ok=True)
    return {"id": asset_id, "status": "deleted"}


# --------------------------------------------------------------------------- #
# Reconstruction jobs
# --------------------------------------------------------------------------- #
STAGE_HINTS = [("Feature extraction", "matching"), ("[features]", "features"), ("[matching]", "matching"),
               ("Matching:", "registration"), ("[mapping]", "mapping"), ("Initialisation", "registration"),
               ("Registered", "registration"), ("Bundle adjustment", "bundle_adjustment"),
               ("[export]", "export"), ("Validated PLY", "validation")]


def run_reconstruction_job(job_id: str, artifact_id: str, engine: str) -> None:
    workspace = config.RECON / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    log_path = workspace / "job.log"
    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{now()}  {msg}\n")
        stage = next((s for hint, s in STAGE_HINTS if hint in msg), None)
        fields = {"message": msg}
        if stage:
            fields["stage"] = stage
        _update_job(job_id, **fields)

    with reconstruction.RECON_LOCK:
        try:
            _update_job(job_id, status="running", stage="preparing", started_at=now(),
                        message=f"Starting {engine} reconstruction.")
            with connect() as con:
                rows = con.execute("SELECT path FROM assets WHERE artifact_id=? ORDER BY created_at",
                                   (artifact_id,)).fetchall()
            paths = [r["path"] for r in rows]
            if len(paths) < config.MIN_RECON_IMAGES:
                raise RuntimeError(f"Only {len(paths)} images found; at least {config.MIN_RECON_IMAGES} are required.")
            stats = reconstruction.reconstruct(engine, paths, workspace, log)
            from .preservation import sha256_file

            checksum = sha256_file(workspace / "sparse_point_cloud.ply")
            _update_job(job_id, status="completed", stage="completed", finished_at=now(),
                        output_dir=str(workspace), stats_json=json.dumps(stats), output_checksum=checksum,
                        message=(f"Sparse point cloud ready: {stats['points']} points from "
                                 f"{stats.get('images_registered', '?')}/{stats.get('images_input', len(paths))} images."))
            with connect() as con:
                audit(con, "job", job_id, "completed", artifact_id=artifact_id, points=stats["points"])
        except Exception as exc:  # noqa: BLE001 - every failure must be reported on the job
            msg = f"{type(exc).__name__}: {exc}"
            try:
                with open(log_path, "a", encoding="utf-8") as fh:
                    fh.write(f"{now()}  FAILED {msg}\n")
            except OSError:
                pass
            _update_job(job_id, status="failed", finished_at=now(), message=msg)
            with connect() as con:
                audit(con, "job", job_id, "failed", artifact_id=artifact_id, error=msg[:300])


@app.post("/api/artifacts/{artifact_id}/reconstructions", tags=["reconstruction"])
def start_reconstruction(artifact_id: str, background_tasks: BackgroundTasks,
                         body: ReconstructionRequest | None = None):
    with connect() as con:
        _artifact_or_404(con, artifact_id)
        count = con.execute("SELECT COUNT(*) FROM assets WHERE artifact_id=?", (artifact_id,)).fetchone()[0]
        if count < config.MIN_RECON_IMAGES:
            raise HTTPException(400, f"Upload at least {config.MIN_RECON_IMAGES} valid photographs before reconstruction")
        active = con.execute("SELECT id FROM jobs WHERE artifact_id=? AND status IN ('queued','running')",
                             (artifact_id,)).fetchone()
        if active:
            raise HTTPException(409, f"Job {active['id']} is already running for this artifact")
    try:
        engine = reconstruction.choose_engine(body.engine if body else None)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc))

    job_id = new_id()
    with connect() as con:
        con.execute(
            """INSERT INTO jobs (id,artifact_id,status,stage,message,created_at,updated_at,engine)
               VALUES (?,?,?,?,?,?,?,?)""",
            (job_id, artifact_id, "queued", "queued", "Waiting for reconstruction worker.", now(), now(), engine),
        )
        audit(con, "job", job_id, "queued", artifact_id=artifact_id, engine=engine, images=count)
    background_tasks.add_task(run_reconstruction_job, job_id, artifact_id, engine)
    return {"job_id": job_id, "status": "queued", "engine": engine}


@app.get("/api/jobs", tags=["reconstruction"])
def list_jobs(artifact_id: str = "", status: str = "", limit: int = Query(100, ge=1, le=500)):
    sql = "SELECT j.*, a.title AS artifact_title FROM jobs j LEFT JOIN artifacts a ON a.id=j.artifact_id WHERE 1=1"
    args: list = []
    if artifact_id:
        sql += " AND j.artifact_id=?"
        args.append(artifact_id)
    if status:
        sql += " AND j.status=?"
        args.append(status)
    sql += " ORDER BY j.created_at DESC LIMIT ?"
    args.append(limit)
    with connect() as con:
        return [_job_public(r) for r in con.execute(sql, args)]


def _job_row(job_id: str):
    _check_id(job_id, "Job")
    with connect() as con:
        row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    return row


@app.get("/api/jobs/{job_id}", tags=["reconstruction"])
def get_job(job_id: str):
    return _job_public(_job_row(job_id))


@app.get("/api/jobs/{job_id}/logs", tags=["reconstruction"])
def job_logs(job_id: str, tail: int = Query(200, ge=1, le=5000)):
    _job_row(job_id)
    path = config.RECON / job_id / "job.log"
    lines = path.read_text(encoding="utf-8").splitlines()[-tail:] if path.is_file() else []
    # Logs are written by us, but strip absolute storage paths defensively.
    root = str(config.STORAGE)
    return {"job_id": job_id, "lines": [ln.replace(root, "<storage>") for ln in lines]}


def _job_output(job_id: str, name: str, media: str):
    row = _job_row(job_id)
    if row["status"] != "completed" or not row["output_dir"]:
        raise HTTPException(404, "This job has no completed output")
    path = Path(row["output_dir"]) / name
    if not path.is_file():
        raise HTTPException(404, "Output file not found")
    return FileResponse(path, media_type=media, filename=f"{job_id[:8]}_{name}")


@app.get("/api/jobs/{job_id}/model.ply", tags=["reconstruction"])
def job_model(job_id: str):
    return _job_output(job_id, "sparse_point_cloud.ply", "application/octet-stream")


@app.get("/api/jobs/{job_id}/cameras.json", tags=["reconstruction"])
def job_cameras(job_id: str):
    return _job_output(job_id, "cameras.json", "application/json")


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
@app.get("/api/classifier", tags=["classification"])
def classifier_status():
    return classifier.status()


@app.get("/api/artifacts/{artifact_id}/classification", tags=["classification"])
def classification_status(artifact_id: str):
    with connect() as con:
        _artifact_or_404(con, artifact_id)
        latest = con.execute("SELECT * FROM predictions WHERE artifact_id=? ORDER BY created_at DESC LIMIT 1",
                             (artifact_id,)).fetchone()
    st = classifier.status()
    out = {
        "status": "available" if st["available"] else "unavailable",
        "message": "Classifier ready." if st["available"] else
                   f"{st['reason']} No prediction was fabricated.",
        "latest_prediction": None,
    }
    if latest:
        out["latest_prediction"] = {**dict(latest), "scores": json.loads(latest["scores_json"])}
        out["latest_prediction"].pop("scores_json")
    return out


@app.post("/api/artifacts/{artifact_id}/classifications", tags=["classification"])
def classify_artifact(artifact_id: str):
    with connect() as con:
        _artifact_or_404(con, artifact_id)
        paths = [Path(r["path"]) for r in con.execute(
            "SELECT path FROM assets WHERE artifact_id=? ORDER BY created_at", (artifact_id,))]
    st = classifier.status()
    if not st["available"]:
        raise HTTPException(503, f"{st['reason']} No prediction was fabricated.")
    if not paths:
        raise HTTPException(400, "Upload at least one image before classification")
    try:
        result = classifier.predict(paths)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Classifier failed: {exc}")
    pid = new_id()
    with connect() as con:
        con.execute(
            """INSERT INTO predictions (id,artifact_id,model_version,predicted_label,scores_json,status,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (pid, artifact_id, st["model_version"], result["predicted_label"],
             json.dumps(result["scores"]), "needs_review", now()),
        )
        audit(con, "prediction", pid, "created", artifact_id=artifact_id, label=result["predicted_label"])
    return {"id": pid, "model_version": st["model_version"], "status": "needs_review", **result}


@app.post("/api/predictions/{prediction_id}/review", tags=["classification"])
def review_prediction(prediction_id: str, data: ReviewInput):
    _check_id(prediction_id, "Prediction")
    with connect() as con:
        row = con.execute("SELECT * FROM predictions WHERE id=?", (prediction_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Prediction not found")
        con.execute("UPDATE predictions SET reviewer_label=?, reviewed_at=?, status='reviewed' WHERE id=?",
                    (data.reviewer_label.strip(), now(), prediction_id))
        audit(con, "prediction", prediction_id, "reviewed", label=data.reviewer_label.strip())
    return {"id": prediction_id, "status": "reviewed", "reviewer_label": data.reviewer_label.strip()}


# --------------------------------------------------------------------------- #
# Reports & preservation
# --------------------------------------------------------------------------- #
@app.get("/api/reports/summary", tags=["reports"])
def summary():
    with connect() as con:
        q = lambda sql, *a: con.execute(sql, a).fetchone()[0]  # noqa: E731
        categories = [dict(r) for r in con.execute(
            "SELECT category, COUNT(*) AS count FROM artifacts GROUP BY category ORDER BY count DESC")]
        jobs = {r["status"]: r["n"] for r in con.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}
        events = [
            {**dict(r), "details": json.loads(r["details_json"] or "{}")}
            for r in con.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT 12")
        ]
        for e in events:
            e.pop("details_json", None)
        timeline = [dict(r) for r in con.execute(
            "SELECT substr(created_at,1,10) AS day, COUNT(*) AS count FROM assets GROUP BY day ORDER BY day")]
        points = 0
        for r in con.execute("SELECT stats_json FROM jobs WHERE status='completed'"):
            points += int(json.loads(r["stats_json"] or "{}").get("points", 0))
        return {
            "artifacts": q("SELECT COUNT(*) FROM artifacts"),
            "images": q("SELECT COUNT(*) FROM assets"),
            "image_bytes": q("SELECT COALESCE(SUM(size_bytes),0) FROM assets"),
            "jobs": jobs,
            "jobs_total": sum(jobs.values()),
            "points_reconstructed": points,
            "predictions": q("SELECT COUNT(*) FROM predictions"),
            "predictions_reviewed": q("SELECT COUNT(*) FROM predictions WHERE status='reviewed'"),
            "reviewed_artifacts": q("SELECT COUNT(*) FROM artifacts WHERE review_status='reviewed'"),
            "categories": categories,
            "uploads_by_day": timeline,
            "recent_events": events,
        }


EXPORT_FIELDS = ["id", "title", "category", "description", "creator", "period", "material", "dimensions",
                 "origin", "condition", "provenance", "rights", "license_url", "review_status",
                 "image_count", "latest_job_status", "created_at", "updated_at"]


@app.get("/api/reports/artifacts.csv", tags=["reports"])
def export_artifacts_csv():
    rows = list_artifacts(q="", category="", limit=500, offset=0)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Neutralise spreadsheet formula injection in user-entered text.
        writer.writerow({k: ("'" + v if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in row.items()})
    with connect() as con:
        audit(con, "report", "artifacts.csv", "exported", rows=len(rows))
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=artifacts.csv"})


@app.get("/api/reports/artifacts.json", tags=["reports"])
def export_artifacts_json():
    rows = list_artifacts(q="", category="", limit=500, offset=0)
    return JSONResponse({"generated_at": now(), "count": len(rows),
                         "artifacts": [{k: r.get(k) for k in EXPORT_FIELDS} for r in rows]},
                        headers={"Content-Disposition": "attachment; filename=artifacts.json"})


def _record(artifact_id: str):
    with connect() as con:
        art = _artifact_or_404(con, artifact_id)
        assets = [dict(r) for r in con.execute("SELECT * FROM assets WHERE artifact_id=? ORDER BY created_at",
                                               (artifact_id,))]
        jobs = [dict(r) for r in con.execute("SELECT * FROM jobs WHERE artifact_id=? ORDER BY created_at DESC",
                                             (artifact_id,))]
        preds = [dict(r) for r in con.execute(
            "SELECT * FROM predictions WHERE artifact_id=? ORDER BY created_at DESC", (artifact_id,))]
    return build_record(art, assets, jobs, preds), assets, jobs


@app.get("/api/artifacts/{artifact_id}/record.json", tags=["reports"])
def artifact_record(artifact_id: str):
    record, _, _ = _record(artifact_id)
    return record


@app.get("/api/artifacts/{artifact_id}/report", response_class=HTMLResponse, tags=["reports"])
def artifact_report(artifact_id: str):
    record, _, _ = _record(artifact_id)
    return render_report(record)


@app.get("/api/artifacts/{artifact_id}/package", tags=["reports"])
def artifact_package(artifact_id: str):
    record, assets, jobs = _record(artifact_id)
    path = build_package(record, assets, jobs)
    with connect() as con:
        audit(con, "artifact", artifact_id, "package_exported", file=path.name)
    return FileResponse(path, media_type="application/zip", filename=path.name)


# --------------------------------------------------------------------------- #
# Reference dataset (iMet Open Access subset, optional)
# --------------------------------------------------------------------------- #
DATASET_SPLITS = {"train", "validation"}


@app.get("/api/dataset", tags=["dataset"])
def list_dataset(split: str = "train", q: str = "",
                 limit: int = Query(60, ge=1, le=100), offset: int = Query(0, ge=0)):
    if split not in DATASET_SPLITS:
        raise HTTPException(400, "split must be train or validation")
    metadata = config.DATASET_ROOT / f"{split}_metadata.csv"
    images_dir = config.DATASET_ROOT / split
    if not metadata.is_file() or not images_dir.is_dir():
        raise HTTPException(503, "Dataset files are not installed. Run ml/download_imet.py.")
    with metadata.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    needle = q.strip().lower()
    items = []
    for row in rows:
        filename = row.get("filename", "")
        if not filename or not (images_dir / filename).is_file():
            continue
        if needle and needle not in f"{row.get('title', '')} {row.get('label_name', '')} {row.get('object_id', '')}".lower():
            continue
        items.append({
            "filename": filename, "title": row.get("title", ""), "label": row.get("label_name", ""),
            "object_id": row.get("object_id", ""), "object_url": row.get("object_url", ""),
            "image_url": f"/api/dataset/images/{split}/{filename}",
        })
    return {"source": "The Metropolitan Museum of Art — iMet Open Access subset (CC0)",
            "split": split, "total": len(items), "offset": offset, "limit": limit,
            "items": items[offset:offset + limit]}


@app.get("/api/dataset/images/{split}/{filename}", tags=["dataset"])
def dataset_image(split: str, filename: str):
    if split not in DATASET_SPLITS:
        raise HTTPException(400, "Invalid dataset split")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.jpg", filename):
        raise HTTPException(400, "Invalid image filename")
    path = config.DATASET_ROOT / split / filename
    if not path.is_file():
        raise HTTPException(404, "Dataset image not found")
    return FileResponse(path, media_type="image/jpeg")


# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index():
    page = config.FRONTEND / "index.html"
    if not page.exists():
        raise HTTPException(500, "Frontend file is missing")
    return page.read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=config.FRONTEND / "static"), name="static")

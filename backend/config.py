"""Runtime configuration, read once from environment variables.

Every setting has a safe local default, so the app runs with no .env file.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

STORAGE = Path(os.getenv("ARTIFACTSCAN_STORAGE", ROOT / "storage")).resolve()
UPLOADS = STORAGE / "uploads"
THUMBS = STORAGE / "thumbnails"
RECON = STORAGE / "reconstructions"
EXPORTS = STORAGE / "exports"
DB_PATH = STORAGE / "artifacts.db"

DATASET_ROOT = Path(os.getenv("ARTIFACTSCAN_DATASET", ROOT / "data" / "imet")).resolve()
MODEL_DIR = Path(os.getenv("ARTIFACTSCAN_MODEL_DIR", ROOT / "models" / "classifier")).resolve()

# auto | colmap | docker | opencv
RECON_ENGINE = os.getenv("ARTIFACTSCAN_RECON_ENGINE", "auto").strip().lower()
COLMAP_BIN = os.getenv("ARTIFACTSCAN_COLMAP_BIN", "colmap")
COLMAP_DOCKER_IMAGE = os.getenv("ARTIFACTSCAN_COLMAP_IMAGE", "colmap/colmap:latest")
RECON_TIMEOUT_S = int(os.getenv("ARTIFACTSCAN_RECON_TIMEOUT", "3600"))

MAX_UPLOAD_MB = int(os.getenv("ARTIFACTSCAN_MAX_UPLOAD_MB", "15"))
MAX_FILES_PER_REQUEST = int(os.getenv("ARTIFACTSCAN_MAX_FILES", "80"))
MIN_RECON_IMAGES = 3

CORS_ORIGINS = [o.strip() for o in os.getenv("ARTIFACTSCAN_CORS_ORIGINS", "").split(",") if o.strip()]

VERSION = "1.0.0"

for folder in (UPLOADS, THUMBS, RECON, EXPORTS):
    folder.mkdir(parents=True, exist_ok=True)

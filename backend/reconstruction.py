"""Photogrammetry runtimes: native COLMAP, COLMAP in Docker, or the built-in
OpenCV engine. All three produce the same outputs in the job folder:

    sparse_point_cloud.ply     coloured sparse point cloud
    cameras.json               registered camera centres and rotations
    reconstruction_stats.json  engine, counts and timing
    job.log                    sanitised log of every stage
"""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np

from . import config

Log = Callable[[str], None]

# Reconstruction is CPU/RAM heavy: run one job at a time per server process.
RECON_LOCK = threading.Semaphore(1)


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def _colmap_native() -> str | None:
    return shutil.which(config.COLMAP_BIN)


def _docker_colmap_ready() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        check = subprocess.run(
            [docker, "image", "inspect", config.COLMAP_DOCKER_IMAGE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
        )
        return check.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _opencv_ready() -> bool:
    try:
        import cv2  # noqa: F401

        cv2.SIFT_create()
        return True
    except Exception:
        return False


def engines() -> dict[str, bool]:
    return {
        "colmap": _colmap_native() is not None,
        "docker": _docker_colmap_ready(),
        "opencv": _opencv_ready(),
    }


def choose_engine(requested: str | None = None) -> str:
    available = engines()
    wanted = (requested or config.RECON_ENGINE or "auto").lower()
    if wanted != "auto":
        if wanted not in available:
            raise ValueError(f"Unknown engine '{wanted}'. Use auto, colmap, docker or opencv.")
        if not available[wanted]:
            raise RuntimeError(f"Reconstruction engine '{wanted}' is not available on this server.")
        return wanted
    for name in ("colmap", "docker", "opencv"):
        if available[name]:
            return name
    raise RuntimeError("No reconstruction engine is available. Install COLMAP or opencv-python.")


# --------------------------------------------------------------------------- #
# COLMAP (native or Docker)
# --------------------------------------------------------------------------- #
class _Colmap:
    def __init__(self, workspace: Path, docker: bool, log: Log):
        self.ws = workspace
        self.docker = docker
        self.log = log
        self.root = "/work" if docker else str(workspace)

    def path(self, *parts: str) -> str:
        return "/".join([self.root, *parts]) if self.docker else str(Path(self.root, *parts))

    def cmd(self, *args: str) -> list[str]:
        if self.docker:
            return ["docker", "run", "--rm", "-v", f"{self.ws.resolve()}:/work",
                    config.COLMAP_DOCKER_IMAGE, "colmap", *args]
        return [_colmap_native() or config.COLMAP_BIN, *args]

    @lru_cache(maxsize=1)
    def gpu_option_prefix(self) -> str:
        # COLMAP 3.12 renamed SiftExtraction.use_gpu -> FeatureExtraction.use_gpu.
        try:
            out = subprocess.run(self.cmd("feature_extractor", "-h"), capture_output=True,
                                 text=True, timeout=120)
            text = out.stdout + out.stderr
        except (OSError, subprocess.TimeoutExpired):
            text = ""
        return "SiftExtraction" if "SiftExtraction.use_gpu" in text else "FeatureExtraction"

    def run(self, stage: str, *args: str) -> None:
        self.log(f"[{stage}] colmap {args[0]}")
        started = time.time()
        result = subprocess.run(self.cmd(*args), capture_output=True, text=True,
                                timeout=config.RECON_TIMEOUT_S)
        tail = (result.stdout[-1500:] + "\n" + result.stderr[-1500:]).strip()
        if result.returncode != 0:
            raise RuntimeError(f"COLMAP {args[0]} failed (exit {result.returncode}).\n{tail}")
        self.log(f"[{stage}] finished in {time.time() - started:.1f}s")


def _qvec_to_R(qw, qx, qy, qz) -> np.ndarray:
    return np.array([
        [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qw * qz, 2 * qz * qx + 2 * qw * qy],
        [2 * qx * qy + 2 * qw * qz, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qw * qx],
        [2 * qz * qx - 2 * qw * qy, 2 * qy * qz + 2 * qw * qx, 1 - 2 * qx * qx - 2 * qy * qy],
    ])


def _parse_colmap_images_txt(path: Path) -> list[dict]:
    cams = []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    for header in lines[0::2]:
        parts = header.split()
        if len(parts) < 10:
            continue
        qw, qx, qy, qz, tx, ty, tz = map(float, parts[1:8])
        R = _qvec_to_R(qw, qx, qy, qz)
        center = -R.T @ np.array([tx, ty, tz])
        cams.append({"image": parts[9], "center": center.round(6).tolist(),
                     "rotation": R.round(6).tolist()})
    return cams


def run_colmap(image_dir: Path, workspace: Path, docker: bool, log: Log) -> dict:
    started = time.time()
    c = _Colmap(workspace, docker, log)
    db = c.path("database.db")
    images = c.path("images")
    gpu = c.gpu_option_prefix()
    (workspace / "sparse").mkdir(exist_ok=True)

    c.run("features", "feature_extractor", "--database_path", db, "--image_path", images,
          "--ImageReader.single_camera", "1", f"--{gpu}.use_gpu", "0")
    match_gpu = "SiftMatching" if gpu == "SiftExtraction" else "FeatureMatching"
    c.run("matching", "exhaustive_matcher", "--database_path", db, f"--{match_gpu}.use_gpu", "0")
    c.run("mapping", "mapper", "--database_path", db, "--image_path", images,
          "--output_path", c.path("sparse"))

    models = [p for p in (workspace / "sparse").iterdir()
              if p.is_dir() and ((p / "points3D.bin").exists() or (p / "points3D.txt").exists())]
    if not models:
        raise RuntimeError("COLMAP did not produce a sparse model. Check image overlap, focus, "
                           "lighting and camera movement.")
    model = max(models, key=lambda p: max((p / f).stat().st_size for f in ("points3D.bin", "points3D.txt")
                                          if (p / f).exists()))
    rel = model.relative_to(workspace).as_posix()
    c.run("export", "model_converter", "--input_path", c.path(*rel.split("/")),
          "--output_path", c.path("sparse_point_cloud.ply"), "--output_type", "PLY")
    txt = workspace / "sparse_txt"
    txt.mkdir(exist_ok=True)
    c.run("export", "model_converter", "--input_path", c.path(*rel.split("/")),
          "--output_path", c.path("sparse_txt"), "--output_type", "TXT")

    cameras = _parse_colmap_images_txt(txt / "images.txt") if (txt / "images.txt").exists() else []
    (workspace / "cameras.json").write_text(json.dumps({"cameras": cameras}, indent=1))
    n_images = len(list((workspace / "images").iterdir()))
    stats = {
        "engine": "colmap-docker" if docker else "colmap",
        "images_input": n_images,
        "images_registered": len(cameras),
        "points": ply_vertex_count(workspace / "sparse_point_cloud.ply"),
        "seconds": round(time.time() - started, 2),
    }
    (workspace / "reconstruction_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


# --------------------------------------------------------------------------- #
# Output validation
# --------------------------------------------------------------------------- #
def ply_vertex_count(path: Path) -> int:
    with open(path, "rb") as fh:
        head = fh.read(4096)
    for line in head.split(b"\n"):
        if line.startswith(b"element vertex"):
            return int(line.split()[-1])
    return 0


def validate_ply(path: Path) -> dict:
    """Parse the PLY header and check every coordinate is finite."""
    if not path.is_file() or path.stat().st_size < 100:
        raise RuntimeError("Reconstruction finished without a valid PLY output.")
    data = path.read_bytes()
    end = data.find(b"end_header\n")
    if not data.startswith(b"ply") or end < 0:
        raise RuntimeError("PLY output is not parseable.")
    header = data[:end].decode("ascii", "replace").splitlines()
    n = 0
    props: list[tuple[str, str]] = []
    in_vertex = False
    fmt = ""
    for line in header:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "format":
            fmt = parts[1]
        elif parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                n = int(parts[2])
        elif parts[0] == "property" and in_vertex:
            props.append((parts[1], parts[2]))
    if n < 10:
        raise RuntimeError(f"PLY output contains only {n} points.")
    sizes = {"float": "f", "float32": "f", "double": "d", "uchar": "B", "uint8": "B",
             "char": "b", "int8": "b", "short": "h", "ushort": "H", "int": "i", "uint": "I",
             "int32": "i", "uint32": "I"}
    if fmt == "binary_little_endian":
        rec = "<" + "".join(sizes[t] for t, _ in props)
        size = struct.calcsize(rec)
        body = data[end + len(b"end_header\n"):]
        dtype = np.dtype([(nm, "<" + np.dtype(sizes[t]).str[1:]) for t, nm in props])
        arr = np.frombuffer(body[: n * size], dtype=dtype, count=n)
        xyz = np.stack([arr["x"], arr["y"], arr["z"]], axis=1).astype(np.float64)
    else:  # ascii
        body = data[end + len(b"end_header\n"):].decode("ascii").split("\n")[:n]
        xyz = np.array([[float(v) for v in row.split()[:3]] for row in body])
    if not np.isfinite(xyz).all():
        raise RuntimeError("PLY output contains non-finite coordinates.")
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    return {"points": int(n), "bbox_min": lo.round(4).tolist(), "bbox_max": hi.round(4).tolist()}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def reconstruct(engine: str, image_paths: list[str], workspace: Path, log: Log) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    image_dir = workspace / "images"
    if image_dir.exists():
        shutil.rmtree(image_dir)
    image_dir.mkdir()
    # Copy originals into the job folder with generated names: user filenames
    # never reach a command line, and source images are never modified.
    copies = []
    for index, item in enumerate(image_paths):
        src = Path(item)
        if not src.is_file():
            raise FileNotFoundError(f"Input image #{index + 1} is missing from storage.")
        dst = image_dir / f"image_{index:04d}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        copies.append(dst)
    log(f"Prepared {len(copies)} images with engine '{engine}'.")

    if engine == "opencv":
        from .sfm import reconstruct as sfm_reconstruct

        stats = sfm_reconstruct(copies, workspace, log=log)
    elif engine in ("colmap", "docker"):
        stats = run_colmap(image_dir, workspace, docker=(engine == "docker"), log=log)
    else:
        raise ValueError(f"Unknown engine {engine}")

    validation = validate_ply(workspace / "sparse_point_cloud.ply")
    stats["validation"] = validation
    (workspace / "reconstruction_stats.json").write_text(json.dumps(stats, indent=2))
    log(f"Validated PLY: {validation['points']} finite points.")
    return stats

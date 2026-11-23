"""Built-in incremental Structure-from-Motion engine (OpenCV + SciPy).

This is ArtifactScan's fallback photogrammetry runtime for machines without
COLMAP. It follows the same classic pipeline COLMAP uses for sparse
reconstruction, at a smaller scale:

1. SIFT feature extraction
2. Pairwise matching with Lowe's ratio test
3. Geometric verification (essential matrix + RANSAC)
4. Two-view initialisation with the best-conditioned image pair
5. Incremental registration (PnP + RANSAC) and triangulation
6. Bundle adjustment (sparse Levenberg-Marquardt / trust-region)
7. Export of a coloured sparse point cloud (binary PLY, same layout as
   COLMAP's ``model_converter``) plus camera poses as JSON

Intrinsics are not calibrated: a single pinhole camera with focal length
``1.2 * max(width, height)`` is assumed (the same prior COLMAP uses when no
EXIF focal length is available) and kept fixed. For heritage-grade results use
COLMAP; this engine exists so the full workflow is usable and testable
everywhere.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

try:  # SciPy is optional: without it bundle adjustment is skipped.
    from scipy.optimize import least_squares
    from scipy.sparse import lil_matrix
    from scipy.spatial.transform import Rotation

    HAVE_SCIPY = True
except ImportError:  # pragma: no cover - exercised only on minimal installs
    HAVE_SCIPY = False


class ReconstructionError(RuntimeError):
    """Raised when the image set cannot produce a valid sparse model."""


@dataclass
class EngineConfig:
    max_image_size: int = 1600
    max_features: int = 6000
    ratio: float = 0.75
    min_pair_inliers: int = 40
    min_pnp_correspondences: int = 15
    max_reproj_error: float = 4.0
    min_tri_angle_deg: float = 1.5
    exhaustive_limit: int = 40  # above this, match within a sliding window
    window: int = 12
    ba_every: int = 4


@dataclass
class _View:
    path: Path
    color: np.ndarray
    kps: np.ndarray
    desc: np.ndarray
    K: np.ndarray
    rvec: np.ndarray | None = None
    tvec: np.ndarray | None = None
    kp2pt: np.ndarray = field(default=None)  # type: ignore[assignment]

    @property
    def registered(self) -> bool:
        return self.rvec is not None


def _log_default(msg: str) -> None:
    print(msg, flush=True)


class SparseReconstructor:
    def __init__(self, config: EngineConfig | None = None,
                 log: Callable[[str], None] = _log_default):
        self.cfg = config or EngineConfig()
        self.log = log
        self.views: list[_View] = []
        self.pairs: dict[tuple[int, int], np.ndarray] = {}
        self.points: list[np.ndarray] = []
        self.obs: list[list[tuple[int, int]]] = []
        self.alive: list[bool] = []

    # ------------------------------------------------------------------ io --
    def _load(self, paths: list[Path]) -> None:
        sift = cv2.SIFT_create(nfeatures=self.cfg.max_features)
        for p in paths:
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if img is None:
                raise ReconstructionError(f"Unreadable image: {p.name}")
            h, w = img.shape[:2]
            scale = min(1.0, self.cfg.max_image_size / max(h, w))
            if scale < 1.0:
                img = cv2.resize(img, (round(w * scale), round(h * scale)),
                                 interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            kps, desc = sift.detectAndCompute(gray, None)
            if desc is None or len(kps) < 50:
                self.log(f"  {p.name}: only {0 if desc is None else len(kps)} features, skipped")
                continue
            f = 1.2 * max(w, h)
            K = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)
            pts = np.array([k.pt for k in kps], dtype=np.float64)
            v = _View(p, cv2.cvtColor(img, cv2.COLOR_BGR2RGB), pts, desc, K)
            v.kp2pt = np.full(len(pts), -1, dtype=np.int64)
            self.views.append(v)
        self.log(f"Feature extraction: {len(self.views)} images, "
                 f"{sum(len(v.kps) for v in self.views)} SIFT keypoints")
        if len(self.views) < 3:
            raise ReconstructionError("Fewer than 3 images had enough texture for features.")

    # ------------------------------------------------------------ matching --
    def _match(self) -> None:
        n = len(self.views)
        if n <= self.cfg.exhaustive_limit:
            candidates = list(combinations(range(n), 2))
        else:
            candidates = sorted({(i, (i + d) % n) if i < (i + d) % n else ((i + d) % n, i)
                                 for i in range(n) for d in range(1, self.cfg.window + 1)})
        matcher = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 5}, {"checks": 64})
        for i, j in candidates:
            a, b = self.views[i], self.views[j]
            knn = matcher.knnMatch(a.desc, b.desc, k=2)
            good = [m[0] for m in knn if len(m) == 2 and m[0].distance < self.cfg.ratio * m[1].distance]
            if len(good) < self.cfg.min_pair_inliers:
                continue
            ia = np.array([m.queryIdx for m in good])
            ib = np.array([m.trainIdx for m in good])
            # Enforce one-to-one matches.
            _, keep = np.unique(ib, return_index=True)
            ia, ib = ia[keep], ib[keep]
            pa = cv2.undistortPoints(a.kps[ia][:, None], a.K, None)[:, 0]
            pb = cv2.undistortPoints(b.kps[ib][:, None], b.K, None)[:, 0]
            if len(pa) < 8:
                continue
            thresh = 2.0 / a.K[0, 0]
            E, mask = cv2.findEssentialMat(pa, pb, np.eye(3), cv2.RANSAC, 0.999, thresh)
            if E is None or mask is None:
                continue
            mask = mask.ravel().astype(bool)
            if mask.sum() >= self.cfg.min_pair_inliers:
                self.pairs[(i, j)] = np.stack([ia[mask], ib[mask]], axis=1)
        self.log(f"Matching: {len(candidates)} pairs tested, {len(self.pairs)} geometrically verified")
        if not self.pairs:
            raise ReconstructionError(
                "No image pairs could be matched. Photos need overlap and visible texture.")

    def _pair(self, i: int, j: int) -> np.ndarray | None:
        if (i, j) in self.pairs:
            return self.pairs[(i, j)]
        if (j, i) in self.pairs:
            return self.pairs[(j, i)][:, ::-1]
        return None

    # ---------------------------------------------------------- geometry ----
    @staticmethod
    def _P(v: _View) -> np.ndarray:
        R, _ = cv2.Rodrigues(v.rvec)
        return v.K @ np.hstack([R, v.tvec.reshape(3, 1)])

    @staticmethod
    def _center(v: _View) -> np.ndarray:
        R, _ = cv2.Rodrigues(v.rvec)
        return -R.T @ v.tvec.reshape(3)

    def _project(self, v: _View, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        R, _ = cv2.Rodrigues(v.rvec)
        Xc = X @ R.T + v.tvec.reshape(1, 3)
        z = Xc[:, 2]
        uv = (Xc[:, :2] / np.where(np.abs(z) < 1e-12, 1e-12, z)[:, None]) * v.K[0, 0] + v.K[:2, 2]
        return uv, z

    def _add_point(self, X: np.ndarray, observations: list[tuple[int, int]]) -> None:
        pid = len(self.points)
        self.points.append(X)
        self.obs.append(list(observations))
        self.alive.append(True)
        for vi, ki in observations:
            self.views[vi].kp2pt[ki] = pid

    def _triangulate_pair(self, i: int, j: int) -> int:
        m = self._pair(i, j)
        if m is None:
            return 0
        a, b = self.views[i], self.views[j]
        free = (a.kp2pt[m[:, 0]] < 0) & (b.kp2pt[m[:, 1]] < 0)
        m = m[free]
        if len(m) == 0:
            return 0
        Xh = cv2.triangulatePoints(self._P(a), self._P(b), a.kps[m[:, 0]].T, b.kps[m[:, 1]].T)
        X = (Xh[:3] / Xh[3]).T
        ok = np.isfinite(X).all(axis=1)
        uva, za = self._project(a, X)
        uvb, zb = self._project(b, X)
        ea = np.linalg.norm(uva - a.kps[m[:, 0]], axis=1)
        eb = np.linalg.norm(uvb - b.kps[m[:, 1]], axis=1)
        ca, cb = self._center(a), self._center(b)
        ra, rb = X - ca, X - cb
        cos = np.einsum("ij,ij->i", ra, rb) / (np.linalg.norm(ra, axis=1) * np.linalg.norm(rb, axis=1) + 1e-12)
        angle = np.degrees(np.arccos(np.clip(cos, -1, 1)))
        ok &= (za > 0) & (zb > 0) & (ea < self.cfg.max_reproj_error) & (eb < self.cfg.max_reproj_error)
        ok &= angle > self.cfg.min_tri_angle_deg
        added = 0
        for k in np.nonzero(ok)[0]:
            self._add_point(X[k], [(i, int(m[k, 0])), (j, int(m[k, 1]))])
            added += 1
        return added

    def _extend_tracks(self, new: int) -> int:
        """Attach observations in ``new`` to existing 3D points via matches."""
        v = self.views[new]
        added = 0
        for r, other in enumerate(self.views):
            if r == new or not other.registered:
                continue
            m = self._pair(new, r)
            if m is None:
                continue
            pids = other.kp2pt[m[:, 1]]
            sel = (pids >= 0) & (v.kp2pt[m[:, 0]] < 0)
            if not sel.any():
                continue
            kps_new, pids = m[sel, 0], pids[sel]
            X = np.array([self.points[p] for p in pids])
            uv, z = self._project(v, X)
            err = np.linalg.norm(uv - v.kps[kps_new], axis=1)
            for k, p, e, zz in zip(kps_new, pids, err, z):
                if zz > 0 and e < self.cfg.max_reproj_error and self.alive[p] and v.kp2pt[k] < 0:
                    v.kp2pt[k] = p
                    self.obs[p].append((new, int(k)))
                    added += 1
        return added

    # ---------------------------------------------------------- pipeline ----
    def _initialize(self) -> tuple[int, int]:
        ranked = sorted(self.pairs.items(), key=lambda kv: -len(kv[1]))
        for (i, j), m in ranked[:30]:
            a, b = self.views[i], self.views[j]
            pa = cv2.undistortPoints(a.kps[m[:, 0]][:, None], a.K, None)[:, 0]
            pb = cv2.undistortPoints(b.kps[m[:, 1]][:, None], b.K, None)[:, 0]
            E, mask = cv2.findEssentialMat(pa, pb, np.eye(3), cv2.RANSAC, 0.999, 1.5 / a.K[0, 0])
            if E is None or E.shape != (3, 3):
                continue
            n_in, R, t, mask2 = cv2.recoverPose(E, pa, pb, np.eye(3), mask=mask)
            if n_in < self.cfg.min_pair_inliers:
                continue
            a.rvec, a.tvec = np.zeros(3), np.zeros(3)
            b.rvec, b.tvec = cv2.Rodrigues(R)[0].ravel(), t.ravel()
            added = self._triangulate_pair(i, j)
            if added >= 50:
                pts = np.array(self.points)
                angle_ok = np.median(np.linalg.norm(pts, axis=1)) < 200  # not near-degenerate
                if angle_ok:
                    self.log(f"Initialisation: pair ({a.path.name}, {b.path.name}) with {added} points")
                    return i, j
            # roll back and try the next candidate
            for v in self.views:
                v.rvec = v.tvec = None
                v.kp2pt[:] = -1
            self.points, self.obs, self.alive = [], [], []
        raise ReconstructionError("No image pair had enough baseline to initialise the model.")

    def _next_view(self) -> tuple[int, np.ndarray, np.ndarray] | None:
        best = None
        for c, v in enumerate(self.views):
            if v.registered:
                continue
            kp_to_pid: dict[int, int] = {}
            for r, other in enumerate(self.views):
                if not other.registered:
                    continue
                m = self._pair(c, r)
                if m is None:
                    continue
                pids = other.kp2pt[m[:, 1]]
                for k, p in zip(m[:, 0], pids):
                    if p >= 0 and self.alive[p]:
                        kp_to_pid.setdefault(int(k), int(p))
            if best is None or len(kp_to_pid) > len(best[1]):
                best = (c, kp_to_pid)
        if best is None or len(best[1]) < self.cfg.min_pnp_correspondences:
            return None
        c, mapping = best
        ks = np.array(list(mapping.keys()))
        ps = np.array(list(mapping.values()))
        return c, ks, ps

    def _register(self, c: int, ks: np.ndarray, ps: np.ndarray) -> bool:
        v = self.views[c]
        obj = np.array([self.points[p] for p in ps], dtype=np.float64)
        img = v.kps[ks].astype(np.float64)
        ok, rvec, tvec, inl = cv2.solvePnPRansac(
            obj, img, v.K, None, iterationsCount=2000,
            reprojectionError=self.cfg.max_reproj_error, confidence=0.999,
            flags=cv2.SOLVEPNP_EPNP)
        if not ok or inl is None or len(inl) < self.cfg.min_pnp_correspondences:
            return False
        inl = inl.ravel()
        rvec, tvec = cv2.solvePnPRefineLM(obj[inl], img[inl], v.K, None, rvec, tvec)
        v.rvec, v.tvec = rvec.ravel(), tvec.ravel()
        for k, p in zip(ks[inl], ps[inl]):
            if v.kp2pt[k] < 0:
                v.kp2pt[k] = p
                self.obs[p].append((c, int(k)))
        self.log(f"Registered {v.path.name}: {len(inl)}/{len(ks)} PnP inliers")
        return True

    def _bundle_adjust(self, max_nfev: int = 60) -> None:
        if not HAVE_SCIPY:
            return
        cams = [i for i, v in enumerate(self.views) if v.registered]
        cam_pos = {c: n for n, c in enumerate(cams)}
        pids = [p for p, a in enumerate(self.alive) if a and len(self.obs[p]) >= 2]
        if len(pids) < 20:
            return
        pt_pos = {p: n for n, p in enumerate(pids)}
        ci, pi, uv = [], [], []
        for p in pids:
            for vi, ki in self.obs[p]:
                if vi in cam_pos:
                    ci.append(cam_pos[vi])
                    pi.append(pt_pos[p])
                    uv.append(self.views[vi].kps[ki])
        ci, pi, uv = np.array(ci), np.array(pi), np.array(uv)
        Ks = np.array([self.views[c].K for c in cams])
        f = Ks[ci, 0, 0]
        cxy = Ks[ci, :2, 2]
        x0 = np.concatenate([
            np.concatenate([self.views[c].rvec, self.views[c].tvec]) for c in cams
        ] + [np.array([self.points[p] for p in pids]).ravel()])
        nc = len(cams)

        def residuals(x):
            cam = x[: nc * 6].reshape(nc, 6)
            X = x[nc * 6:].reshape(-1, 3)
            Xc = Rotation.from_rotvec(cam[ci, :3]).apply(X[pi]) + cam[ci, 3:]
            z = np.where(np.abs(Xc[:, 2]) < 1e-9, 1e-9, Xc[:, 2])
            proj = Xc[:, :2] / z[:, None] * f[:, None] + cxy
            return (proj - uv).ravel()

        m = len(ci)
        A = lil_matrix((2 * m, nc * 6 + 3 * len(pids)), dtype=int)
        rows = np.arange(m)
        for s in range(6):
            A[2 * rows, ci * 6 + s] = 1
            A[2 * rows + 1, ci * 6 + s] = 1
        for s in range(3):
            A[2 * rows, nc * 6 + pi * 3 + s] = 1
            A[2 * rows + 1, nc * 6 + pi * 3 + s] = 1
        # Fix the first camera (gauge freedom) by zeroing its Jacobian columns.
        A[:, :6] = 0

        before = np.sqrt(np.mean(residuals(x0) ** 2))
        res = least_squares(residuals, x0, jac_sparsity=A, method="trf", loss="huber",
                            f_scale=2.0, x_scale="jac", max_nfev=max_nfev, verbose=0)
        x = res.x
        cam = x[: nc * 6].reshape(nc, 6)
        for n, c in enumerate(cams):
            self.views[c].rvec, self.views[c].tvec = cam[n, :3].copy(), cam[n, 3:].copy()
        X = x[nc * 6:].reshape(-1, 3)
        for n, p in enumerate(pids):
            self.points[p] = X[n]
        after = np.sqrt(np.mean(residuals(x) ** 2))
        self.log(f"Bundle adjustment: {nc} cameras, {len(pids)} points, "
                 f"RMS reprojection {before:.2f}px -> {after:.2f}px")
        self._filter_points()

    def _filter_points(self) -> None:
        removed = 0
        for p, alive in enumerate(self.alive):
            if not alive:
                continue
            X = self.points[p][None]
            good = []
            for vi, ki in self.obs[p]:
                v = self.views[vi]
                uv, z = self._project(v, X)
                if z[0] > 0 and np.linalg.norm(uv[0] - v.kps[ki]) < self.cfg.max_reproj_error:
                    good.append((vi, ki))
                else:
                    v.kp2pt[ki] = -1
            self.obs[p] = good
            if len(good) < 2:
                self.alive[p] = False
                for vi, ki in good:
                    self.views[vi].kp2pt[ki] = -1
                removed += 1
        if removed:
            self.log(f"Filtered {removed} points with high reprojection error")

    # --------------------------------------------------------------- run ----
    def run(self, image_paths: list[str | Path], out_dir: str | Path) -> dict:
        started = time.time()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._load([Path(p) for p in image_paths])
        self._match()
        i, j = self._initialize()
        self._bundle_adjust(max_nfev=30)
        since_ba = 0
        while True:
            nxt = self._next_view()
            if nxt is None:
                break
            c, ks, ps = nxt
            if not self._register(c, ks, ps):
                # Mark as unusable for this run by giving it no pairs.
                self.pairs = {k: v for k, v in self.pairs.items() if c not in k}
                self.log(f"Could not register {self.views[c].path.name}; skipping")
                continue
            self._extend_tracks(c)
            for r, other in enumerate(self.views):
                if r != c and other.registered:
                    self._triangulate_pair(c, r)
            since_ba += 1
            if since_ba >= self.cfg.ba_every:
                self._bundle_adjust(max_nfev=30)
                since_ba = 0
        self._bundle_adjust(max_nfev=80)

        registered = [v for v in self.views if v.registered]
        pids = [p for p, a in enumerate(self.alive) if a and len(self.obs[p]) >= 2]
        if len(registered) < 3 or len(pids) < 100:
            raise ReconstructionError(
                f"Reconstruction too sparse: {len(registered)} cameras, {len(pids)} points. "
                "Check image overlap, focus, lighting and camera movement.")

        xyz = np.array([self.points[p] for p in pids], dtype=np.float32)
        rgb = np.zeros((len(pids), 3), dtype=np.float64)
        errs = []
        for n, p in enumerate(pids):
            cols = []
            for vi, ki in self.obs[p]:
                v = self.views[vi]
                x, y = np.clip(np.round(v.kps[ki]).astype(int), 0, [v.color.shape[1] - 1, v.color.shape[0] - 1])
                cols.append(v.color[y, x])
                uv, _ = self._project(v, xyz[n:n + 1].astype(np.float64))
                errs.append(np.linalg.norm(uv[0] - v.kps[ki]))
            rgb[n] = np.mean(cols, axis=0)
        ply = out_dir / "sparse_point_cloud.ply"
        write_ply(ply, xyz, rgb.astype(np.uint8))

        cameras = []
        for v in registered:
            R, _ = cv2.Rodrigues(v.rvec)
            cameras.append({
                "image": v.path.name,
                "center": self._center(v).round(6).tolist(),
                "rotation": R.round(6).tolist(),
                "focal_px": float(v.K[0, 0]),
                "width": int(v.color.shape[1]),
                "height": int(v.color.shape[0]),
            })
        stats = {
            "engine": "opencv-sfm",
            "images_input": len(image_paths),
            "images_registered": len(registered),
            "points": int(len(pids)),
            "mean_track_length": float(np.mean([len(self.obs[p]) for p in pids])),
            "mean_reprojection_error_px": float(np.mean(errs)),
            "seconds": round(time.time() - started, 2),
        }
        (out_dir / "cameras.json").write_text(json.dumps({"cameras": cameras}, indent=1))
        (out_dir / "reconstruction_stats.json").write_text(json.dumps(stats, indent=2))
        self.log(f"Done: {stats}")
        return stats


def write_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    """Binary little-endian PLY with x,y,z float + red,green,blue uchar."""
    n = len(xyz)
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    rec = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                             ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    rec["r"], rec["g"], rec["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(rec.tobytes())


def reconstruct(image_paths: list[str | Path], out_dir: str | Path,
                log: Callable[[str], None] = _log_default,
                config: EngineConfig | None = None) -> dict:
    return SparseReconstructor(config, log).run(image_paths, out_dir)


if __name__ == "__main__":  # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description="Run the built-in sparse reconstruction engine")
    ap.add_argument("images", help="folder of images")
    ap.add_argument("out", help="output folder")
    a = ap.parse_args()
    files = sorted(p for p in Path(a.images).iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    reconstruct(files, a.out)

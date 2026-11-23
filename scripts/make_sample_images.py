"""Render a synthetic, photogrammetry-friendly turntable image set.

The scene is a textured "artifact" (a vase-like sphere on a carved pedestal,
with a few small blocks) standing on a textured plinth. Textures are solid 3D
noise, so every surface point keeps the same colour from every viewpoint —
exactly what feature matching needs.

These images are for demos and automated tests of the reconstruction pipeline.
They are synthetic: never present them as photographs of a real object.

Usage:
    python scripts/make_sample_images.py --out samples/turntable --views 24
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------- #
# Procedural solid texture
# --------------------------------------------------------------------------- #
def _hash3(ix, iy, iz, seed):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFF).astype(np.float64) / 65535.0


def value_noise(p, freq, seed=0):
    q = p * freq
    i = np.floor(q).astype(np.int64)
    f = q - i
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (
                    (f[:, 0] if dx else 1 - f[:, 0])
                    * (f[:, 1] if dy else 1 - f[:, 1])
                    * (f[:, 2] if dz else 1 - f[:, 2])
                )
                out = out + w * _hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
    return out


def fbm(p, base=4.0, octaves=5, seed=0):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + amp * value_noise(p, base * 2 ** o, seed + o)
        norm += amp
        amp *= 0.55
    return total / norm


PALETTES = {
    "terracotta": (np.array([0.55, 0.27, 0.15]), np.array([0.93, 0.68, 0.45])),
    "bronze": (np.array([0.20, 0.25, 0.18]), np.array([0.78, 0.62, 0.32])),
    "stone": (np.array([0.30, 0.30, 0.33]), np.array([0.85, 0.83, 0.78])),
    "lapis": (np.array([0.08, 0.14, 0.40]), np.array([0.55, 0.70, 0.95])),
}


def shade_material(p, name, seed):
    lo, hi = PALETTES[name]
    n = fbm(p, base=6.0, octaves=6, seed=seed)
    speckle = value_noise(p, 60.0, seed + 31)  # fine grain gives features
    veins = 0.5 + 0.5 * np.sin(p[:, 2] * 22 + 6 * fbm(p, 2.0, 3, seed + 9))
    t = 0.55 * n + 0.15 * veins + 0.30 * speckle
    t = np.clip((t - 0.5) * 2.2 + 0.5, 0, 1)[:, None]  # boost contrast
    return lo * (1 - t) + hi * t


# --------------------------------------------------------------------------- #
# Ray casting
# --------------------------------------------------------------------------- #
def hit_sphere(o, d, c, r):
    oc = o - c
    b = np.einsum("ij,ij->i", oc, d)
    cc = np.einsum("ij,ij->i", oc, oc) - r * r
    disc = b * b - cc
    t = -b - np.sqrt(np.maximum(disc, 0))
    t[(disc < 0) | (t <= 1e-4)] = np.inf
    n = (o + t[:, None] * d - c) / r
    return t, n


def hit_box(o, d, lo, hi):
    with np.errstate(divide="ignore", invalid="ignore"):
        inv = 1.0 / d
        t1 = (lo - o) * inv
        t2 = (hi - o) * inv
    tmin = np.nanmax(np.minimum(t1, t2), axis=1)
    tmax = np.nanmin(np.maximum(t1, t2), axis=1)
    t = np.where((tmax >= tmin) & (tmin > 1e-4), tmin, np.inf)
    axis = np.argmax(np.minimum(t1, t2), axis=1)
    n = np.zeros_like(o)
    n[np.arange(len(o)), axis] = -np.sign(d[np.arange(len(o)), axis])
    return t, n


def build_scene():
    objs = [
        ("box", (np.array([-1.6, -1.6, -0.25]), np.array([1.6, 1.6, 0.0])), "stone", 1),
        ("box", (np.array([-0.55, -0.55, 0.0]), np.array([0.55, 0.55, 0.45])), "bronze", 2),
        ("sphere", (np.array([0.0, 0.0, 1.05]), 0.6), "terracotta", 3),
        ("sphere", (np.array([0.0, 0.0, 1.78]), 0.22), "lapis", 4),
        ("box", (np.array([0.85, -0.35, 0.0]), np.array([1.25, 0.05, 0.4])), "lapis", 5),
        ("box", (np.array([-1.3, 0.6, 0.0]), np.array([-0.8, 1.1, 0.3])), "terracotta", 6),
        ("box", (np.array([0.3, 0.9, 0.0]), np.array([0.7, 1.3, 0.55])), "bronze", 7),
    ]
    return objs


def render(eye, target, width, height, focal, scene):
    fwd = target - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0.0, 0.0, 1.0]))
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)

    xs, ys = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    u = (xs.ravel() - width / 2) / focal
    v = (ys.ravel() - height / 2) / focal
    d = fwd[None] + u[:, None] * right[None] + v[:, None] * down[None]
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    o = np.repeat(eye[None], len(d), axis=0)

    best_t = np.full(len(d), np.inf)
    best_n = np.zeros_like(d)
    best_id = np.full(len(d), -1)
    for idx, (kind, geom, _, _) in enumerate(scene):
        if kind == "sphere":
            t, n = hit_sphere(o, d, *geom)
        else:
            t, n = hit_box(o, d, *geom)
        closer = t < best_t
        best_t[closer] = t[closer]
        best_n[closer] = n[closer]
        best_id[closer] = idx

    # Plain, feature-poor studio backdrop (like a photo booth sweep).
    sky = 0.80 + 0.12 * (1 - (ys.ravel() / height))
    color = np.stack([sky * 0.97, sky * 0.98, sky], axis=1)
    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    for idx, (_, _, material, seed) in enumerate(scene):
        m = best_id == idx
        if not m.any():
            continue
        p = o[m] + best_t[m, None] * d[m]
        albedo = shade_material(p, material, seed)
        lam = np.clip(best_n[m] @ light, 0, 1)
        color[m] = albedo * (0.45 + 0.55 * lam)[:, None]
    img = (np.clip(color, 0, 1).reshape(height, width, 3) * 255).astype(np.uint8)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="samples/turntable")
    ap.add_argument("--views", type=int, default=24)
    ap.add_argument("--width", type=int, default=800)
    ap.add_argument("--height", type=int, default=600)
    ap.add_argument("--radius", type=float, default=4.4)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scene = build_scene()
    focal = 1.2 * max(args.width, args.height)  # matches the engine's default prior
    target = np.array([0.0, 0.0, 0.75])
    for k in range(args.views):
        a = 2 * np.pi * k / args.views
        elev = np.deg2rad(28 + 8 * np.sin(2 * a))
        eye = target + args.radius * np.array(
            [np.cos(a) * np.cos(elev), np.sin(a) * np.cos(elev), np.sin(elev)]
        )
        img = render(eye, target, args.width, args.height, focal, scene)
        path = out / f"view_{k:03d}.jpg"
        Image.fromarray(img).save(path, quality=93)
        print("wrote", path)


if __name__ == "__main__":
    main()

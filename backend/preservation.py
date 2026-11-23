"""Preservation outputs: single-artifact digital record, printable HTML report
and a checksummed archive package (BagIt-style layout)."""
from __future__ import annotations

import hashlib
import html
import json
import zipfile
from pathlib import Path

from . import config
from .db import now

RECORD_FIELDS = [
    ("Identity", ["id", "title", "category"]),
    ("Description", ["description", "material", "dimensions", "condition"]),
    ("Context", ["creator", "period", "origin"]),
    ("Provenance & rights", ["provenance", "rights", "license_url", "review_status"]),
    ("Record", ["created_at", "updated_at"]),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_record(artifact: dict, assets: list[dict], jobs: list[dict], predictions: list[dict]) -> dict:
    integrity = []
    for a in assets:
        p = Path(a["path"])
        current = sha256_file(p) if p.is_file() else None
        integrity.append({
            "asset_id": a["id"], "original_filename": a.get("original_filename", ""),
            "stored_sha256": a["checksum"], "current_sha256": current,
            "status": "ok" if current == a["checksum"] else ("missing" if current is None else "mismatch"),
        })
    return {
        "export_version": "artifactscan-record/1",
        "generated_at": now(),
        "generator": f"ArtifactScan AI {config.VERSION}",
        "artifact": {k: v for k, v in artifact.items()},
        "missing_fields": [k for k, v in artifact.items() if v in ("", None)],
        "assets": [{k: v for k, v in a.items() if k != "path"} for a in assets],
        "integrity_check": integrity,
        "reconstructions": [
            {**{k: v for k, v in j.items() if k not in ("output_dir", "stats_json")},
             "stats": json.loads(j.get("stats_json") or "{}")}
            for j in jobs
        ],
        "classifications": [
            {**{k: v for k, v in p.items() if k != "scores_json"}, "scores": json.loads(p["scores_json"])}
            for p in predictions
        ],
        "notes": [
            "Checksums prove file integrity, not authenticity or historical correctness.",
            "AI labels are uncalibrated suggestions and are not authoritative provenance.",
        ],
    }


def build_package(record: dict, assets: list[dict], jobs: list[dict]) -> Path:
    art = record["artifact"]
    stamp = now().replace(":", "").replace("-", "")[:15]
    target = config.EXPORTS / f"artifact_{art['id'][:8]}_{stamp}.zip"
    manifest: list[tuple[str, str]] = []

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        def add_file(src: Path, arc: str):
            z.write(src, arc)
            manifest.append((sha256_file(src), arc))

        def add_bytes(data: bytes, arc: str):
            z.writestr(arc, data)
            manifest.append((hashlib.sha256(data).hexdigest(), arc))

        add_bytes(json.dumps(record, indent=2).encode(), "data/record.json")
        add_bytes(render_report(record).encode(), "data/report.html")
        for a in assets:
            p = Path(a["path"])
            if p.is_file():
                add_file(p, f"data/originals/{a['filename']}")
        for j in jobs:
            if j["status"] != "completed" or not j.get("output_dir"):
                continue
            out = Path(j["output_dir"])
            for name in ("sparse_point_cloud.ply", "cameras.json", "reconstruction_stats.json", "job.log"):
                if (out / name).is_file():
                    add_file(out / name, f"data/reconstructions/{j['id']}/{name}")
        z.writestr("bagit.txt", "BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n")
        z.writestr("bag-info.txt",
                   f"Source-Organization: ArtifactScan AI\nBagging-Date: {record['generated_at'][:10]}\n"
                   f"External-Identifier: {art['id']}\nExternal-Description: {art['title']}\n")
        z.writestr("manifest-sha256.txt", "".join(f"{h}  {p}\n" for h, p in manifest))
    return target


def render_report(record: dict) -> str:
    e = lambda v: html.escape(str(v if v not in (None, "") else "—"))  # noqa: E731
    art = record["artifact"]
    sections = []
    for title, keys in RECORD_FIELDS:
        rows = "".join(f"<tr><th>{e(k.replace('_', ' ').title())}</th><td>{e(art.get(k))}</td></tr>" for k in keys)
        sections.append(f"<h2>{e(title)}</h2><table>{rows}</table>")
    assets = "".join(
        f"<tr><td>{e(i['original_filename'] or i['asset_id'])}</td><td><code>{e(i['stored_sha256'][:16])}…</code></td>"
        f"<td class='{e(i['status'])}'>{e(i['status'])}</td></tr>"
        for i in record["integrity_check"]
    ) or "<tr><td colspan=3>No images recorded.</td></tr>"
    recon = "".join(
        f"<tr><td><code>{e(j['id'][:8])}</code></td><td>{e(j['status'])}</td><td>{e(j.get('engine'))}</td>"
        f"<td>{e(j['stats'].get('images_registered'))}/{e(j['stats'].get('images_input'))}</td>"
        f"<td>{e(j['stats'].get('points'))}</td><td>{e(j.get('finished_at') or j['updated_at'])}</td></tr>"
        for j in record["reconstructions"]
    ) or "<tr><td colspan=6>No reconstruction jobs.</td></tr>"
    preds = "".join(
        f"<tr><td>{e(p['predicted_label'])}</td><td>{e(p['scores'][0]['score'] if p['scores'] else '')}</td>"
        f"<td>{e(p['model_version'])}</td><td>{e(p.get('reviewer_label'))}</td></tr>"
        for p in record["classifications"]
    ) or "<tr><td colspan=4>No classifier predictions.</td></tr>"
    notes = "".join(f"<li>{e(n)}</li>" for n in record["notes"])
    missing = ", ".join(record["missing_fields"]) or "none"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Digital record — {e(art['title'])}</title>
<style>
body{{font:14px/1.55 Georgia,'Times New Roman',serif;color:#1d2433;max-width:860px;margin:40px auto;padding:0 24px}}
h1{{font-size:28px;margin:0}}h2{{font-size:15px;text-transform:uppercase;letter-spacing:.08em;color:#8a6a2f;
border-bottom:1px solid #e6dcc8;padding-bottom:4px;margin-top:28px}}
table{{width:100%;border-collapse:collapse;font-family:system-ui,sans-serif;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}}th{{width:30%;color:#555;font-weight:600}}
.meta{{color:#667;font-family:system-ui,sans-serif;font-size:12px}}.ok{{color:#1a7f4b}}.mismatch,.missing{{color:#b3261e}}
@media print{{body{{margin:0}}}}
</style></head><body>
<p class="meta">ArtifactScan AI · Digital preservation record · generated {e(record['generated_at'])}</p>
<h1>{e(art['title'])}</h1><p class="meta">ID {e(art['id'])} · Incomplete fields: {e(missing)}</p>
{''.join(sections)}
<h2>Image assets &amp; integrity</h2><table><tr><th>File</th><th>SHA-256</th><th>Check</th></tr>{assets}</table>
<h2>3D reconstructions</h2><table>
<tr><th>Job</th><th>Status</th><th>Engine</th><th>Cameras</th><th>Points</th><th>Finished</th></tr>{recon}</table>
<h2>AI classification</h2><table><tr><th>Predicted</th><th>Score</th><th>Model</th><th>Reviewer label</th></tr>{preds}</table>
<h2>Notes</h2><ul>{notes}</ul>
</body></html>"""

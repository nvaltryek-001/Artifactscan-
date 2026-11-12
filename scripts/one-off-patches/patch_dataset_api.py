from pathlib import Path

p = Path("backend/main.py")
s = p.read_text(encoding="utf-8")

if '"/api/dataset"' in s:
    raise SystemExit("Dataset API route already exists. No changes made.")

old = "from fastapi.responses import HTMLResponse, StreamingResponse"
new = "from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse"

if old not in s:
    raise SystemExit("Could not locate FastAPI response import. No changes made.")

s = s.replace(old, new, 1)

anchor = '@app.get("/", response_class=HTMLResponse)'
if anchor not in s:
    raise SystemExit("Could not locate root route. No changes made.")

routes = r'''
DATASET_ROOT = ROOT / "data" / "imet"
DATASET_SPLITS = {"train", "validation"}


@app.get("/api/dataset")
def list_dataset(split: str = "train", limit: int = 60, offset: int = 0):
    import csv

    if split not in DATASET_SPLITS:
        raise HTTPException(400, "split must be train or validation")
    if limit < 1 or limit > 100:
        raise HTTPException(400, "limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(400, "offset must be non-negative")

    metadata = DATASET_ROOT / f"{split}_metadata.csv"
    images_dir = DATASET_ROOT / split
    if not metadata.is_file() or not images_dir.is_dir():
        raise HTTPException(503, "Dataset files are not installed")

    with metadata.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    items = []
    for row in rows:
        filename = row.get("filename", "")
        image_path = images_dir / filename
        if not filename or not image_path.is_file():
            continue
        items.append({
            "filename": filename,
            "title": row.get("title", ""),
            "label": row.get("label_name", ""),
            "object_id": row.get("object_id", ""),
            "object_url": row.get("object_url", ""),
            "image_url": f"/api/dataset/images/{split}/{filename}",
        })

    return {
        "source": "The Metropolitan Museum of Art — iMet Open Access subset",
        "split": split,
        "total": len(items),
        "offset": offset,
        "limit": limit,
        "items": items[offset:offset + limit],
    }


@app.get("/api/dataset/images/{split}/{filename}")
def dataset_image(split: str, filename: str):
    import re

    if split not in DATASET_SPLITS:
        raise HTTPException(400, "Invalid dataset split")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.jpg", filename):
        raise HTTPException(400, "Invalid image filename")

    path = DATASET_ROOT / split / filename
    if not path.is_file():
        raise HTTPException(404, "Dataset image not found")
    return FileResponse(path, media_type="image/jpeg")


'''

s = s.replace(anchor, routes + anchor, 1)
p.write_text(s, encoding="utf-8")
print("Added read-only dataset API routes.")

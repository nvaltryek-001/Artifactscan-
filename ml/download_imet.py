import csv, json, time
from pathlib import Path
from datasets import load_dataset
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "imet"
LIMITS = {"train": 1200, "validation": 300}
REPO = "timm/imet-open-access"

def download_split(split, limit):
    folder = OUT / split
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / f"{split}_metadata.csv"

    # Reuse an already completed split rather than downloading it again.
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        valid = [r for r in rows if (folder / r["filename"]).exists()]
        if len(valid) >= limit:
            print(f"{split}: reusing {len(valid)} saved records")
            return

    print(f"\nLoading {REPO} split={split} in streaming mode...")
    ds = load_dataset(REPO, split=split, streaming=True)
    ds = ds.shuffle(seed=42, buffer_size=250)

    label_names = ds.features["classification"].names
    rows, seen = [], 0
    started = time.time()

    for item in ds:
        label = item.get("classification")
        image = item.get("image")
        if label is None or image is None:
            continue
        try:
            label = int(label)
            if label < 0 or label >= len(label_names):
                continue
            image = image.convert("RGB")
            filename = f"{split}_{seen:06d}.jpg"
            image.save(folder / filename, "JPEG", quality=92)
            rows.append({
                "filename": filename,
                "label_id": label,
                "label_name": label_names[label],
                "title": str(item.get("title") or ""),
                "object_id": str(item.get("object_id") or ""),
                "object_url": str(item.get("object_url") or ""),
            })
            seen += 1
            if seen % 100 == 0:
                print(f"{split}: saved {seen}/{limit}")
            if seen >= limit:
                break
        except Exception as exc:
            print("Skipped one unreadable record:", repr(exc))

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filename", "label_id", "label_name",
            "title", "object_id", "object_url"
        ])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{split}: saved {len(rows)} images in {time.time()-started:.1f}s")

    if len(rows) == 0:
        raise RuntimeError(
            f"No images downloaded for {split}. Check network and dataset schema."
        )

    with (OUT / f"{split}_label_names.json").open("w", encoding="utf-8") as f:
        json.dump(label_names, f, ensure_ascii=False, indent=2)

def main():
    print("Dataset: iMet Open Access — The Metropolitan Museum of Art")
    print("License/source details: data/imet/DATASET_NOTES.txt")
    for split, limit in LIMITS.items():
        download_split(split, limit)

    print("\nDataset download stage finished.")
    print("Next: run ml/train_classifier.py")

if __name__ == "__main__":
    main()


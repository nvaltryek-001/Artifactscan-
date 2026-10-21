import csv, json
from pathlib import Path
from PIL import Image

root = Path("data/imet")
for split in ("train", "validation"):
    metadata = root / f"{split}_metadata.csv"
    folder = root / split

    if not metadata.exists():
        print(f"{split}: METADATA MISSING")
        continue

    with metadata.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    valid = 0
    missing = 0
    broken = 0
    labels = set()

    for row in rows:
        path = folder / row["filename"]
        if not path.exists():
            missing += 1
            continue
        try:
            with Image.open(path) as image:
                image.verify()
            valid += 1
            labels.add(row.get("label_name", ""))
        except Exception:
            broken += 1

    print(
        f"{split}: metadata={len(rows)}, valid_images={valid}, "
        f"missing={missing}, unreadable={broken}, "
        f"unique_labels={len(labels)}"
    )

    print("Example records:")
    for row in rows[:3]:
        print(json.dumps(row, ensure_ascii=False))

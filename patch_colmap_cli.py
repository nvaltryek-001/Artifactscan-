from pathlib import Path

path = Path("backend/main.py")
source = path.read_text(encoding="utf-8")

replacements = {
    '"feature_extractor",': '"colmap", "feature_extractor",',
    '"exhaustive_matcher",': '"colmap", "exhaustive_matcher",',
    '"mapper",': '"colmap", "mapper",',
    '"model_converter",': '"colmap", "model_converter",',
}

for old, new in replacements.items():
    count = source.count(old)
    if count != 1:
        raise SystemExit(
            f"Expected exactly one occurrence of {old}; found {count}. No changes made."
        )

if '"--FeatureExtraction.use_gpu", "0"' not in source:
    old = '"--ImageReader.single_camera", "1",'
    if source.count(old) != 1:
        raise SystemExit("Could not safely locate feature extraction options.")
    source = source.replace(
        old,
        old + '\n        "--FeatureExtraction.use_gpu", "0",',
        1,
    )

for old, new in replacements.items():
    source = source.replace(old, new, 1)

backup = path.with_suffix(".main.py.pre-colmap-cli.bak")
if backup.exists():
    raise SystemExit(f"Backup already exists: {backup}. No changes made.")

backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
path.write_text(source, encoding="utf-8")

print(f"Backup created: {backup}")
print("COLMAP executable prefixes and CPU feature extraction applied.")

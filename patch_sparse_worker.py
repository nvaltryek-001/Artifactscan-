from pathlib import Path
import re

path = Path("backend/main.py")
source = path.read_text(encoding="utf-8")

start = source.find("def run_colmap(")
if start < 0:
    raise SystemExit("ERROR: run_colmap() was not found.")

# Find the next top-level function or route after run_colmap().
matches = list(re.finditer(r"(?m)^(?:def |async def |@app\.)", source[start + 1:]))
if not matches:
    raise SystemExit("ERROR: Could not locate the end of run_colmap().")

end = start + 1 + matches[0].start()
old_function = source[start:end]

if "automatic_reconstructor" not in old_function:
    raise SystemExit("STOP: The expected original worker was not found. No changes made.")

replacement = r'''def run_colmap(job_id: str, image_paths: list[str]):
    import shutil
    import subprocess
    from pathlib import Path

    root = Path("storage/reconstructions").resolve()
    workspace = root / job_id
    images_dir = workspace / "images"
    sparse_dir = workspace / "workspace" / "sparse"
    workspace.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Prepare a clean workspace and copy the source images.
    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True)

    for index, item in enumerate(image_paths):
        src = Path(item)
        if not src.exists():
            raise FileNotFoundError(f"Input image not found: {src}")
        shutil.copy2(src, images_dir / f"image_{index:04d}{src.suffix.lower()}")

    # Convert Windows paths to paths inside the Docker container.
    container_workspace = f"/workspace/{job_id}"
    container_images = f"{container_workspace}/images"
    container_output = f"{container_workspace}/workspace"

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace.resolve()}:/workspace/{job_id}",
        "colmap/colmap:latest",
        "feature_extractor",
        "--database_path", f"{container_output}/database.db",
        "--image_path", container_images,
        "--ImageReader.single_camera", "1",
    ]
    result = subprocess.run(docker_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "COLMAP feature extraction failed.\n"
            + result.stdout[-3000:] + "\n" + result.stderr[-3000:]
        )

    match_cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace.resolve()}:/workspace/{job_id}",
        "colmap/colmap:latest",
        "exhaustive_matcher",
        "--database_path", f"{container_output}/database.db",
        "--FeatureMatching.use_gpu", "0",
    ]
    result = subprocess.run(match_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "COLMAP feature matching failed.\n"
            + result.stdout[-3000:] + "\n" + result.stderr[-3000:]
        )

    sparse_dir.mkdir(parents=True, exist_ok=True)
    mapper_cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace.resolve()}:/workspace/{job_id}",
        "colmap/colmap:latest",
        "mapper",
        "--database_path", f"{container_output}/database.db",
        "--image_path", container_images,
        "--output_path", f"{container_output}/sparse",
    ]
    result = subprocess.run(mapper_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "COLMAP sparse mapping failed.\n"
            + result.stdout[-3000:] + "\n" + result.stderr[-3000:]
        )

    models = [
        p for p in sparse_dir.iterdir()
        if p.is_dir() and (
            (p / "points3D.bin").exists() or (p / "points3D.txt").exists()
        )
    ]
    if not models:
        raise RuntimeError(
            "COLMAP did not produce a valid sparse 3D model. "
            "Check image overlap, focus, lighting, and camera movement."
        )

    model = max(
        models,
        key=lambda p: (p / "points3D.bin").stat().st_size
        if (p / "points3D.bin").exists()
        else (p / "points3D.txt").stat().st_size
    )

    model_relative = model.relative_to(workspace / "workspace").as_posix()
    ply_path = workspace / "sparse_point_cloud.ply"
    export_cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace.resolve()}:/workspace/{job_id}",
        "colmap/colmap:latest",
        "model_converter",
        "--input_path", f"{container_output}/{model_relative}",
        "--output_path", f"{container_workspace}/sparse_point_cloud.ply",
        "--output_type", "PLY",
    ]
    result = subprocess.run(export_cmd, capture_output=True, text=True)
    if result.returncode != 0 or not ply_path.exists() or ply_path.stat().st_size < 100:
        raise RuntimeError(
            "Sparse model was created, but PLY export failed.\n"
            + result.stdout[-3000:] + "\n" + result.stderr[-3000:]
        )

    print(f"Sparse reconstruction exported: {ply_path}")
    return str(ply_path)
'''

updated = source[:start] + replacement + source[end:]
path.write_text(updated, encoding="utf-8")
print("Sparse reconstruction worker patch applied.")

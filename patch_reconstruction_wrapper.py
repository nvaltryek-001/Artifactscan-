from pathlib import Path

path = Path("backend/main.py")
source = path.read_text(encoding="utf-8")

if "def run_reconstruction_job(" in source:
    raise SystemExit("Wrapper already exists. No changes made.")

route_marker = '@app.post("/api/artifacts/{artifact_id}/reconstructions")'
if route_marker not in source:
    raise SystemExit("Reconstruction route not found. No changes made.")

# Ensure the database directory exists before Docker starts COLMAP.
old = '    images_dir.mkdir(parents=True)\n\n    for index, item in enumerate(image_paths):'
new = '    images_dir.mkdir(parents=True)\n    (workspace / "workspace").mkdir(parents=True, exist_ok=True)\n\n    for index, item in enumerate(image_paths):'

if old not in source:
    raise SystemExit("Expected image setup code not found. No changes made.")

source = source.replace(old, new, 1)

wrapper = '''def run_reconstruction_job(job_id: str, artifact_id: str):
    from pathlib import Path

    try:
        with connect() as con:
            rows = con.execute(
                "SELECT path FROM assets WHERE artifact_id=? ORDER BY created_at",
                (artifact_id,),
            ).fetchall()

        image_paths = [row["path"] for row in rows]
        if len(image_paths) < 3:
            raise RuntimeError(
                f"Only {len(image_paths)} image paths found; at least 3 are required."
            )

        update_job(
            job_id, "running", "photogrammetry",
            f"Starting sparse reconstruction with {len(image_paths)} images."
        )

        output_path = run_colmap(job_id, image_paths)
        output_file = Path(output_path)

        if not output_file.is_file() or output_file.stat().st_size < 100:
            raise RuntimeError("Reconstruction finished without a valid PLY output.")

        update_job(
            job_id, "completed", "completed",
            f"Sparse point cloud exported: {output_file}",
            str(output_file.parent),
        )

    except Exception as exc:
        update_job(
            job_id, "failed", "photogrammetry",
            f"{type(exc).__name__}: {exc}",
        )
        print(f"Reconstruction job {job_id} failed: {exc}")


'''

source = source.replace(route_marker, wrapper + route_marker, 1)

old_call = "    background_tasks.add_task(run_colmap, job_id, artifact_id)"
new_call = "    background_tasks.add_task(run_reconstruction_job, job_id, artifact_id)"

if old_call not in source:
    raise SystemExit("Expected background task call not found. No changes made.")

source = source.replace(old_call, new_call, 1)

backup = path.with_suffix(".main.py.pre-wrapper.bak")
if backup.exists():
    raise SystemExit(f"Backup already exists: {backup}. No changes made.")

backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
path.write_text(source, encoding="utf-8")

print(f"Backup created: {backup}")
print("Reconstruction wrapper and output-directory fix applied.")

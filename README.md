# ArtifactScan AI

Local MVP for artifact records, validated image uploads, provenance fields,
SQLite persistence, CSV exports and real COLMAP job execution when available.

## Requirements
Python compatible with FastAPI, Pillow and the selected dependencies.
Photogrammetry requires a separately installed and verified COLMAP executable.

## Windows setup
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Current limitations
The classifier is not trained or enabled. The UI does not claim otherwise.
COLMAP must be installed separately. Reconstruction outputs require quality
inspection; a successful process alone does not establish scientific accuracy.
The MVP does not yet provide production authentication or multi-user isolation.
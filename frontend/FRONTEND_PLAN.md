# ArtifactScan AI - Frontend Plan

## Design
- Clean white theme
- Navy typography
- Warm gold and bronze accents
- Responsive dashboard
- Museum and cultural heritage visuals

## Planned pages
1. Overview Dashboard
2. Artifact Collection
3. Capture Studio
4. 3D Reconstruction
5. AI Classification
6. Research and Analytics
7. Reports and Export
8. Settings

## Backend integration
- FastAPI base URL: http://127.0.0.1:8000
- GET /api/health
- GET /api/readiness
- GET /api/artifacts
- POST /api/artifacts
- POST /api/artifacts/{artifact_id}/images
- POST /api/artifacts/{artifact_id}/reconstructions
- GET /api/jobs/{job_id}
- GET /api/artifacts/{artifact_id}/classification
- GET /api/reports/artifacts.csv

## Important
Display real API data wherever available.
Do not fabricate reconstruction results or AI predictions.
The classifier endpoint must be integrated before claiming live predictions.

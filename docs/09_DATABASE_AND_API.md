# Database Design and API Contracts

## Core entities

### Artifact
id, title, description, category, creator, historical_period, material, dimensions, scale_method, provenance, rights_statement, license_url, created_at, updated_at, review_status.

### Asset
id, artifact_id, asset_type, storage_key, original_filename, media_type, size_bytes, checksum, format, metadata_json, created_at.

### ReconstructionJob
id, artifact_id, status, current_stage, progress_if_measured, tool_version, parameters_json, started_at, finished_at, error_code, safe_error_message, log_asset_id.

### Prediction
id, artifact_id, model_version, predicted_label, scores_json, status, created_at, reviewer_label, reviewed_at.

### DatasetRecord
id, dataset_version, source_url, license, attribution, checksum, category, split, review_status.

### AuditEvent
id, actor_id_if_available, entity_type, entity_id, action, timestamp, safe_details_json.

## Data rules
Use primary keys, foreign keys, indexes and migrations. Validate data at API boundaries. Store timestamps consistently in UTC. Use transactions for related database changes. Never store passwords or secrets in plain text. Use JSON fields only where flexible metadata is justified.

## Proposed API
- POST /api/artifacts
- GET /api/artifacts
- GET /api/artifacts/{id}
- PATCH /api/artifacts/{id}
- POST /api/artifacts/{id}/images
- POST /api/artifacts/{id}/reconstructions
- GET /api/jobs/{job_id}
- GET /api/jobs/{job_id}/logs
- GET /api/artifacts/{id}/predictions
- POST /api/artifacts/{id}/classifications
- POST /api/artifacts/{id}/review
- GET /api/artifacts/{id}/assets
- GET /api/reports/summary
- GET /api/health
- GET /api/readiness

Adjust route names to the implemented contract and document all changes.

## API requirements
Use Pydantic request/response schemas, appropriate HTTP status codes, pagination and consistent error structures. Validate identifiers and uploaded files. Protect download routes and avoid exposing filesystem paths. CORS must be explicitly configured. Health checks must not reveal secrets.

## Persistence
SQLite is suitable for the local MVP if access patterns are controlled. Use migrations and keep database files out of source control. PostgreSQL is the production target if concurrent usage and deployment requirements justify it.
# Deployment, Release Packaging and Implementation Roadmap

## Milestones

### M0 — Inspect and baseline
Inspect the current workspace, Git remotes, installed runtimes and available disk space. Record the starting state. Do not delete prior work or clone over an existing directory.

### M1 — Foundation
Create application skeleton, configuration, health endpoint, database migration, API client, frontend shell and reproducible setup scripts.

### M2 — Artifact catalogue
Implement create/edit/search/detail views, metadata persistence, upload validation and asset storage.

### M3 — Real reconstruction
Verify the photogrammetry tool and its platform requirements. Implement background jobs, real processing, output validation, viewer loading, error reporting and a small reproducible fixture test.

### M4 — Dataset and classifier
Prepare a license-aware manifest, inspect dataset quality, train and evaluate a baseline model, register model versions and implement inference plus human review.

### M5 — Preservation and reports
Add checksums, provenance, metadata exports, asset inventory and printable reports.

### M6 — Quality and security
Run unit, integration and browser tests. Address upload security, secrets, permissions, resource limits and recovery behavior.

### M7 — Release
Create setup instructions, environment example, Docker configuration where verified, local Windows scripts, release notes and the ZIP archive.

## Local commands to provide
- scripts/setup.ps1
- scripts/run-dev.ps1
- scripts/test.ps1
- scripts/package.ps1

Each script must check prerequisites, stop on meaningful errors and explain what it is doing. Avoid silently installing system-wide software or overwriting user data.

## Environment configuration
Provide .env.example with placeholder values only. Validate required settings on startup. Optional services should have a clear disabled state. Never commit actual keys or credentials.

## ZIP requirements
Target: dist/ArtifactScanAI.zip
Include source, documentation, dependency manifests, migrations, scripts, tests and necessary small licensed fixtures.
Exclude .git, virtual environments, node_modules, caches, secrets, local databases, private uploads, large unlicensed datasets and unnecessary generated outputs.
Verify the archive opens, contains expected files and excludes sensitive paths. Record its size and SHA-256 checksum if feasible.

## Deployment
Prefer a reproducible Docker Compose setup if all images and dependencies are compatible. Also document native Windows development. Production deployment requires configured secrets, persistent storage, database backups, HTTPS, authentication, monitoring and resource limits. Mark any unimplemented controls as limitations.

## Final report
Report completed features, partially completed features, exact test commands and results, real reconstruction availability, classifier evaluation results, environment limitations, known issues, deployment status and ZIP location. Estimate progress by verified acceptance criteria rather than number of files or lines of code.
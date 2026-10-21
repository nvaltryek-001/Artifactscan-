# Application Folder Structure

## Target structure
ArtifactScanAI-Rebuild/
  README.md
  .gitignore
  .env.example
  docker-compose.yml
  Dockerfile
  docs/                         # The 12 blueprint documents
  scripts/
    setup.ps1
    run-dev.ps1
    test.ps1
    package.ps1
  frontend/
    package.json
    vite.config.ts
    src/
      app/
      components/
      features/
        artifacts/
        uploads/
        reconstruction/
        classification/
        catalogue/
        reports/
      services/
      types/
      styles/
      tests/
  backend/
    pyproject.toml
    app/
      main.py
      api/
      core/
      schemas/
      models/
      repositories/
      services/
      workers/
      reconstruction/
      classification/
      preservation/
      storage/
    migrations/
    tests/
  data/
    README.md
    manifests/
    samples/
  storage/
    uploads/
    reconstructions/
    exports/
  models/
    README.md
  deployment/
    Dockerfile.frontend
    Dockerfile.backend
    healthchecks/
  dist/

## Folder responsibilities
- frontend: presentation, navigation, forms, viewers and API client.
- backend/api: HTTP endpoints and request/response handling.
- backend/services: business rules and orchestration.
- backend/repositories: database access.
- backend/workers: long-running jobs.
- backend/reconstruction: photogrammetry integration and output checks.
- backend/classification: training, inference and evaluation interfaces.
- backend/preservation: metadata, provenance, reports and exports.
- data/manifests: dataset inventory and license/provenance information.
- models: model instructions and metadata; do not commit huge weights without an explicit policy.
- storage: local runtime data, excluded from Git unless a small intentional fixture is needed.
- scripts: repeatable Windows developer operations.
- dist: generated release packages, not source code.

## Rules
- Keep secrets and user uploads out of version control.
- Add small fixtures for tests; do not require a large dataset to run basic tests.
- Use a single documented configuration system.
- Separate sample data from real datasets and generated output.
- Create this structure incrementally and keep the working application runnable after each milestone.
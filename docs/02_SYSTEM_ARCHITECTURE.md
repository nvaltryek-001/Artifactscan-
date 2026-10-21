# System Architecture and Technology Decisions

## Proposed architecture
Browser UI -> API backend -> relational database
                         -> upload/object storage
                         -> background job queue/worker
Worker -> photogrammetry engine -> validated 3D assets
Worker/API -> trained classifier -> prediction record
API -> reports, metadata exports and download authorization

## Initial technology choices
- Frontend: React, Vite, TypeScript, Three.js or React Three Fiber
- Backend: Python FastAPI with Pydantic validation
- Database: SQLite for local MVP; PostgreSQL for production
- Background work: a separate worker process; Redis/queue only when justified
- Reconstruction: COLMAP or another verified photogrammetry tool
- Model inspection: Three.js with format-specific loaders
- ML: PyTorch or compatible scikit-learn baseline, selected after environment tests
- Packaging: Docker Compose where supported; native Windows instructions as an alternative
- Testing: pytest, frontend unit tests and browser-based end-to-end tests

## Architecture rules
- Keep API routes, domain logic, persistence and external tools separate.
- Never run long reconstruction jobs synchronously inside a request.
- Use persistent job IDs and explicit states: queued, running, succeeded, failed, cancelled.
- Store large files outside database rows; save paths or object keys and metadata.
- Make external tool locations and storage paths configurable.
- Validate every subprocess argument and never build shell commands from user input.
- Add timeouts, logs, cleanup and disk-space checks.
- Use database migrations as the schema evolves.

## Development strategy
Begin with a locally runnable vertical slice. Prove upload, record persistence, job execution and output retrieval before adding distributed infrastructure. Avoid Kafka, microservices or Kubernetes unless demonstrated requirements justify their operational cost.

## Python compatibility gate
The machine reports Python 3.14. Test package availability before selecting versions. If scientific or photogrammetry dependencies are incompatible, use an isolated Python version supported by those dependencies. Do not downgrade or alter the system Python automatically.

## Architecture decision records
Document significant decisions with context, alternatives, consequences and date. Never claim production readiness based only on a successful local launch.
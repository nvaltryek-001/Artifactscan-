# Testing, Security and Quality Gates

## Testing layers
1. Backend unit tests for schemas, services and validation.
2. Database integration tests for persistence and relationships.
3. API tests for success, invalid input and error states.
4. Reconstruction tests using tiny, licensed fixtures or mocked tool boundaries.
5. Classifier tests using a known test fixture and verified model.
6. Frontend component and API-client tests.
7. End-to-end browser tests for create, upload, job status and record retrieval.
8. Packaging tests that inspect the final ZIP.
9. Optional performance and deployment smoke tests.

## Required scenarios
- Empty and invalid uploads are rejected.
- Unsupported file types and excessive file sizes are rejected.
- Artifact data persists after backend restart.
- Missing photogrammetry executable is reported clearly.
- Reconstruction failure is saved with diagnostic information.
- Invalid or empty 3D outputs are not published as success.
- Missing classifier weights produce unavailable status.
- Human review does not erase the original prediction.
- Unauthorized or malformed asset requests are rejected.
- Search, pagination and exports handle empty datasets.
- Secrets and private uploads are excluded from the release package.

## Security controls
- Allowlist accepted file types and inspect actual content where feasible.
- Enforce file size, image count and request limits.
- Generate server-side storage names; do not trust user filenames.
- Prevent path traversal and unsafe archive extraction.
- Run subprocesses with argument lists, timeouts and constrained permissions.
- Keep secrets in environment variables and exclude .env from Git.
- Apply authentication and authorization before exposing private data.
- Restrict CORS and configure TLS at the deployment edge.
- Sanitize logs and report output.
- Add rate limits and resource limits before public exposure.
- Document upload retention and deletion policy.

## Quality gates
- Linting and type checks pass.
- Backend and frontend builds pass.
- Automated tests pass and actual counts are recorded.
- Critical user flows pass in a browser.
- API documentation matches implementation.
- Dependency and secret scans are reviewed.
- ZIP contents are inspected and archive integrity is verified.

Never claim a test, scan or deployment passed unless it was actually executed. Clearly distinguish unit tests, mocked integration tests and tests requiring real external tools.
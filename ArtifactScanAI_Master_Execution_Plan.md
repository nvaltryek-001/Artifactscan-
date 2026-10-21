# ArtifactScan AI --- Master Execution Plan

**Project root:** `N:\ArtifactScanAI-Rebuild`\
**Last verified from user-provided terminal output:** 2026-10-21\
**Purpose:** Single source of truth for repeatedly completing, testing,
and documenting the remaining project work.

> **Status honesty rule:** Do not mark a task complete because code
> exists or a command was attempted. Mark it complete only after its
> acceptance test passes and the evidence is recorded. The current
> overall percentage is a rough planning estimate, not a measured
> metric.

## 1. Working rules --- follow every session

1.  **Use this file as the project checklist.** At the start of each
    work session, review Sections 2--7 and update the session log.
2.  **One change set at a time.** Inspect existing code before editing.
    Make a timestamped backup or use Git before changing important
    files.
3.  **Never guess file contents or API schemas.** Read the real files,
    routes, database schema, and logs first.
4.  **No destructive cleanup without a backup and explicit scope.** Do
    not delete uploaded photos, database rows, job history, or
    reconstruction folders casually.
5.  **Do not fake success.** A reconstruction is successful only when
    the output file exists, is non-empty, parses as a valid model, and
    can be loaded in the viewer.
6.  **Separate image capture, reconstruction, model export, and viewer
    rendering.** Each stage needs its own status and error message.
7.  **Use genuine reconstruction inputs for the real demo.** Prefer
    40--80 sharp, overlapping photos of the same textured, stationary
    object, with the camera moving around it. Avoid blur, reflections,
    featureless surfaces, changing backgrounds, and large lighting
    changes. Synthetic views are for experiments, not a guaranteed
    photogrammetry solution.
8.  **Hardware-aware pipeline.** Detect Docker/COLMAP capabilities. Do
    not assume CUDA/GPU is available. The known dense PatchMatch path
    may fail without GPU support; sparse reconstruction and dense
    reconstruction must be handled as distinct stages.
9.  **Test after each meaningful change.** Run Python tests, JavaScript
    syntax checks when available, API checks, and the relevant browser
    flow. Record actual results.
10. **Keep the app usable when something fails.** Show actionable
    errors; never show a fake model or report completion if no valid
    model exists.
11. **Keep secrets out of logs and commits.** Do not commit virtual
    environments, uploaded user images, databases containing personal
    data, secrets, or large generated artifacts unless intentionally
    required.
12. **Update this plan after every session.** Mark tasks `DONE`,
    `IN PROGRESS`, `BLOCKED`, or `NOT STARTED`; include evidence and the
    next exact action.
13. **Do not claim the "12-file guide" is complete until the guide is
    identified and each item has been checked against the actual
    project.**
14. **Progress percentages are estimates until a task-weighted checklist
    is scored.** Report completed, partial, and pending work separately.

## 2. Verified baseline

Based on terminal output supplied on 2026-10-21:

-   API readiness reported `api: true`, `database: true`,
    `colmap: true`, `colmap_runtime: docker`.
-   Classifier readiness reported `classifier: false`, note: no trained
    model configured.
-   A recursive search under `storage` found no `.ply`, `.obj`, `.glb`,
    `.gltf`, or `.stl` files at that time.
-   `backend/main.py` contains a COLMAP sparse pipeline:
    1.  Copies source images into a job workspace.
    2.  Runs `feature_extractor`.
    3.  Runs `exhaustive_matcher`.
    4.  Runs `mapper`.
    5.  Exports a sparse point cloud as `sparse_point_cloud.ply`.
-   The backend job marks completion after the PLY exists and is at
    least 100 bytes; it does not yet prove the browser viewer can load
    it.
-   `frontend/index.html` still has the static "Your 3D model will
    appear here" placeholder and no confirmed Three.js / model-viewer /
    PLY loader was found in the inspected snippet.
-   `frontend/static/app.js` submits reconstruction jobs and polls
    `/api/jobs/{job_id}` only eight times at 2.5 seconds each (about 20
    seconds); this can stop polling before a long job finishes.
-   Automatic webcam scanner UI and frame-change capture code were
    added. It does not verify blur, camera coverage, or useful feature
    overlap; it can collect unsuitable views.
-   Previous COLMAP jobs failed with "No good initial image pair found"
    / "Discarding reconstruction due to bad initial pair".
-   Prior sample images were approximately 102 × 105/106 pixels,
    unsuitable for a convincing real photogrammetry demo.
-   Existing tests were previously reported as 5 passing in
    `tests/test_api.py`; rerun them before relying on this result.
-   Current rough estimate from the conversation was around 50%, but it
    is not a verified score.

## 3. Definition of done

The core demo is complete only when all of the following pass:

-   [ ] User can select or create an artifact.
-   [ ] Upload validation rejects unsupported, corrupt, too-small, or
    excessive files with clear messages.
-   [ ] Uploaded image count and file paths are consistent in the
    database and storage.
-   [ ] A new reconstruction job is created and its status can be
    queried until terminal state.
-   [ ] Logs identify the failed stage if reconstruction fails.
-   [ ] Suitable images produce a valid COLMAP sparse model and a
    non-empty exported point cloud.
-   [ ] Model output is exposed through a safe API/static-file route,
    not an arbitrary filesystem path.
-   [ ] Browser loads the actual model and supports orbit/rotate, zoom,
    pan, reset, and loading/error states.
-   [ ] The UI distinguishes point cloud from mesh; do not call a point
    cloud a textured mesh.
-   [ ] If mesh generation is supported, export a valid mesh such as
    PLY/OBJ/GLB and verify it separately.
-   [ ] End-to-end browser test: select artifact → upload images → start
    job → wait → load model → interact with model.
-   [ ] Tests pass and a concise demo procedure is documented.
-   [ ] No destructive database or image cleanup occurs without a backup
    and explicit target.

## 4. Priority work plan

### P0 --- Protect and inspect the current project

Status: NOT STARTED for this session.

-   [ ] Confirm the app startup command and whether Git is initialized.
-   [ ] Create a timestamped backup of `backend/main.py`,
    `frontend/index.html`, `frontend/static/app.js`,
    `frontend/static/styles.css`, and the SQLite database before edits.
-   [ ] Record current test output, API readiness, latest jobs, database
    schema, image counts, and existing reconstruction files.
-   [ ] Do not delete the 120 old image records until a safe, verified
    cleanup procedure is prepared and approved.

Acceptance: backup exists and diagnostics are saved; no project data
lost.

### P1 --- Make reconstruction diagnosable and reliable

Status: IN PROGRESS --- pipeline exists, but successful model output is
not verified.

-   [ ] Inspect the full `backend/main.py`, DB schema, job status
    endpoint, and complete failure logs.
-   [ ] Verify Docker volume mapping and output path consistency on
    Windows.
-   [ ] Log image count, dimensions, feature counts, verified matches,
    mapper result, model folder, and export result per job.
-   [ ] Check that at least three images are valid and that there is
    adequate overlap before starting COLMAP.
-   [ ] Keep sparse reconstruction separate from optional dense
    reconstruction/meshing.
-   [ ] Make all terminal job statuses consistent (`completed` vs
    `succeeded` etc.) across API and UI.
-   [ ] Confirm generated output path and file type with a parser or
    header check.

Acceptance: a suitable test dataset creates a valid PLY, or the UI
displays a clear stage-specific failure with useful logs. Do not mark
success merely because COLMAP exits zero.

### P2 --- Implement the real 3D viewer

Status: NOT STARTED --- placeholder remains in the inspected HTML.

-   [ ] Choose a browser viewer that can load the actual exported format
    (for example, a Three.js PLY loader for point clouds, and
    appropriate mesh loader for OBJ/GLB).
-   [ ] Add a stable viewer container/canvas and responsive sizing.
-   [ ] Add loading, success, empty, and error states.
-   [ ] Add orbit controls, zoom, pan, reset camera, and model-fit
    behavior.
-   [ ] Ensure viewer requests a served model URL from the API and never
    tries to read a Windows filesystem path directly.
-   [ ] Confirm large model loading and browser console errors.

Acceptance: an actual generated model file is visible and can be rotated
and zoomed in the browser.

### P3 --- Fix job status and frontend flow

Status: IN PROGRESS --- basic submission/polling exists.

-   [ ] Poll until a terminal state with a reasonable timeout/backoff,
    rather than stopping after about 20 seconds.
-   [ ] On completion, retrieve the model metadata/URL and load it into
    the viewer.
-   [ ] On failure, show the stage and actionable error.
-   [ ] Disable duplicate submissions while a job is active.
-   [ ] Refresh artifact image counts after upload and reflect real
    backend state.
-   [ ] Handle API timeouts and network errors clearly.

Acceptance: frontend status accurately follows queued → running →
completed/failed and loads the model on completion.

### P4 --- Verify camera capture and dataset quality

Status: IN PROGRESS --- capture UI exists; quality validation is
incomplete.

-   [ ] Make camera permission and unavailable-camera errors friendly.
-   [ ] Capture sharp frames with sufficient overlap; do not rely on
    frame-change detection alone.
-   [ ] Provide clear guidance to move the camera around a stationary
    object.
-   [ ] Use a textured, matte object and stable diffuse lighting.
-   [ ] Avoid capturing only rotating backgrounds or duplicate frames.
-   [ ] Add a preview/review step before uploading captures.
-   [ ] Test using full-resolution camera images, not tiny sample
    thumbnails.

Acceptance: captured set has adequate image dimensions and visually
useful overlapping views; reconstruction result is evaluated.

### P5 --- Safe image/data cleanup

Status: NOT STARTED.

-   [ ] Inspect schema and all references to the old 120 images.
-   [ ] Back up SQLite database and copy/backup image folder.
-   [ ] Prepare a dry-run report listing exact asset IDs and exact file
    paths targeted.
-   [ ] Confirm cleanup scope is limited to the intended
    artifact/assets; preserve unrelated artifacts and job records unless
    explicitly intended.
-   [ ] Delete database rows and files consistently in a
    transaction-aware process, with rollback or restore instructions.
-   [ ] Verify database counts, filesystem counts, and API output after
    cleanup.

Acceptance: only the explicitly targeted records/files are removed and
unrelated data is intact.

### P6 --- Classifier and remaining project features

Status: NOT STARTED / NOT CONFIGURED.

-   [ ] Identify the intended classifier, supported labels, training
    dataset, model format, and inference dependencies.
-   [ ] Do not invent classification results when no trained model is
    configured.
-   [ ] Add model loading, validation, inference endpoint integration,
    and user-visible confidence/limitations only after a real model is
    available.
-   [ ] Test classifier independently from 3D reconstruction.
-   [ ] Audit all remaining features in the actual project and the
    referenced 12-file guide.

Acceptance: classification is backed by a real model and test cases, or
is explicitly labelled unavailable. Remaining guide items are
individually verified.

### P7 --- End-to-end test and demo readiness

Status: NOT STARTED.

-   [ ] Run
    `.\.venv\Scripts\python.exe -m pytest .\tests\test_api.py -q`.
-   [ ] Run `node --check .\frontend\static\app.js` if Node is
    installed.
-   [ ] Check `/api/health` and `/api/readiness`.
-   [ ] Run a reconstruction with a suitable image set.
-   [ ] Confirm model file exists, is non-empty, and loads in the
    browser.
-   [ ] Test failure path with an unsuitable set and confirm a useful
    message.
-   [ ] Test responsive layout and browser console.
-   [ ] Record evidence, known limitations, and exact demo steps.
-   [ ] If Git is initialized, review `git diff`, run tests, and commit
    a focused change set.

Acceptance: complete user journey passes on the target machine and demo
steps can be repeated.

## 5. Useful diagnostic commands

Run from PowerShell:

``` powershell
Set-Location "N:\ArtifactScanAI-Rebuild"

# API readiness
Invoke-RestMethod "http://127.0.0.1:8000/api/readiness" |
  ConvertTo-Json -Depth 5

# Tests
.\.venv\Scripts\python.exe -m pytest .\tests\test_api.py -q

# JavaScript syntax (if Node is installed)
node --check .\frontend\static\app.js

# Find model files
Get-ChildItem ".\storage" -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in ".ply", ".obj", ".glb", ".gltf", ".stl" } |
  Select-Object FullName, Length, LastWriteTime

# Check whether Git is initialized
git status --short
```

If an API route fails, capture its status and response body. Never infer
a successful model from API readiness alone.

## 6. Session handoff template

Append a new entry after each work session:

``` text
Date/time:
Task attempted:
Files inspected:
Files changed:
Backup or Git commit:
Commands/tests run:
Actual results:
Evidence/model output path:
Known blockers:
Checklist items changed:
Next exact action:
```

## 7. Session log

### 2026-10-21 --- Baseline from user-provided output

-   API/database/COLMAP readiness returned true; classifier was false.
-   No supported 3D model files were found under `storage`.
-   Backend sparse COLMAP + PLY export code exists.
-   Frontend contains a static placeholder; an actual 3D model loader
    was not found in the inspected HTML.
-   Frontend job polling stops after eight 2.5-second attempts.
-   Prior jobs failed because COLMAP could not find a good initial image
    pair.
-   Next action: back up the project and inspect full backend routes,
    database schema, logs, and frontend assets; then implement one
    tested improvement at a time.

## 8. Rule for future assistant sessions

When continuing this project: 1. Read this plan first. 2. Ask for
current terminal output only when needed; don't ask for information
already in the plan. 3. Work on the highest-priority unchecked item. 4.
Inspect relevant code before editing it. 5. Give copy/paste commands
appropriate for Windows PowerShell. 6. After edits, provide the exact
tests and verify actual outputs. 7. Update this file's status and
session log before ending. 8. Report the percentage as an estimate and
state what evidence supports it.

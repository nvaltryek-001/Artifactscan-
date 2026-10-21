# Real Photo-to-3D Reconstruction Pipeline

## Objective
Reconstruct a 3D representation from multiple overlapping photographs using a real photogrammetry engine, such as COLMAP where platform and dependency support are verified.

## Expected stages
1. Upload and validate the image set.
2. Create a job record and unique working directory.
3. Check tool availability and version.
4. Extract image features.
5. Match features across views.
6. Estimate camera poses and sparse geometry.
7. Run dense reconstruction where supported.
8. Generate or import a mesh.
9. Generate texture where supported.
10. Validate output files and geometry.
11. Store outputs, logs and metadata.
12. Publish the viewer-ready asset only after validation.

## Output formats
Choose supported formats based on the engine and viewer. OBJ with associated material/texture files, PLY and GLB may be useful. Do not promise a format until conversion and loading are tested. Preserve the original engine outputs when appropriate.

## Validation
Check file existence, file size, parseability, vertex/face counts where applicable, finite coordinates, texture references and bounding box. Reject empty or corrupt outputs. Report if the result is sparse, incomplete or untextured.

## API/job contract
- Submit reconstruction request and receive a job ID.
- Query job state and stage details.
- Retrieve sanitized logs.
- Cancel or retry only when supported.
- Retrieve output metadata and authorized download links.

## Reliability
Run reconstruction outside the web request process. Use timeouts, controlled concurrency, disk-space checks, job isolation and safe cleanup. Capture tool versions and command parameters for reproducibility. Never interpolate untrusted filenames into shell commands.

## Capture guidance
Recommend many overlapping views around the object, stable lighting, sharp images and a textured object surface. Avoid large viewpoint changes, motion blur and reflective/transparent surfaces when possible. Explain that featureless surfaces, changing lighting and insufficient overlap can cause failure.

## Important limitations
Photogrammetry cannot reliably infer unseen surfaces from missing viewpoints. Metric scale requires a known reference, scale marker or another justified calibration method. A generated sample mesh is not a successful reconstruction. The application must distinguish genuine output, demo fixture and unavailable tool.
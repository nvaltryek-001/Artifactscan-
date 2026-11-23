# ArtifactScan AI — Completion Status

Updated: 2026-11-23 · Version 1.0.0

This report lists only what was verified by running it. Unverified items stay open.

## Verified

| Item | Evidence |
|---|---|
| FastAPI backend, SQLite schema with in-place migrations | 26/26 automated tests pass (`pytest -v`) |
| Artifact CRUD, search, review status, audit trail | `tests/test_api.py` |
| Image upload validation, atomic batches, SHA-256 checksums, thumbnails | `tests/test_api.py` |
| Built-in OpenCV Structure-from-Motion engine | 24/24 cameras, 20,898 points, 0.59 px mean reprojection error on the synthetic turntable set; 20/20 cameras, 17,746 points, 0.74 px on the stele set |
| End-to-end reconstruction through the API, output validation, PLY/cameras download | `tests/test_reconstruction.py::test_end_to_end_reconstruction_via_api` |
| Honest failure for featureless input (no fake model) | `test_reconstruction_of_featureless_images_fails_honestly` |
| Classifier "unavailable" contract (no fabricated predictions) | `test_classification_never_fabricates` |
| CSV/JSON exports, printable report (HTML-escaped), BagIt-style package with verified manifest | `tests/test_api.py` |
| All frontend workspaces (overview, collection, record, capture, 3D, classification, analytics, reports, settings) | Exercised in a headless browser; screenshots and demo video in `docs/media/` |

## Implemented but not verified on this machine

- **COLMAP native / Docker runners** — code paths, option-name detection and TXT→`cameras.json` parsing are implemented, but COLMAP was not installed in the verification environment.
- **Classifier inference** — `backend/classifier.py` loads the checkpoint written by `ml/train_classifier.py`; no model was trained here (PyTorch and the iMet download were unavailable).
- **Webcam auto-scanner** — needs a physical camera; logic unchanged from the previous verified version.
- **Docker image** — Dockerfile and CI smoke test provided; the image was not built in the verification environment.

## Still open

1. Run a reconstruction with COLMAP on real photographs of a physical object.
2. Train and evaluate the classifier on the iMet subset; record metrics in `logs/`.
3. Dense reconstruction / meshing and GLB export.
4. Authentication and multi-user isolation before any network deployment.
5. Choose and add a licence.

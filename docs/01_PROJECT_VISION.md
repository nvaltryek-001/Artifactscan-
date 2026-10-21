# ArtifactScan AI — Project Vision and Requirements

## Vision
Build a digital heritage preservation platform that turns photographs of physical artifacts into documented, inspectable 3D assets, with AI-assisted classification and searchable digital records.

## Core capabilities
1. Create an artifact record and capture/upload multiple photographs.
2. Validate images and explain capture problems to users.
3. Run real photogrammetry reconstruction in a background job.
4. Display reconstruction status, logs, errors and downloadable outputs.
5. Preview supported 3D models interactively.
6. Predict artifact classes using a trained and evaluated model.
7. Record confidence, model version and human-review decisions.
8. Store provenance, source, rights, dimensions and preservation metadata.
9. Search, filter, export and report on saved artifacts.
10. Package the project reproducibly for local setup and deployment.

## Users
- Museum and archive staff
- Researchers and students
- Digital heritage teams
- Administrators and reviewers

## Functional requirements
- Persistent artifact and job records
- Multi-image uploads with validation
- Background reconstruction with progress tracking
- Model and image downloads with access controls
- AI predictions with uncertainty and model-version metadata
- Searchable artifact catalogue
- Error handling, retry and job cancellation where supported
- Audit history for important actions

## Non-functional requirements
- Responsive desktop and mobile UI
- Reproducible installation
- Safe file handling and configurable storage
- Clear logs and actionable error messages
- Automated tests and documented limitations
- No fabricated models, predictions, metrics or test results

## MVP acceptance criteria
A user can create an artifact, upload suitable photographs, run an actual reconstruction when required tools are installed, preview a valid output, obtain a real model prediction when a trained model is available, save the record, and retrieve it after restarting the application.

## Explicit boundaries
A single photograph cannot generally recover a complete, accurate unseen 3D object. The system must explain that multi-view photogrammetry requires sufficient overlapping views and suitable image quality. Missing optional AI models must produce an honest unavailable state, not a fake result.
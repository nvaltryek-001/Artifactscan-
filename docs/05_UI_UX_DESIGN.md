# UI/UX Design System and Screen Specifications

## Visual direction
A premium digital-heritage workspace: calm neutral backgrounds, readable typography, restrained accent colour, generous spacing, strong image presentation and clear status indicators. Avoid decorative clutter and misleading AI claims.

## Global navigation
- Dashboard
- Artifact catalogue
- New scan
- Reconstruction jobs
- AI classification
- Reports and exports
- Dataset and model information
- Settings

## Required screens
1. Dashboard: artifact count, job states, recent records and system readiness.
2. New artifact: metadata form and rights/provenance fields.
3. Capture/upload: multi-image selection, thumbnails, validation and guidance.
4. Reconstruction detail: job timeline, logs, output status and retry action.
5. 3D viewer: orbit, zoom, reset camera, model information and supported download formats.
6. Classification: predicted label, calibrated confidence when available, model version and review controls.
7. Catalogue: search, category filters, sort, pagination and empty/error states.
8. Artifact detail: photographs, model, metadata, provenance, history and downloads.
9. Reports: date filters, CSV/JSON export and printable summary.
10. System readiness: dependency availability and setup diagnostics without exposing secrets.

## Design tokens
Define shared CSS variables for background, surface, text, muted text, border, primary, success, warning and danger colours. Maintain consistent spacing, radius, typography and shadows. Check contrast and keyboard focus.

## Components
- App shell and responsive sidebar
- Page header and breadcrumbs
- Metric cards
- Status badge
- Upload dropzone
- Image gallery
- Job timeline
- 3D viewer container
- Confidence/review panel
- Search and filter toolbar
- Data table/list
- Confirmation dialog
- Toasts and accessible form errors
- Loading, empty and error states

## Interaction requirements
- Every visible button must work.
- Provide keyboard navigation, labels and focus indicators.
- Never hide critical errors only in toast messages.
- Warn before destructive actions.
- Do not imply a generated 3D asset or AI result exists before it is available.
- Handle narrow screens, slow requests and no-data states.
- Use realistic sample content only when clearly marked as sample data.
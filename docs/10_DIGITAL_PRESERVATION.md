# Digital Preservation, Metadata and Reports

## Preservation record
A record should connect the physical object description, original photographs, generated 3D assets, reconstruction parameters, classification results, provenance and rights information.

## Recommended metadata groups
- Identity: persistent internal ID, title, alternate title, category
- Description: object type, materials, dimensions and condition if known
- Context: creator, period, origin and collection
- Provenance: source, acquisition/context notes and source record
- Rights: license, attribution, access restrictions and review status
- Capture: date if known, image set, capture notes and operator if provided
- Reconstruction: engine/version, parameters, completion state and output checksum
- Classification: model version, predicted label, scores, confirmed label and reviewer
- Preservation: file format, size, checksum, creation date and validation result
- Change history: meaningful edits, export and review events

## File integrity
Calculate checksums for original uploads and final assets. Preserve originals separately from processed derivatives. Do not overwrite source images during processing. Record format conversions and software versions. Re-check checksums during export or integrity audits.

## Reports and exports
- Single-artifact digital record
- Catalogue summary
- Reconstruction job report
- Classification evaluation report
- Dataset provenance manifest
- Asset inventory and checksum report
- CSV/JSON metadata export
- Printable human-readable report

## Report integrity
Reports must be generated from stored records and real evaluation results. Distinguish missing metadata from verified absence. Include generation time, export version and any incomplete fields. Escape user-provided text before rendering HTML or PDF.

## Preservation boundaries
A checksum proves file integrity, not authenticity or historical correctness. AI labels are not authoritative provenance. Preserve uncertainty, source attribution and human corrections. Long-term archival compliance requires an explicit policy and storage strategy beyond simply keeping files on one disk.
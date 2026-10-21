# Dataset Sourcing, Licensing and Preparation

## Goal
Create a traceable dataset for artifact categories and, if suitable data is available, a separate collection of multi-view images for reconstruction testing.

## Discovery sources to investigate
- Smithsonian Open Access
- The Metropolitan Museum of Art Collection API
- Europeana
- Wikimedia Commons
- OpenHeritage3D

These are discovery leads, not blanket permission to download or redistribute every item. Verify the rights and terms of each asset and each service before use.

## Required manifest fields
- record_id
- title
- object_type/category
- source_name
- source_record_url
- image_url or local relative path
- creator/photographer where available
- rights_statement
- license_identifier and license_url
- attribution_text
- retrieval_date
- checksum
- split: train, validation or test
- notes and review status

## Preparation workflow
1. Define a manageable initial category taxonomy.
2. Collect metadata and approved images through documented methods.
3. Verify each license and attribution requirement.
4. Validate image readability, dimensions and duplicates.
5. Normalize labels and record ambiguous cases.
6. Detect near-duplicates and images of the same physical object.
7. Split data by object/source identity to prevent leakage.
8. Create a reproducible manifest and preprocessing report.
9. Review class imbalance and representation.
10. Version the dataset and record exclusions.

## Reconstruction dataset
A classification image dataset is not automatically suitable for photogrammetry. Multi-view images should depict the same physical object from different viewpoints, with adequate overlap and detail. Record image-set identity, capture conditions and source rights.

## Governance
Never scrape around access restrictions, bypass rate limits or bundle assets without permission. Keep API credentials in environment variables. Preserve attribution and source links. If rights are unclear, exclude the item until reviewed.

## Evaluation discipline
Keep the test set separate from training and model selection. Report class counts, split method, known limitations and the exact dataset version used for each result. Do not invent a dataset size or claim an external source was downloaded until verified.
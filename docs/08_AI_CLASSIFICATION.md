# AI Classification, Training and Evaluation

## Objective
Provide genuine artifact-category predictions with traceable model versions and honest uncertainty.

## Baseline
Start with a simple, reproducible baseline appropriate to the verified dataset. Consider transfer learning with a pretrained vision backbone only when its framework, weights and license are compatible. Compare against a simple baseline rather than assuming a complex model is better.

## Training workflow
1. Validate manifest and labels.
2. Group by object identity before splitting.
3. Create train, validation and untouched test partitions.
4. Record preprocessing, random seeds and dependency versions.
5. Train only on the training partition.
6. Select model settings using validation data.
7. Evaluate once on the held-out test set.
8. Save model weights, label map, configuration and metrics.
9. Register a versioned model artifact.
10. Verify inference against known test examples.

## Metrics
Report accuracy, macro precision, macro recall, macro F1, per-class metrics and confusion matrix where sample sizes allow. Include class support and uncertainty in the evaluation report. Avoid presenting a metric without its dataset split and evaluation context.

## Inference contract
Return predicted class, per-class scores when appropriate, model identifier/version, preprocessing version and status. Treat raw softmax scores as uncalibrated unless calibration has been tested. Support abstention or human review for ambiguous predictions.

## Human review
Store predicted label separately from the confirmed label. Record reviewer correction, timestamp and model version. Do not silently overwrite expert labels with model output.

## Safety and honesty
- No hardcoded predictions pretending to be model inference.
- No invented training data, accuracy or benchmark results.
- If weights or dependencies are missing, return an explicit unavailable state.
- Do not train or evaluate on the same data and report it as generalization performance.
- Record class imbalance, dataset bias and known domain limitations.

## Optional image-language model
Any external vision API must be explicitly configured, called server-side and handled as an optional service. Label its output as AI-assisted metadata, preserve human review, and never expose API keys to the browser.
"""Artifact category classifier (optional).

Inference is enabled only when BOTH are present:
  * PyTorch + torchvision installed (see ml/requirements.txt), and
  * a checkpoint produced by ``ml/train_classifier.py`` in ``models/classifier``.

Otherwise every endpoint reports an explicit "unavailable" state. Predictions
are never hard-coded or simulated.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config

CHECKPOINT = "imet_resnet18_baseline.pth"
_lock = threading.Lock()
_model = None
_meta: dict = {}


def status() -> dict:
    ckpt = config.MODEL_DIR / CHECKPOINT
    try:
        import torch  # noqa: F401
        import torchvision  # noqa: F401

        torch_ok = True
    except Exception:
        torch_ok = False
    metrics_path = config.ROOT / "logs" / "imet_training_metrics.json"
    metrics = None
    if metrics_path.is_file():
        try:
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
            metrics = {k: m.get(k) for k in (
                "dataset", "classes", "train_images", "validation_images",
                "best_validation_macro_f1", "final_epoch_accuracy", "caution")}
        except (OSError, ValueError):
            metrics = None
    if not ckpt.is_file():
        reason = "No trained model checkpoint found. Run ml/download_imet.py then ml/train_classifier.py."
    elif not torch_ok:
        reason = "Checkpoint found but PyTorch/torchvision are not installed (pip install -r ml/requirements.txt)."
    else:
        reason = ""
    return {
        "available": ckpt.is_file() and torch_ok,
        "reason": reason,
        "model_version": f"{CHECKPOINT}" if ckpt.is_file() else None,
        "metrics": metrics,
    }


def _load():
    global _model, _meta
    if _model is not None:
        return _model, _meta
    import torch
    from torch import nn
    from torchvision import models

    ckpt = torch.load(config.MODEL_DIR / CHECKPOINT, map_location="cpu", weights_only=False)
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(ckpt["classes"]))
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    _model, _meta = model, {"classes": ckpt["classes"], "input_size": ckpt.get("input_size", 224)}
    return _model, _meta


def predict(image_paths: list[Path], top_k: int = 5) -> dict:
    """Average softmax scores over all images of one artifact."""
    if not status()["available"]:
        raise RuntimeError(status()["reason"])
    import torch
    from PIL import Image
    from torchvision import transforms

    with _lock:
        model, meta = _load()
        size = meta["input_size"]
        tf = transforms.Compose([
            transforms.Resize((size, size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        batch = []
        for p in image_paths[:16]:
            with Image.open(p) as img:
                batch.append(tf(img.convert("RGB")))
        if not batch:
            raise RuntimeError("Artifact has no images to classify.")
        with torch.no_grad():
            probs = torch.softmax(model(torch.stack(batch)), dim=1).mean(dim=0)
    scores = sorted(
        ({"label": c, "score": round(float(probs[i]), 4)} for i, c in enumerate(meta["classes"])),
        key=lambda s: -s["score"],
    )[:top_k]
    return {"predicted_label": scores[0]["label"], "scores": scores,
            "images_used": len(batch), "calibrated": False}

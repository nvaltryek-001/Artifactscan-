import csv, json, random, time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image
from torchvision import models, transforms
from sklearn.metrics import accuracy_score, f1_score, classification_report

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "imet"
MODEL_DIR = ROOT / "models" / "classifier"
LOG_DIR = ROOT / "logs"
SEED = 42
BATCH_SIZE = 16
EPOCHS = 3
MAX_CLASSES = 8
MIN_TRAIN_PER_CLASS = 20
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

class ArtifactDataset(Dataset):
    def __init__(self, rows, split, class_to_idx, train=False):
        self.rows = [
            r for r in rows
            if r["label_name"] in class_to_idx
            and (DATA / split / r["filename"]).exists()
        ]
        self.split = split
        self.class_to_idx = class_to_idx
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip() if train else transforms.Lambda(lambda x: x),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        path = DATA / self.split / row["filename"]
        with Image.open(path) as img:
            image = self.transform(img.convert("RGB"))
        return image, self.class_to_idx[row["label_name"]]

def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    train_rows = read_csv(DATA / "train_metadata.csv")
    val_rows = read_csv(DATA / "validation_metadata.csv")

    counts = Counter(r["label_name"] for r in train_rows)
    classes = [
        name for name, count in counts.most_common()
        if count >= MIN_TRAIN_PER_CLASS
    ][:MAX_CLASSES]
    if len(classes) < 2:
        raise RuntimeError(
            "Not enough classes have 20 training images. "
            "Download a larger subset before training."
        )

    class_to_idx = {name: i for i, name in enumerate(classes)}
    train_ds = ArtifactDataset(train_rows, "train", class_to_idx, train=True)
    val_ds = ArtifactDataset(val_rows, "validation", class_to_idx)
    if len(train_ds) < 40 or len(val_ds) < 10:
        raise RuntimeError(
            f"Too few usable images: train={len(train_ds)}, validation={len(val_ds)}. "
            "Increase download limits."
        )

    print("Classes:", classes)
    print(f"Usable images: train={len(train_ds)}, validation={len(val_ds)}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    # Use pretrained ImageNet features, then train a new classification head.
    try:
        weights = models.ResNet18_Weights.DEFAULT
        model = models.resnet18(weights=weights)
    except Exception as exc:
        raise RuntimeError(
            "Could not load pretrained ResNet18 weights. Check internet access "
            "and rerun; no random-weight result will be reported as pretrained."
        ) from exc

    for param in model.parameters():
        param.requires_grad = False
    model.fc = nn.Linear(model.fc.in_features, len(classes))
    model = model.to(device)

    train_loader = DataLoader(
        train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0
    )
    val_loader = DataLoader(
        val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0
    )
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.fc.parameters(), lr=1e-3)
    history = []
    best_f1 = -1.0
    best_path = MODEL_DIR / "imet_resnet18_baseline.pth"

    for epoch in range(EPOCHS):
        model.train()
        loss_total, total = 0.0, 0
        started = time.time()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            loss_total += loss.item() * labels.size(0)
            total += labels.size(0)

        model.eval()
        y_true, y_pred = [], []
        with torch.no_grad():
            for images, labels in val_loader:
                logits = model(images.to(device))
                preds = logits.argmax(dim=1).cpu().tolist()
                y_pred.extend(preds)
                y_true.extend(labels.tolist())

        accuracy = accuracy_score(y_true, y_pred)
        macro_f1 = f1_score(
            y_true, y_pred, average="macro", zero_division=0
        )
        result = {
            "epoch": epoch + 1,
            "train_loss": loss_total / max(total, 1),
            "validation_accuracy": accuracy,
            "validation_macro_f1": macro_f1,
            "seconds": round(time.time() - started, 2),
        }
        history.append(result)
        print(json.dumps(result))

        if macro_f1 > best_f1:
            best_f1 = macro_f1
            torch.save({
                "model_state_dict": model.state_dict(),
                "classes": classes,
                "class_to_idx": class_to_idx,
                "architecture": "resnet18",
                "input_size": 224,
                "seed": SEED,
            }, best_path)

    report = classification_report(
        y_true, y_pred, labels=list(range(len(classes))),
        target_names=classes, output_dict=True, zero_division=0
    )
    metrics = {
        "dataset": "timm/imet-open-access",
        "source": "The Metropolitan Museum of Art Open Access",
        "license": "CC0-1.0",
        "task": "single-label classification field; top classes in downloaded subset",
        "seed": SEED,
        "device": str(device),
        "classes": classes,
        "train_images": len(train_ds),
        "validation_images": len(val_ds),
        "epochs": EPOCHS,
        "best_validation_macro_f1": best_f1,
        "final_epoch_accuracy": history[-1]["validation_accuracy"],
        "final_epoch_macro_f1": history[-1]["validation_macro_f1"],
        "history": history,
        "final_epoch_classification_report": report,
        "caution": "Small pilot subset; not a full-dataset or publication-grade result.",
    }
    (LOG_DIR / "imet_training_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (MODEL_DIR / "imet_classes.json").write_text(
        json.dumps(class_to_idx, indent=2), encoding="utf-8"
    )
    print("\nSaved model:", best_path)
    print("Saved metrics:", LOG_DIR / "imet_training_metrics.json")
    print("NOTE: final classification report is from the final epoch; "
          "best checkpoint is selected by validation macro-F1.")

if __name__ == "__main__":
    main()

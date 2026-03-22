"""
Train a crop classifier to boost classification accuracy.

Strategy: YOLO handles detection (det≈0.95), this classifier handles class ID.
1. Extract ground-truth crops from training images
2. Train EfficientNet-B0 classifier on crops
3. At inference: YOLO detects boxes → crop → classify → override class ID

This targets the cls bottleneck (0.82 → 0.88+).
"""
import json, random, argparse
from pathlib import Path
from collections import defaultdict

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image

ROOT = Path(__file__).parent


class CropDataset(Dataset):
    def __init__(self, crops: list, transform=None):
        self.crops = crops  # list of (image_path, bbox, category_id)
        self.transform = transform

    def __len__(self):
        return len(self.crops)

    def __getitem__(self, idx):
        img_path, bbox, cat_id = self.crops[idx]
        img = Image.open(img_path).convert("RGB")
        x, y, w, h = bbox
        # Add 10% padding
        pad_w, pad_h = w * 0.1, h * 0.1
        x1 = max(0, x - pad_w)
        y1 = max(0, y - pad_h)
        x2 = min(img.width, x + w + pad_w)
        y2 = min(img.height, y + h + pad_h)
        crop = img.crop((x1, y1, x2, y2))
        if self.transform:
            crop = self.transform(crop)
        return crop, cat_id


def extract_crops(ann_file, img_dir, split_ids=None):
    with open(ann_file) as f:
        data = json.load(f)

    id_to_info = {img["id"]: img for img in data["images"]}
    crops = []
    for ann in data["annotations"]:
        img_id = ann["image_id"]
        if split_ids and img_id not in split_ids:
            continue
        info = id_to_info.get(img_id)
        if not info:
            continue
        img_path = img_dir / info["file_name"]
        if not img_path.exists():
            continue
        bbox = ann["bbox"]  # [x, y, w, h]
        if bbox[2] < 5 or bbox[3] < 5:
            continue
        crops.append((str(img_path), bbox, ann["category_id"]))
    return crops


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--img-size", type=int, default=128)
    args = parser.parse_args()

    ann_file = ROOT / "annotations.json"
    img_dir = ROOT / "data" / "images"

    with open(ann_file) as f:
        data = json.load(f)

    # Get number of classes
    cat_ids = sorted(set(c["id"] for c in data["categories"]))
    num_classes = max(cat_ids) + 1  # category IDs may not be 0-indexed
    print(f"Categories: {len(cat_ids)}, max_id: {max(cat_ids)}, num_classes: {num_classes}")

    # Split
    existing = {int(p.stem.split("_")[-1]) for p in img_dir.iterdir() if p.suffix == ".jpg"}
    image_ids = sorted(existing & set(img["id"] for img in data["images"]))
    random.seed(42)
    random.shuffle(image_ids)
    split = int(0.9 * len(image_ids))
    train_ids = set(image_ids[:split])
    val_ids = set(image_ids[split:])

    train_crops = extract_crops(ann_file, img_dir, train_ids)
    val_crops = extract_crops(ann_file, img_dir, val_ids)
    print(f"Train crops: {len(train_crops)}, Val crops: {len(val_crops)}")

    # Count class distribution
    class_counts = defaultdict(int)
    for _, _, cat_id in train_crops:
        class_counts[cat_id] += 1
    print(f"Classes with crops: {len(class_counts)}")
    print(f"Min crops per class: {min(class_counts.values())}, Max: {max(class_counts.values())}")

    # Transforms
    train_transform = transforms.Compose([
        transforms.Resize((args.img_size, args.img_size)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
        transforms.RandomRotation(15),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    val_transform = transforms.Compose([
        transforms.Resize((args.img_size, args.img_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    train_ds = CropDataset(train_crops, train_transform)
    val_ds = CropDataset(val_crops, val_transform)
    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch, shuffle=False, num_workers=4, pin_memory=True)

    # Model: EfficientNet-B0
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    # Class weights for imbalanced dataset
    total = sum(class_counts.values())
    weights = torch.ones(num_classes, device=device)
    for cat_id, count in class_counts.items():
        if cat_id < num_classes:
            weights[cat_id] = total / (len(class_counts) * count)
    weights = weights.clamp(max=10.0)

    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_acc = 0
    save_dir = ROOT / "classifier"
    save_dir.mkdir(exist_ok=True)

    for epoch in range(args.epochs):
        # Train
        model.train()
        total_loss = 0
        correct = 0
        total = 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()

        train_acc = correct / total
        scheduler.step()

        # Validate
        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, predicted = outputs.max(1)
                total += labels.size(0)
                correct += predicted.eq(labels).sum().item()

        val_acc = correct / total
        print(f"Epoch {epoch+1}/{args.epochs} | loss={total_loss/len(train_loader):.4f} | train_acc={train_acc:.4f} | val_acc={val_acc:.4f}")

        if val_acc > best_acc:
            best_acc = val_acc
            torch.save({
                "model": model.state_dict(),
                "num_classes": num_classes,
                "img_size": args.img_size,
                "best_acc": best_acc,
            }, save_dir / "best.pt")
            print(f"  -> New best: {best_acc:.4f}")

    print(f"\nBest val accuracy: {best_acc:.4f}")
    print(f"Saved to: {save_dir / 'best.pt'}")


if __name__ == "__main__":
    main()

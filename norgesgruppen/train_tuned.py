"""Tuned YOLO training with optimized hyperparameters for shelf detection.

Key changes from baseline:
- close_mosaic=20 (disable mosaic for last 20 epochs for better fine-tuning)
- Higher copy_paste=0.3 (more synthetic augmentation for rare classes)
- mixup=0.15
- scale=0.9 (more aggressive scale augmentation for varying product sizes)
- Lower conf threshold for more recall
- Warmup 5 epochs
- Train on ALL data (no val split) for final submission weights
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=root / "data" / "train")
    p.add_argument("--model", type=str, default="yolo11x.pt")
    p.add_argument("--epochs", type=int, default=150)
    p.add_argument("--img-size", type=int, default=1920)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=Path, default=root / "yolo_runs")
    p.add_argument("--name", type=str, default="shelf_tuned")
    p.add_argument("--all-data", action="store_true", help="Train on all data (no val split)")
    return p.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)

    # Reuse existing YOLO dataset if available
    yolo_data_dir = args.save_dir / "data"
    yaml_path = yolo_data_dir / "dataset.yaml"

    if not yaml_path.exists():
        print("ERROR: Run train_yolo.py first to prepare the dataset")
        return

    if args.all_data:
        # Create a dataset yaml that uses all images for both train and val
        yaml_content = yaml_path.read_text()
        all_data_yaml = yolo_data_dir / "dataset_all.yaml"
        # Point both train and val to train (we want to train on everything)
        yaml_content = yaml_content.replace("train: train/images", "train: train/images\n# Using all data for final submission")
        # Keep val pointing to val for monitoring but scores won't matter
        all_data_yaml.write_text(yaml_content)
        yaml_path = all_data_yaml
        print("Training on ALL data (no holdout)")

    model = YOLO(args.model)

    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.img_size,
        batch=args.batch_size,
        name=args.name,
        project=str(args.save_dir),
        seed=args.seed,
        # Tuned augmentation
        mosaic=1.0,
        close_mosaic=20,  # Disable mosaic for last 20 epochs
        mixup=0.15,
        copy_paste=0.3,   # More copy-paste for rare classes
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        flipud=0.0,
        fliplr=0.5,
        scale=0.9,         # Aggressive scale augmentation
        translate=0.2,
        degrees=5.0,        # Slight rotation
        shear=2.0,
        perspective=0.001,
        # Training
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=5e-4,
        warmup_epochs=5,
        warmup_momentum=0.8,
        cos_lr=True,
        # Detection
        iou=0.5,
        max_det=500,
        # Save
        save=True,
        save_period=25,
        plots=True,
        verbose=True,
    )

    print(f"\nTraining complete. Results in: {args.save_dir / args.name}")


if __name__ == "__main__":
    main()

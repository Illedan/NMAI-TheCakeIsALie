"""Train YOLOv8 models with tuned hyperparameters for sandbox submission.

Sandbox: ultralytics==8.1.0, PyTorch 2.6.0+cu124, L4 GPU, 420MB zip limit.
YOLO11 is NOT supported — must use YOLOv8 models.

Usage:
  python3 train_v8_tuned.py --model yolov8x.pt --epochs 150 --img-size 1920
  python3 train_v8_tuned.py --model yolov8l.pt --epochs 150 --img-size 1920
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
    p.add_argument("--model", type=str, default="yolov8x.pt")
    p.add_argument("--epochs", type=int, default=150)
    p.add_argument("--img-size", type=int, default=1920)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=Path, default=root / "yolo_runs")
    p.add_argument("--name", type=str, default="v8x_tuned")
    return p.parse_args()


def main():
    args = parse_args()
    random.seed(args.seed)

    yaml_path = args.save_dir / "data" / "dataset.yaml"
    if not yaml_path.exists():
        print("ERROR: Run train_yolo.py first to prepare the dataset")
        return

    model = YOLO(args.model)

    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.img_size,
        batch=args.batch_size,
        name=args.name,
        project=str(args.save_dir),
        seed=args.seed,
        # Tuned augmentation (from Run 9 that got 0.806)
        mosaic=1.0,
        close_mosaic=20,
        mixup=0.15,
        copy_paste=0.3,
        hsv_h=0.02,
        hsv_s=0.7,
        hsv_v=0.4,
        flipud=0.0,
        fliplr=0.5,
        scale=0.9,
        translate=0.2,
        degrees=5.0,
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

    # Report final metrics
    best_pt = args.save_dir / args.name / "weights" / "best.pt"
    if best_pt.exists():
        size_mb = best_pt.stat().st_size / 1e6
        print(f"\nBest model: {best_pt} ({size_mb:.1f} MB)")
        print(f"Fits in 420MB zip: {'YES' if size_mb < 400 else 'NO'}")

    print(f"\nTraining complete.")


if __name__ == "__main__":
    main()

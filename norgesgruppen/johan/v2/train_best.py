"""Train with Johan's best config (exp1_strong_aug) on single GPU."""
import torch
from pathlib import Path

_orig_load = torch.load
torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})

from ultralytics import YOLO
import argparse

ROOT = Path(__file__).parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--name", default="exp1_best")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    model = YOLO("yolov8x.pt")
    model.train(
        data=str(ROOT / "dataset.yaml"),
        epochs=args.epochs,
        imgsz=1280,
        batch=args.batch,
        device=0,
        project=str(ROOT / "runs"),
        name=args.name,
        exist_ok=True,
        seed=args.seed,
        # Johan's best config (exp1_strong_aug)
        copy_paste=0.3,
        mixup=0.3,
        erasing=0.4,
        degrees=10,
        flipud=0.5,
        close_mosaic=20,
        cos_lr=True,
        warmup_epochs=3,
        weight_decay=0.0005,
        patience=0,
        # Standard
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        fliplr=0.5,
        scale=0.5,
        translate=0.1,
        plots=True,
        verbose=True,
    )
    print(f"\nDone! Best model: {ROOT}/runs/{args.name}/weights/best.pt")

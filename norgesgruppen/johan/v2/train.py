"""YOLOv8x training — 4x GPU DDP."""
import argparse, os, torch
from pathlib import Path

_orig_load = torch.load
torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})
os.environ["WANDB_DISABLED"] = "true"

from ultralytics import YOLO
import ultralytics.utils.callbacks.raytune
ultralytics.utils.callbacks.raytune.callbacks = {}

ROOT = Path(__file__).parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="0,1,2,3")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--name", default="yolov8x")
    args = parser.parse_args()

    devices = [int(d) for d in args.device.split(",")]
    model = YOLO("yolov8x.pt")
    model.train(
        data=str(ROOT / "dataset.yaml"),
        epochs=args.epochs,
        imgsz=1280,
        batch=args.batch,
        device=devices if len(devices) > 1 else devices[0],
        project=str(ROOT / "runs"),
        name=args.name,
        exist_ok=True,
        degrees=5.0,
        mixup=0.15,
        copy_paste=0.1,
        close_mosaic=20,
        cos_lr=True,
        warmup_epochs=3,
        weight_decay=0.0005,
        patience=0,
        plots=True,
        verbose=True,
    )

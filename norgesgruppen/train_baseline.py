from __future__ import annotations

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


def enable_trusted_checkpoint_loading() -> None:
    original_load = torch.load

    def patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)

    torch.load = patched_load


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Train a simple YOLO baseline for the NorgesGruppen challenge.")
    parser.add_argument(
        "--data",
        type=Path,
        default=root / "yolo_single_class" / "data.yaml",
    )
    parser.add_argument(
        "--model",
        default="yolov8n.yaml",
        help="Model definition or pretrained weights.",
    )
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--project", type=Path, default=root / "runs")
    parser.add_argument("--name", default="yolov8n_single_class")
    return parser.parse_args()


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    args = parse_args()
    enable_trusted_checkpoint_loading()
    model = YOLO(args.model)
    device = pick_device()

    results = model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=device,
        project=str(args.project),
        name=args.name,
        pretrained=args.model.endswith(".pt"),
        cache=False,
        seed=42,
        deterministic=True,
        verbose=True,
    )

    save_dir = Path(results.save_dir)
    best_weights = save_dir / "weights" / "best.pt"
    last_weights = save_dir / "weights" / "last.pt"
    print(f"Training finished on {device}")
    print(f"Run directory: {save_dir}")
    print(f"Best weights: {best_weights}")
    print(f"Last weights: {last_weights}")


if __name__ == "__main__":
    main()

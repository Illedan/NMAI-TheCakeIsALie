from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "weights" / "best.pt"


def enable_trusted_checkpoint_loading() -> None:
    original_load = torch.load

    def patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)

    torch.load = patched_load


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the NorgesGruppen detection baseline.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.1)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--max-det", type=int, default=300)
    parser.add_argument(
        "--category-id",
        type=int,
        default=0,
        help="Baseline is detection-only, so category_id defaults to 0 for all boxes.",
    )
    return parser.parse_args()


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def iter_images(input_dir: Path) -> list[Path]:
    return sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def parse_image_id(image_path: Path) -> int:
    return int(image_path.stem.split("_")[-1])


def main() -> None:
    args = parse_args()
    if not args.weights.exists():
        raise FileNotFoundError(f"Could not find weights at {args.weights}")

    enable_trusted_checkpoint_loading()
    device = pick_device()
    model = YOLO(str(args.weights))
    predictions: list[dict] = []

    for image_path in iter_images(args.input):
        image_id = parse_image_id(image_path)
        results = model.predict(
            source=str(image_path),
            device=device,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            max_det=args.max_det,
            verbose=False,
        )

        for result in results:
            if result.boxes is None:
                continue
            for index in range(len(result.boxes)):
                x1, y1, x2, y2 = result.boxes.xyxy[index].tolist()
                confidence = max(0.01, float(result.boxes.conf[index].item()))
                predictions.append(
                    {
                        "image_id": image_id,
                        "category_id": args.category_id,
                        "bbox": [
                            round(x1, 1),
                            round(y1, 1),
                            round(x2 - x1, 1),
                            round(y2 - y1, 1),
                        ],
                        "score": round(confidence, 4),
                    }
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions))


if __name__ == "__main__":
    main()

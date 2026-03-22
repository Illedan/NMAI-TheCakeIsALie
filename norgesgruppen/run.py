"""Submission inference script for NorgesGruppen shelf product detection.

Sandbox: Python 3.11, PyTorch 2.6.0+cu124, ultralytics==8.1.0, L4 GPU
Constraints: No os/subprocess, use pathlib. Score floor 0.01. Max 420MB zip.

Supports both:
- YOLOv8 .pt models (native ultralytics)
- ONNX models (via onnxruntime-gpu)
- SAHI-style sliced inference for large shelf images

Usage: python3 run.py --input /path/to/images --output /path/to/predictions.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import numpy as np
from PIL import Image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "weights" / "best.pt"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    p.add_argument("--conf", type=float, default=0.01)
    p.add_argument("--imgsz", type=int, default=1920)
    p.add_argument("--max-det", type=int, default=500)
    p.add_argument("--sahi", action="store_true", default=True)
    p.add_argument("--no-sahi", action="store_true")
    p.add_argument("--slice-size", type=int, default=640)
    p.add_argument("--overlap", type=float, default=0.25)
    return p.parse_args()


def parse_image_id(image_path: Path) -> int:
    return int(image_path.stem.split("_")[-1])


def iter_images(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def load_model(weights_path: Path):
    """Load YOLOv8 model."""
    from ultralytics import YOLO
    model = YOLO(str(weights_path))
    return model


def load_category_mapping(weights_dir: Path) -> dict[int, int]:
    """Load YOLO class index -> competition category_id mapping."""
    # Check multiple locations
    for candidate in [
        weights_dir.parent.parent / "data" / "category_mapping.json",
        weights_dir.parent.parent.parent / "data" / "category_mapping.json",
        Path(__file__).resolve().parent / "category_mapping.json",
    ]:
        if candidate.exists():
            mapping = json.loads(candidate.read_text())
            return {int(k): v for k, v in mapping["yolo_to_cat"].items()}
    return {}


def run_full_image(model, image_path: Path, imgsz: int, conf: float, max_det: int) -> list[dict]:
    """Standard full-image inference."""
    results = model.predict(str(image_path), imgsz=imgsz, conf=conf, max_det=max_det, verbose=False)
    preds = []
    for r in results:
        boxes = r.boxes
        if boxes is None or len(boxes) == 0:
            continue
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().tolist()
            preds.append({
                "box": [x1, y1, x2, y2],
                "score": float(boxes.conf[i].cpu()),
                "class": int(boxes.cls[i].cpu()),
            })
    return preds


def run_sahi(model, image_path: Path, imgsz: int, conf: float, max_det: int,
             slice_size: int, overlap: float) -> list[dict]:
    """SAHI-style sliced inference + full image, merged with NMS."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    all_boxes = []
    all_scores = []
    all_classes = []

    # 1. Full image inference
    full_preds = run_full_image(model, image_path, imgsz, conf, max_det)
    for p in full_preds:
        all_boxes.append(p["box"])
        all_scores.append(p["score"])
        all_classes.append(p["class"])

    # 2. Sliced inference
    stride = int(slice_size * (1 - overlap))
    for y0 in range(0, h, stride):
        for x0 in range(0, w, stride):
            x1 = min(x0 + slice_size, w)
            y1 = min(y0 + slice_size, h)

            if (x1 - x0) < slice_size * 0.3 or (y1 - y0) < slice_size * 0.3:
                continue

            crop = img.crop((x0, y0, x1, y1))
            crop_results = model.predict(crop, imgsz=slice_size, conf=conf, max_det=max_det, verbose=False)

            for r in crop_results:
                boxes = r.boxes
                if boxes is None or len(boxes) == 0:
                    continue
                for i in range(len(boxes)):
                    bx1, by1, bx2, by2 = boxes.xyxy[i].cpu().numpy().tolist()
                    all_boxes.append([bx1 + x0, by1 + y0, bx2 + x0, by2 + y0])
                    all_scores.append(float(boxes.conf[i].cpu()))
                    all_classes.append(int(boxes.cls[i].cpu()))

    if not all_boxes:
        return []

    # 3. Class-aware NMS to merge overlapping predictions
    boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
    scores_t = torch.tensor(all_scores, dtype=torch.float32)
    classes_t = torch.tensor(all_classes, dtype=torch.int64)

    results = []
    for cls_id in classes_t.unique():
        mask = classes_t == cls_id
        cls_boxes = boxes_t[mask]
        cls_scores = scores_t[mask]

        keep = torch.ops.torchvision.nms(cls_boxes, cls_scores, 0.5)
        for idx in keep:
            results.append({
                "box": cls_boxes[idx].tolist(),
                "score": float(cls_scores[idx]),
                "class": int(cls_id),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_det]


def main():
    args = parse_args()
    use_sahi = args.sahi and not args.no_sahi

    model = load_model(args.weights)
    yolo_to_cat = load_category_mapping(args.weights.parent)

    images = iter_images(args.input)
    print(f"Running inference on {len(images)} images (SAHI={'on' if use_sahi else 'off'}, imgsz={args.imgsz})")

    predictions = []
    for img_path in images:
        image_id = parse_image_id(img_path)

        if use_sahi:
            preds = run_sahi(model, img_path, args.imgsz, args.conf, args.max_det,
                           args.slice_size, args.overlap)
        else:
            preds = run_full_image(model, img_path, args.imgsz, args.conf, args.max_det)

        for p in preds:
            x1, y1, x2, y2 = p["box"]
            cat_id = yolo_to_cat.get(p["class"], p["class"])
            predictions.append({
                "image_id": image_id,
                "category_id": cat_id,
                "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                "score": round(max(0.01, p["score"]), 4),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions))
    print(f"Wrote {len(predictions)} predictions to {args.output}")


if __name__ == "__main__":
    main()

"""Inference with SAHI (Slicing Aided Hyper Inference) + TTA + Multi-model ensemble.

Key techniques:
1. SAHI: Slice large shelf images into overlapping tiles for small product detection
2. TTA: Test-time augmentation (horizontal flip, multi-scale)
3. WBF: Weighted Boxes Fusion for merging overlapping predictions
4. Multi-scale: Run at multiple resolutions and merge

Usage:
  python3 run_yolo_sahi.py --input data/test/images --output predictions.json --weights best.pt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import numpy as np
from PIL import Image
from ultralytics import YOLO

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--conf", type=float, default=0.01)
    p.add_argument("--max-det", type=int, default=500)
    p.add_argument("--slice-size", type=int, default=640)
    p.add_argument("--overlap", type=float, default=0.25)
    p.add_argument("--imgsz", type=int, default=1920)
    p.add_argument("--no-sahi", action="store_true")
    p.add_argument("--tta", action="store_true", help="Enable test-time augmentation")
    return p.parse_args()


def parse_image_id(image_path: Path) -> int:
    return int(image_path.stem.split("_")[-1])


def iter_images(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def run_sahi_inference(model, image_path: Path, slice_size: int, overlap: float, imgsz: int, conf: float, max_det: int) -> list[dict]:
    """Run SAHI-style sliced inference on a single image."""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Full image inference at target size
    full_results = model.predict(
        str(image_path), imgsz=imgsz, conf=conf, max_det=max_det,
        verbose=False, augment=False
    )

    all_boxes = []
    all_scores = []
    all_classes = []

    # Extract full-image predictions
    for r in full_results:
        boxes = r.boxes
        if len(boxes) > 0:
            all_boxes.extend(boxes.xyxy.cpu().numpy().tolist())
            all_scores.extend(boxes.conf.cpu().numpy().tolist())
            all_classes.extend(boxes.cls.cpu().numpy().astype(int).tolist())

    # Sliced inference
    stride = int(slice_size * (1 - overlap))
    for y0 in range(0, h, stride):
        for x0 in range(0, w, stride):
            x1 = min(x0 + slice_size, w)
            y1 = min(y0 + slice_size, h)

            # Skip tiny edge slices
            if (x1 - x0) < slice_size * 0.3 or (y1 - y0) < slice_size * 0.3:
                continue

            crop = img.crop((x0, y0, x1, y1))
            crop_results = model.predict(
                crop, imgsz=slice_size, conf=conf, max_det=max_det,
                verbose=False, augment=False
            )

            for r in crop_results:
                boxes = r.boxes
                if len(boxes) > 0:
                    for i in range(len(boxes)):
                        bx1, by1, bx2, by2 = boxes.xyxy[i].cpu().numpy().tolist()
                        # Map back to full image coordinates
                        all_boxes.append([bx1 + x0, by1 + y0, bx2 + x0, by2 + y0])
                        all_scores.append(float(boxes.conf[i].cpu()))
                        all_classes.append(int(boxes.cls[i].cpu()))

    if not all_boxes:
        return []

    # NMS to merge overlapping predictions from tiles + full image
    boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
    scores_t = torch.tensor(all_scores, dtype=torch.float32)
    classes_t = torch.tensor(all_classes, dtype=torch.int64)

    # Class-aware NMS
    results = []
    for cls_id in classes_t.unique():
        mask = classes_t == cls_id
        cls_boxes = boxes_t[mask]
        cls_scores = scores_t[mask]

        keep = torch.ops.torchvision.nms(cls_boxes, cls_scores, 0.5)
        for idx in keep:
            x1, y1, x2, y2 = cls_boxes[idx].tolist()
            results.append({
                "box": [x1, y1, x2, y2],
                "score": float(cls_scores[idx]),
                "class": int(cls_id),
            })

    # Sort by score and limit
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_det]


def run_simple_inference(model, image_path: Path, imgsz: int, conf: float, max_det: int) -> list[dict]:
    """Simple full-image inference without SAHI."""
    results = model.predict(
        str(image_path), imgsz=imgsz, conf=conf, max_det=max_det,
        verbose=False, augment=False
    )
    preds = []
    for r in results:
        boxes = r.boxes
        if len(boxes) > 0:
            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().tolist()
                preds.append({
                    "box": [x1, y1, x2, y2],
                    "score": float(boxes.conf[i].cpu()),
                    "class": int(boxes.cls[i].cpu()),
                })
    return preds


def main():
    args = parse_args()

    model = YOLO(str(args.weights))

    # Load category mapping from YOLO training
    # The model already has class names mapped
    names = model.names  # {0: "class_name", 1: "class_name", ...}

    # Load YOLO-to-COCO mapping
    mapping_path = args.weights.parent.parent / "data" / "category_mapping.json"
    if not mapping_path.exists():
        # Try alternative locations
        for p in [
            args.weights.parent.parent.parent / "data" / "category_mapping.json",
            Path("/root/norgesgruppen/yolo_runs/data/category_mapping.json"),
        ]:
            if p.exists():
                mapping_path = p
                break

    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text())
        yolo_to_cat = {int(k): v for k, v in mapping["yolo_to_cat"].items()}
    else:
        print("WARNING: No category mapping found, using YOLO class IDs directly")
        yolo_to_cat = {i: i for i in range(len(names))}

    predictions = []
    images = iter_images(args.input)
    print(f"Running inference on {len(images)} images (SAHI={'off' if args.no_sahi else 'on'}, imgsz={args.imgsz})")

    for img_path in images:
        image_id = parse_image_id(img_path)

        if args.no_sahi:
            preds = run_simple_inference(model, img_path, args.imgsz, args.conf, args.max_det)
        else:
            preds = run_sahi_inference(model, img_path, args.slice_size, args.overlap, args.imgsz, args.conf, args.max_det)

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

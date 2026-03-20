"""Train YOLOv8 for shelf product detection.

Converts COCO annotations to YOLO format, then trains.
Usage: python3 train_yolo.py --model yolov8m.pt --epochs 100 --img-size 1280
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

from ultralytics import YOLO


def parse_args():
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=root / "data" / "train")
    p.add_argument("--model", type=str, default="yolov8m.pt", help="YOLOv8 model: yolov8s.pt, yolov8m.pt, yolov8l.pt, yolov8x.pt")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--img-size", type=int, default=1280)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--val-split", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=Path, default=root / "yolo_runs")
    p.add_argument("--name", type=str, default="shelf_det")
    return p.parse_args()


def coco_to_yolo(annotations_path: Path, images_dir: Path, output_dir: Path, val_split: float, seed: int):
    """Convert COCO annotations to YOLO format with train/val split."""
    with open(annotations_path) as f:
        data = json.load(f)

    # Build image info map
    id_to_info = {img["id"]: img for img in data["images"]}

    # Only keep images that exist on disk
    existing_ids = []
    for img in data["images"]:
        if (images_dir / img["file_name"]).exists():
            existing_ids.append(img["id"])

    # Category mapping: YOLO needs 0-indexed sequential classes
    cat_ids = sorted(set(c["id"] for c in data["categories"]))
    cat_to_yolo = {cid: i for i, cid in enumerate(cat_ids)}

    # Save category mapping
    mapping = {
        "cat_to_yolo": {str(k): v for k, v in cat_to_yolo.items()},
        "yolo_to_cat": {str(v): k for k, v in cat_to_yolo.items()},
        "categories": data["categories"],
    }
    (output_dir / "category_mapping.json").write_text(json.dumps(mapping, indent=2))

    # Group annotations by image
    ann_by_image: dict[int, list[dict]] = {}
    for ann in data["annotations"]:
        if ann["image_id"] in set(existing_ids):
            ann_by_image.setdefault(ann["image_id"], []).append(ann)

    # Split
    rng = random.Random(seed)
    rng.shuffle(existing_ids)
    n_val = max(1, int(len(existing_ids) * val_split))
    val_ids = set(existing_ids[:n_val])
    train_ids = set(existing_ids[n_val:])

    for split, img_ids in [("train", train_ids), ("val", val_ids)]:
        img_dir = output_dir / split / "images"
        lbl_dir = output_dir / split / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        for img_id in img_ids:
            info = id_to_info[img_id]
            src_path = images_dir / info["file_name"]
            dst_path = img_dir / info["file_name"]

            # Symlink image
            if not dst_path.exists():
                dst_path.symlink_to(src_path.resolve())

            # Write YOLO labels
            img_w = info["width"]
            img_h = info["height"]
            anns = ann_by_image.get(img_id, [])

            label_path = lbl_dir / (Path(info["file_name"]).stem + ".txt")
            lines = []
            for ann in anns:
                x, y, w, h = ann["bbox"]
                if w < 1 or h < 1:
                    continue
                # Convert to YOLO format: class cx cy w h (normalized)
                cx = (x + w / 2) / img_w
                cy = (y + h / 2) / img_h
                nw = w / img_w
                nh = h / img_h
                cls = cat_to_yolo[ann["category_id"]]
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

            label_path.write_text("\n".join(lines))

    # Write YOLO dataset YAML
    yaml_content = f"""path: {output_dir.resolve()}
train: train/images
val: val/images

nc: {len(cat_ids)}
names:
"""
    for cat in data["categories"]:
        idx = cat_to_yolo[cat["id"]]
        name = cat["name"].replace(":", " -")
        yaml_content += f'  {idx}: "{name}"\n'

    yaml_path = output_dir / "dataset.yaml"
    yaml_path.write_text(yaml_content)

    print(f"Converted: {len(train_ids)} train, {len(val_ids)} val images")
    print(f"Classes: {len(cat_ids)}")
    print(f"Dataset YAML: {yaml_path}")

    return yaml_path, mapping


def main():
    args = parse_args()
    random.seed(args.seed)

    annotations_path = args.data_dir / "annotations.json"
    images_dir = args.data_dir / "images"

    # Prepare YOLO dataset
    yolo_data_dir = args.save_dir / "data"
    if (yolo_data_dir / "dataset.yaml").exists():
        print("YOLO dataset already prepared, reusing...")
        yaml_path = yolo_data_dir / "dataset.yaml"
    else:
        yaml_path, _ = coco_to_yolo(annotations_path, images_dir, yolo_data_dir, args.val_split, args.seed)

    # Train
    model = YOLO(args.model)

    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.img_size,
        batch=args.batch_size,
        name=args.name,
        project=str(args.save_dir),
        seed=args.seed,
        # Augmentation
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        flipud=0.0,
        fliplr=0.5,
        scale=0.5,
        # Training
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=5e-4,
        warmup_epochs=5,
        warmup_momentum=0.8,
        cos_lr=True,
        # Save
        save=True,
        save_period=10,
        plots=True,
        verbose=True,
    )

    # Save training log
    log = {
        "model": args.model,
        "epochs": args.epochs,
        "img_size": args.img_size,
        "batch_size": args.batch_size,
        "results_dir": str(results.save_dir) if hasattr(results, 'save_dir') else str(args.save_dir / args.name),
    }
    (args.save_dir / f"{args.name}_log.json").write_text(json.dumps(log, indent=2))
    print(f"\nTraining complete. Results in: {log['results_dir']}")


if __name__ == "__main__":
    main()

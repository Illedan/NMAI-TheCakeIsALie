from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a YOLO dataset from the COCO annotations.")
    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "train" / "annotations.json",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "train" / "images",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "yolo_single_class",
    )
    parser.add_argument(
        "--val-fraction",
        type=float,
        default=0.1,
        help="Fraction of images to use for validation.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--mode",
        choices=("single-class", "multi-class"),
        default="single-class",
        help="Use a single generic product class or preserve category ids.",
    )
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def recreate_symlink(src: Path, dst: Path) -> None:
    ensure_parent(dst)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(src.resolve())


def coco_to_yolo_bbox(bbox: list[float], width: int, height: int) -> tuple[float, float, float, float]:
    x, y, w, h = bbox
    x_center = (x + w / 2.0) / width
    y_center = (y + h / 2.0) / height
    return x_center, y_center, w / width, h / height


def build_yaml_text(dataset_root: Path, class_names: list[str]) -> str:
    return "\n".join(
        [
            f"path: {dataset_root}",
            "train: images/train",
            "val: images/val",
            f"names: {json.dumps(class_names, ensure_ascii=False)}",
            "",
        ]
    )


def main() -> None:
    args = parse_args()
    data = json.loads(args.annotations.read_text())

    images = sorted(data["images"], key=lambda item: item["file_name"])
    categories = sorted(data["categories"], key=lambda item: item["id"])
    annotations_by_image: dict[int, list[dict]] = defaultdict(list)
    for ann in data["annotations"]:
        annotations_by_image[ann["image_id"]].append(ann)

    rng = random.Random(args.seed)
    shuffled = list(images)
    rng.shuffle(shuffled)
    val_size = max(1, int(round(len(shuffled) * args.val_fraction)))
    val_ids = {item["id"] for item in shuffled[:val_size]}

    if args.mode == "single-class":
        class_names = ["product"]
    else:
        class_names = [cat["name"] for cat in categories]

    for split in ("train", "val"):
        (args.output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    for image in images:
        split = "val" if image["id"] in val_ids else "train"
        image_src = args.images_dir / image["file_name"]
        image_dst = args.output_dir / "images" / split / image["file_name"]
        label_dst = args.output_dir / "labels" / split / f"{Path(image['file_name']).stem}.txt"

        recreate_symlink(image_src, image_dst)

        lines: list[str] = []
        for ann in annotations_by_image[image["id"]]:
            class_id = 0 if args.mode == "single-class" else int(ann["category_id"])
            x_center, y_center, bbox_w, bbox_h = coco_to_yolo_bbox(ann["bbox"], image["width"], image["height"])
            lines.append(
                f"{class_id} "
                f"{x_center:.6f} {y_center:.6f} {bbox_w:.6f} {bbox_h:.6f}"
            )

        ensure_parent(label_dst)
        label_dst.write_text("\n".join(lines) + ("\n" if lines else ""))

    data_yaml = args.output_dir / "data.yaml"
    data_yaml.write_text(build_yaml_text(args.output_dir.resolve(), class_names))

    train_count = len(images) - len(val_ids)
    print(f"Prepared {args.mode} YOLO dataset at {args.output_dir}")
    print(f"Train images: {train_count}")
    print(f"Val images: {len(val_ids)}")
    print(f"Classes: {len(class_names)}")
    print(f"Config: {data_yaml}")


if __name__ == "__main__":
    main()

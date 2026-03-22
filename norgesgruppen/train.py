from __future__ import annotations

import argparse
import json
import math
import os
import random
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.utils.data
import torchvision
from torchvision import transforms as T
from torchvision.models.detection import fasterrcnn_resnet50_fpn_v2, FasterRCNN_ResNet50_FPN_V2_Weights
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from PIL import Image
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=root / "data" / "train")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--lr", type=float, default=0.005)
    p.add_argument("--momentum", type=float, default=0.9)
    p.add_argument("--weight-decay", type=float, default=5e-4)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--val-split", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-dir", type=Path, default=root / "checkpoints")
    p.add_argument("--img-size", type=int, default=1024)
    p.add_argument("--resume", type=Path, default=None)
    return p.parse_args()


class ShelfDataset(torch.utils.data.Dataset):
    def __init__(
        self,
        images_dir: Path,
        annotations_path: Path,
        image_ids: list[int],
        cat_to_label: dict[int, int],
        train: bool = True,
        img_size: int = 1024,
    ):
        self.images_dir = images_dir
        self.train = train
        self.img_size = img_size
        self.cat_to_label = cat_to_label

        with open(annotations_path) as f:
            data = json.load(f)

        id_to_info = {img["id"]: img for img in data["images"]}
        # Only keep images that exist on disk
        self.image_infos = []
        for i in image_ids:
            if i in id_to_info:
                info = id_to_info[i]
                if (images_dir / info["file_name"]).exists():
                    self.image_infos.append(info)

        self.ann_by_image: dict[int, list[dict]] = {}
        valid_ids = set(info["id"] for info in self.image_infos)
        for ann in data["annotations"]:
            if ann["image_id"] in valid_ids:
                self.ann_by_image.setdefault(ann["image_id"], []).append(ann)

    def __len__(self) -> int:
        return len(self.image_infos)

    def __getitem__(self, idx: int):
        info = self.image_infos[idx]
        img = Image.open(self.images_dir / info["file_name"]).convert("RGB")
        orig_w, orig_h = img.size
        anns = self.ann_by_image.get(info["id"], [])

        boxes = []
        labels = []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            if w < 1 or h < 1:
                continue
            boxes.append([x, y, x + w, y + h])
            labels.append(self.cat_to_label[ann["category_id"]])

        # Augmentation for training
        if self.train:
            # Random horizontal flip
            if random.random() < 0.5:
                img = T.functional.hflip(img)
                boxes = [[orig_w - x2, y1, orig_w - x1, y2] for x1, y1, x2, y2 in boxes]

            # Random brightness/contrast/saturation
            img = T.functional.adjust_brightness(img, random.uniform(0.8, 1.2))
            img = T.functional.adjust_contrast(img, random.uniform(0.8, 1.2))
            img = T.functional.adjust_saturation(img, random.uniform(0.8, 1.2))

        img_tensor = T.functional.to_tensor(img)

        if len(boxes) == 0:
            boxes_t = torch.zeros((0, 4), dtype=torch.float32)
            labels_t = torch.zeros((0,), dtype=torch.int64)
        else:
            boxes_t = torch.as_tensor(boxes, dtype=torch.float32)
            labels_t = torch.as_tensor(labels, dtype=torch.int64)

            # Clamp boxes
            boxes_t[:, 0].clamp_(min=0, max=orig_w)
            boxes_t[:, 1].clamp_(min=0, max=orig_h)
            boxes_t[:, 2].clamp_(min=0, max=orig_w)
            boxes_t[:, 3].clamp_(min=0, max=orig_h)

            # Filter degenerate boxes
            keep = (boxes_t[:, 2] > boxes_t[:, 0]) & (boxes_t[:, 3] > boxes_t[:, 1])
            boxes_t = boxes_t[keep]
            labels_t = labels_t[keep]

        target = {
            "boxes": boxes_t,
            "labels": labels_t,
            "image_id": info["id"],
        }
        return img_tensor, target


def collate_fn(batch):
    return tuple(zip(*batch))


def build_model(num_classes: int, img_size: int = 1024) -> torch.nn.Module:
    weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
    model = fasterrcnn_resnet50_fpn_v2(weights=weights, min_size=640, max_size=img_size)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model


def build_category_mapping(annotations_path: Path) -> tuple[dict[int, int], dict[int, int]]:
    with open(annotations_path) as f:
        data = json.load(f)
    cat_ids = sorted(set(c["id"] for c in data["categories"]))
    cat_to_label = {cid: i + 1 for i, cid in enumerate(cat_ids)}
    label_to_cat = {v: k for k, v in cat_to_label.items()}
    return cat_to_label, label_to_cat


def split_image_ids(annotations_path: Path, images_dir: Path, val_split: float, seed: int) -> tuple[list[int], list[int]]:
    with open(annotations_path) as f:
        data = json.load(f)
    # Only use images that exist on disk
    all_ids = sorted(
        img["id"] for img in data["images"]
        if (images_dir / img["file_name"]).exists()
    )
    rng = random.Random(seed)
    rng.shuffle(all_ids)
    n_val = max(1, int(len(all_ids) * val_split))
    return all_ids[n_val:], all_ids[:n_val]


@torch.no_grad()
def evaluate(model, val_dataset, device, cat_to_label, label_to_cat, annotations_path: Path, batch_size: int = 4):
    """Run evaluation on validation set. Uses a fresh dataloader to avoid iterator issues."""
    model.eval()

    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False,
        num_workers=2, collate_fn=collate_fn, pin_memory=True,
    )

    predictions = []
    val_image_ids = set()

    for images, targets in val_loader:
        images = [img.to(device) for img in images]
        outputs = model(images)

        for target, output in zip(targets, outputs):
            image_id = int(target["image_id"])
            val_image_ids.add(image_id)
            boxes = output["boxes"].cpu()
            scores = output["scores"].cpu()
            pred_labels = output["labels"].cpu()

            for i in range(len(boxes)):
                if float(scores[i]) < 0.01:
                    continue
                x1, y1, x2, y2 = boxes[i].tolist()
                cat_id = label_to_cat.get(int(pred_labels[i]), 0)
                predictions.append({
                    "image_id": image_id,
                    "category_id": cat_id,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": float(scores[i]),
                })

    if not predictions:
        return 0.0, 0.0, 0.0

    # Detection AP (class-agnostic): all predictions mapped to category 0
    det_preds = [{**p, "category_id": 0} for p in predictions]

    gt_data = json.loads(annotations_path.read_text())
    # Only include val image annotations
    val_anns = [a for a in gt_data["annotations"] if a["image_id"] in val_image_ids]
    val_images = [img for img in gt_data["images"] if img["id"] in val_image_ids]

    det_gt_data = {
        "images": val_images,
        "annotations": [{"id": a["id"], "image_id": a["image_id"], "category_id": 0, "bbox": a["bbox"], "area": a["area"], "iscrowd": a.get("iscrowd", 0)} for a in val_anns],
        "categories": [{"id": 0, "name": "product"}],
    }

    det_ap50 = _run_coco_eval(det_gt_data, det_preds, val_image_ids, "det")

    # Classification AP (per-category)
    cls_gt_data = {
        "images": val_images,
        "annotations": [{"id": a["id"], "image_id": a["image_id"], "category_id": a["category_id"], "bbox": a["bbox"], "area": a["area"], "iscrowd": a.get("iscrowd", 0)} for a in val_anns],
        "categories": gt_data["categories"],
    }
    cls_preds = [p for p in predictions if p["image_id"] in val_image_ids]
    cls_ap50 = _run_coco_eval(cls_gt_data, cls_preds, val_image_ids, "cls")

    final_score = 0.7 * det_ap50 + 0.3 * cls_ap50
    return det_ap50, cls_ap50, final_score


def _run_coco_eval(gt_data: dict, predictions: list, image_ids: set, label: str) -> float:
    """Run COCO evaluation and return AP50, handling numpy quirks."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(gt_data, f)
            gt_path = f.name

        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(predictions)
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.params.imgIds = sorted(image_ids)
        coco_eval.params.iouThrs = [0.5]
        coco_eval.evaluate()
        coco_eval.accumulate()
        try:
            coco_eval.summarize()
        except Exception:
            pass  # numpy 2.x compat issue in pycocotools
        # Extract precision directly from eval results
        # precision shape: [T, R, K, A, M] — T=iouThrs, R=recallThrs, K=cats, A=areas, M=maxDets
        precision = coco_eval.eval['precision']
        if precision is not None and precision.size > 0:
            valid = precision[precision > -1]
            ap50 = float(np.mean(valid)) if valid.size > 0 else 0.0
        else:
            ap50 = 0.0
        os.unlink(gt_path)
        return ap50
    except Exception as e:
        print(f"  [eval] {label}_ap50 error: {e}")
        return 0.0


def main():
    args = parse_args()
    args.save_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    annotations_path = args.data_dir / "annotations.json"
    images_dir = args.data_dir / "images"

    cat_to_label, label_to_cat = build_category_mapping(annotations_path)
    num_classes = len(cat_to_label) + 1

    train_ids, val_ids = split_image_ids(annotations_path, images_dir, args.val_split, args.seed)
    print(f"Train: {len(train_ids)} images, Val: {len(val_ids)} images, Classes: {num_classes - 1}")

    train_ds = ShelfDataset(images_dir, annotations_path, train_ids, cat_to_label, train=True, img_size=args.img_size)
    val_ds = ShelfDataset(images_dir, annotations_path, val_ids, cat_to_label, train=False, img_size=args.img_size)
    print(f"Train dataset: {len(train_ds)} images, Val dataset: {len(val_ds)} images")

    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, collate_fn=collate_fn, pin_memory=True,
    )

    model = build_model(num_classes, args.img_size)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
    # Use cosine with warmup - min_lr = 1e-5 so it never fully dies
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    start_epoch = 0
    best_score = 0.0

    if args.resume and args.resume.exists():
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scheduler.load_state_dict(ckpt["scheduler"])
        start_epoch = ckpt["epoch"] + 1
        best_score = ckpt.get("best_score", 0.0)
        print(f"Resumed from epoch {start_epoch}, best_score={best_score:.4f}")

    mapping_path = args.save_dir / "category_mapping.json"
    mapping_path.write_text(json.dumps({"cat_to_label": cat_to_label, "label_to_cat": {str(k): v for k, v in label_to_cat.items()}}))

    # Training log
    log_path = args.save_dir / "training_log.json"
    training_log: list[dict] = []
    if log_path.exists():
        training_log = json.loads(log_path.read_text())

    # Warmup: linearly ramp up LR for first 3 epochs
    warmup_epochs = 3

    for epoch in range(start_epoch, args.epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0

        for batch_idx, (images, targets) in enumerate(train_loader):
            images = [img.to(device) for img in images]
            targets = [{k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in t.items()} for t in targets]

            # Warmup LR
            if epoch < warmup_epochs:
                warmup_factor = min(1.0, (epoch * len(train_loader) + batch_idx + 1) / (warmup_epochs * len(train_loader)))
                for pg in optimizer.param_groups:
                    pg["lr"] = args.lr * warmup_factor

            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss_dict = model(images, targets)
                losses = sum(loss_dict.values())

            optimizer.zero_grad()
            scaler.scale(losses).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            scaler.step(optimizer)
            scaler.update()

            total_loss += float(losses.detach())
            n_batches += 1

        if epoch >= warmup_epochs:
            scheduler.step()

        avg_loss = total_loss / max(n_batches, 1)
        lr = optimizer.param_groups[0]["lr"]

        det_ap50, cls_ap50, final_score = evaluate(model, val_ds, device, cat_to_label, label_to_cat, annotations_path, args.batch_size)
        print(f"Epoch {epoch+1}/{args.epochs} | loss={avg_loss:.4f} lr={lr:.6f} | det_AP50={det_ap50:.4f} cls_AP50={cls_ap50:.4f} score={final_score:.4f}")

        # Save training log
        training_log.append({
            "epoch": epoch + 1,
            "loss": round(avg_loss, 4),
            "lr": round(lr, 6),
            "det_AP50": round(det_ap50, 4),
            "cls_AP50": round(cls_ap50, 4),
            "score": round(final_score, 4),
            "best_score": round(max(best_score, final_score), 4),
        })
        log_path.write_text(json.dumps(training_log, indent=2))

        ckpt_data = {
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "epoch": epoch,
            "best_score": max(best_score, final_score),
            "num_classes": num_classes,
            "cat_to_label": cat_to_label,
            "label_to_cat": label_to_cat,
        }
        torch.save(ckpt_data, args.save_dir / "last.pt")

        if final_score > best_score:
            best_score = final_score
            torch.save(ckpt_data, args.save_dir / "best.pt")
            print(f"  -> New best: {best_score:.4f}")

    # Save final summary
    summary = {
        "total_epochs": args.epochs,
        "best_score": round(best_score, 4),
        "final_loss": round(avg_loss, 4),
        "num_classes": num_classes - 1,
        "train_images": len(train_ds),
        "val_images": len(val_ds),
        "img_size": args.img_size,
        "batch_size": args.batch_size,
        "lr": args.lr,
    }
    (args.save_dir / "training_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nTraining complete. Best score: {best_score:.4f}")

    ckpt_path = args.save_dir / "best.pt" if (args.save_dir / "best.pt").exists() else args.save_dir / "last.pt"
    print(f"Best checkpoint: {ckpt_path}")

    best_ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    inference_ckpt = {
        "model": best_ckpt["model"],
        "num_classes": best_ckpt["num_classes"],
        "label_to_cat": best_ckpt["label_to_cat"],
    }
    torch.save(inference_ckpt, args.save_dir / "best_inference.pt")
    print(f"Inference checkpoint: {args.save_dir / 'best_inference.pt'}")
    sz = (args.save_dir / "best_inference.pt").stat().st_size / 1e6
    print(f"Inference checkpoint size: {sz:.1f} MB")


if __name__ == "__main__":
    main()

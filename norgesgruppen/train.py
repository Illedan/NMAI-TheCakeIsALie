from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

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
    p.add_argument("--epochs", type=int, default=30)
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
        self.image_infos = [id_to_info[i] for i in image_ids if i in id_to_info]

        self.ann_by_image: dict[int, list[dict]] = {}
        for ann in data["annotations"]:
            if ann["image_id"] in set(image_ids):
                self.ann_by_image.setdefault(ann["image_id"], []).append(ann)

        self.to_tensor = T.ToTensor()

    def __len__(self) -> int:
        return len(self.image_infos)

    def __getitem__(self, idx: int):
        info = self.image_infos[idx]
        img = Image.open(self.images_dir / info["file_name"]).convert("RGB")
        anns = self.ann_by_image.get(info["id"], [])

        boxes = []
        labels = []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            if w < 1 or h < 1:
                continue
            boxes.append([x, y, x + w, y + h])
            labels.append(self.cat_to_label[ann["category_id"]])

        if self.train and random.random() < 0.5:
            img = T.functional.hflip(img)
            w_img = img.width
            boxes = [[w_img - x2, y1, w_img - x1, y2] for x1, y1, x2, y2 in boxes]

        img_tensor = self.to_tensor(img)

        if len(boxes) == 0:
            boxes = torch.zeros((0, 4), dtype=torch.float32)
            labels = torch.zeros((0,), dtype=torch.int64)
        else:
            boxes = torch.as_tensor(boxes, dtype=torch.float32)
            labels = torch.as_tensor(labels, dtype=torch.int64)

        target = {
            "boxes": boxes,
            "labels": labels,
            "image_id": info["id"],
        }
        return img_tensor, target


def collate_fn(batch):
    return tuple(zip(*batch))


def build_model(num_classes: int) -> torch.nn.Module:
    weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
    model = fasterrcnn_resnet50_fpn_v2(weights=weights, min_size=800, max_size=1333)
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


def split_image_ids(annotations_path: Path, val_split: float, seed: int) -> tuple[list[int], list[int]]:
    with open(annotations_path) as f:
        data = json.load(f)
    all_ids = sorted(img["id"] for img in data["images"])
    rng = random.Random(seed)
    rng.shuffle(all_ids)
    n_val = max(1, int(len(all_ids) * val_split))
    return all_ids[n_val:], all_ids[:n_val]


@torch.no_grad()
def evaluate(model, data_loader, device, cat_to_label, label_to_cat, annotations_path: Path):
    model.eval()
    predictions = []

    for images, targets in data_loader:
        images = [img.to(device) for img in images]
        outputs = model(images)

        for target, output in zip(targets, outputs):
            image_id = target["image_id"]
            boxes = output["boxes"].cpu()
            scores = output["scores"].cpu()
            pred_labels = output["labels"].cpu()

            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes[i].tolist()
                cat_id = label_to_cat.get(int(pred_labels[i]), 0)
                predictions.append({
                    "image_id": int(image_id),
                    "category_id": cat_id,
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": max(0.01, float(scores[i])),
                })

    if not predictions:
        return 0.0, 0.0, 0.0

    coco_gt = COCO(str(annotations_path))

    det_preds = []
    for p in predictions:
        det_preds.append({**p, "category_id": 0})

    gt_data = json.loads(annotations_path.read_text())
    det_gt_data = {
        "images": gt_data["images"],
        "annotations": [{**a, "category_id": 0} for a in gt_data["annotations"]],
        "categories": [{"id": 0, "name": "product"}],
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(det_gt_data, f)
        det_gt_path = f.name
    det_coco_gt = COCO(det_gt_path)

    val_image_ids = set(t["image_id"] for _, targets in data_loader for t in targets)
    det_preds_val = [p for p in det_preds if p["image_id"] in val_image_ids]
    cls_preds_val = [p for p in predictions if p["image_id"] in val_image_ids]

    try:
        det_coco_dt = det_coco_gt.loadRes(det_preds_val)
        det_eval = COCOeval(det_coco_gt, det_coco_dt, "bbox")
        det_eval.params.imgIds = list(val_image_ids)
        det_eval.params.iouThrs = [0.5]
        det_eval.evaluate()
        det_eval.accumulate()
        det_eval.summarize()
        det_ap50 = det_eval.stats[0]
    except Exception:
        det_ap50 = 0.0

    try:
        cls_coco_dt = coco_gt.loadRes(cls_preds_val)
        cls_eval = COCOeval(coco_gt, cls_coco_dt, "bbox")
        cls_eval.params.imgIds = list(val_image_ids)
        cls_eval.params.iouThrs = [0.5]
        cls_eval.evaluate()
        cls_eval.accumulate()
        cls_eval.summarize()
        cls_ap50 = cls_eval.stats[0]
    except Exception:
        cls_ap50 = 0.0

    final_score = 0.7 * det_ap50 + 0.3 * cls_ap50
    return det_ap50, cls_ap50, final_score


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

    train_ids, val_ids = split_image_ids(annotations_path, args.val_split, args.seed)
    print(f"Train: {len(train_ids)} images, Val: {len(val_ids)} images, Classes: {num_classes - 1}")

    train_ds = ShelfDataset(images_dir, annotations_path, train_ids, cat_to_label, train=True, img_size=args.img_size)
    val_ds = ShelfDataset(images_dir, annotations_path, val_ids, cat_to_label, train=False, img_size=args.img_size)

    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, collate_fn=collate_fn, pin_memory=True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, collate_fn=collate_fn, pin_memory=True,
    )

    model = build_model(num_classes)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(params, lr=args.lr, momentum=args.momentum, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
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

    for epoch in range(start_epoch, args.epochs):
        model.train()
        total_loss = 0.0
        n_batches = 0

        for images, targets in train_loader:
            images = [img.to(device) for img in images]
            targets = [{k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in t.items()} for t in targets]

            with torch.amp.autocast("cuda", enabled=device.type == "cuda"):
                loss_dict = model(images, targets)
                losses = sum(loss_dict.values())

            optimizer.zero_grad()
            scaler.scale(losses).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            scaler.step(optimizer)
            scaler.update()

            total_loss += float(losses)
            n_batches += 1

        scheduler.step()
        avg_loss = total_loss / max(n_batches, 1)
        lr = optimizer.param_groups[0]["lr"]

        det_ap50, cls_ap50, final_score = evaluate(model, val_loader, device, cat_to_label, label_to_cat, annotations_path)
        print(f"Epoch {epoch+1}/{args.epochs} | loss={avg_loss:.4f} lr={lr:.6f} | det_AP50={det_ap50:.4f} cls_AP50={cls_ap50:.4f} score={final_score:.4f}")

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

    print(f"\nTraining complete. Best score: {best_score:.4f}")
    print(f"Best checkpoint: {args.save_dir / 'best.pt'}")

    best_ckpt = torch.load(args.save_dir / "best.pt", map_location="cpu", weights_only=False)
    inference_ckpt = {
        "model": best_ckpt["model"],
        "num_classes": best_ckpt["num_classes"],
        "label_to_cat": best_ckpt["label_to_cat"],
    }
    torch.save(inference_ckpt, args.save_dir / "best_inference.pt")
    print(f"Inference checkpoint: {args.save_dir / 'best_inference.pt'}")


if __name__ == "__main__":
    main()

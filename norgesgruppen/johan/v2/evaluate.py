"""Evaluate a model on the val set using our competition metric."""
import argparse, contextlib, io, json, os, tempfile
import numpy as np, torch
from pathlib import Path
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

_orig_load = torch.load
torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})

from ultralytics import YOLO

ROOT = Path(__file__).parent

def evaluate(model_path, device="cuda:0"):
    with open(ROOT / "annotations.json") as f:
        gt_data = json.load(f)

    val_dir = ROOT / "dataset/val/images"
    val_ids = {int(p.stem.split("_")[-1]) for p in val_dir.iterdir()
               if p.suffix.lower() in (".jpg", ".jpeg", ".png")}

    model = YOLO(model_path)
    preds = []
    for img in sorted(val_dir.iterdir()):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        image_id = int(img.stem.split("_")[-1])
        for r in model(str(img), device=device, imgsz=1280, conf=0.001, max_det=1500, verbose=False):
            if r.boxes is None:
                continue
            for i in range(len(r.boxes)):
                x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                preds.append({
                    "image_id": image_id,
                    "category_id": int(r.boxes.cls[i].item()),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                    "score": round(float(r.boxes.conf[i].item()), 4),
                })

    if not preds:
        print("No predictions"); return

    gt_val = {
        "images": [i for i in gt_data["images"] if i["id"] in val_ids],
        "annotations": [a for a in gt_data["annotations"] if a["image_id"] in val_ids],
        "categories": gt_data["categories"],
    }
    with contextlib.redirect_stdout(io.StringIO()):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(gt_val, f); gt_path = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(preds, f); pred_path = f.name
        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(pred_path)
        maps = []
        for use_cats in range(2):
            ev = COCOeval(coco_gt, coco_dt, "bbox")
            ev.params.useCats = use_cats
            ev.params.iouThrs = [0.5]
            ev.params.maxDets = [1, 10, 1500]
            ev.evaluate(); ev.accumulate()
            prec = ev.eval["precision"][0, :, :, 0, 2]
            maps.append(np.mean(prec[prec > -1]))
    os.unlink(gt_path); os.unlink(pred_path)
    det, cls = maps
    combined = det * 0.7 + cls * 0.3
    print(f"det={det:.4f}  cls={cls:.4f}  combined={combined:.4f}  ({len(preds)} preds)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="Path to .pt or .onnx")
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    evaluate(args.model, args.device)

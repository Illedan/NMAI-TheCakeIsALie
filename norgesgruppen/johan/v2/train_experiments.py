"""Run multiple training experiments to find the best config.
Focus on boosting classification (cls is the bottleneck).
"""
import torch, json, time, contextlib, io, tempfile, os
import numpy as np
from pathlib import Path
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

_orig_load = torch.load
torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})

from ultralytics import YOLO

ROOT = Path(__file__).parent

def evaluate_model(model_path, conf=0.001, augment=True):
    """Evaluate with proper competition metric."""
    with open(ROOT / "annotations.json") as f:
        gt_data = json.load(f)
    val_dir = ROOT / "dataset/val/images"
    val_ids = {int(p.stem.split("_")[-1]) for p in val_dir.iterdir() if p.suffix == ".jpg"}

    model = YOLO(str(model_path))
    preds = []
    for img in sorted(val_dir.iterdir()):
        if img.suffix != ".jpg": continue
        image_id = int(img.stem.split("_")[-1])
        for r in model(str(img), device="cuda:0", imgsz=1280, conf=conf, max_det=1500, verbose=False, augment=augment):
            if r.boxes is None: continue
            for i in range(len(r.boxes)):
                x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                preds.append({"image_id": image_id, "category_id": int(r.boxes.cls[i].item()),
                    "bbox": [round(x1,1), round(y1,1), round(x2-x1,1), round(y2-y1,1)],
                    "score": round(float(r.boxes.conf[i].item()), 4)})

    gt_val = {"images": [i for i in gt_data["images"] if i["id"] in val_ids],
        "annotations": [a for a in gt_data["annotations"] if a["image_id"] in val_ids],
        "categories": gt_data["categories"]}

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
    return maps[0], maps[1]  # det, cls


EXPERIMENTS = [
    # Exp A: Higher mixup (boost cls diversity)
    {"name": "expA_mixup05", "config": {"mixup": 0.5, "copy_paste": 0.3, "erasing": 0.4, "degrees": 10, "flipud": 0.5}},
    # Exp B: Freeze backbone longer (focus cls head training)
    {"name": "expB_freeze10", "config": {"mixup": 0.3, "copy_paste": 0.3, "erasing": 0.4, "degrees": 10, "flipud": 0.5}, "freeze": 10},
    # Exp C: More epochs, lower LR
    {"name": "expC_200ep", "config": {"mixup": 0.3, "copy_paste": 0.3, "erasing": 0.4, "degrees": 10, "flipud": 0.5}, "epochs": 200},
]


def run_experiment(exp):
    name = exp["name"]
    config = exp.get("config", {})
    epochs = exp.get("epochs", 150)
    freeze = exp.get("freeze", 0)

    print(f"\n{'='*50}")
    print(f"EXPERIMENT: {name}")
    print(f"{'='*50}")

    model = YOLO("yolov8x.pt")
    start = time.time()

    model.train(
        data=str(ROOT / "dataset.yaml"),
        epochs=epochs,
        imgsz=1280,
        batch=8,
        device=0,
        project=str(ROOT / "runs"),
        name=name,
        exist_ok=True,
        seed=42,
        close_mosaic=20,
        cos_lr=True,
        warmup_epochs=3,
        weight_decay=0.0005,
        patience=0,
        freeze=freeze,
        plots=False,
        verbose=True,
        **config,
    )
    duration = time.time() - start

    # Evaluate
    best_pt = ROOT / "runs" / name / "weights" / "best.pt"
    det, cls = evaluate_model(best_pt)
    combined = det * 0.7 + cls * 0.3

    result = {"name": name, "det": round(det, 4), "cls": round(cls, 4),
              "combined": round(combined, 4), "duration_min": round(duration/60, 1)}
    print(f"\n>>> {name}: det={det:.4f} cls={cls:.4f} combined={combined:.4f} ({duration/60:.0f}min)")

    # With TTA
    det_tta, cls_tta = evaluate_model(best_pt, conf=0.001, augment=True)
    combined_tta = det_tta * 0.7 + cls_tta * 0.3
    result["det_tta"] = round(det_tta, 4)
    result["cls_tta"] = round(cls_tta, 4)
    result["combined_tta"] = round(combined_tta, 4)
    print(f"    +TTA: det={det_tta:.4f} cls={cls_tta:.4f} combined={combined_tta:.4f}")

    # Save log
    log_path = ROOT / "experiment_results.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    log.append(result)
    log_path.write_text(json.dumps(log, indent=2))

    # Clean epoch checkpoints
    for f in (ROOT / "runs" / name / "weights").glob("epoch*.pt"):
        f.unlink()

    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", help="Run specific experiment by name")
    args = parser.parse_args()

    log_path = ROOT / "experiment_results.json"
    completed = set()
    if log_path.exists():
        completed = {e["name"] for e in json.loads(log_path.read_text())}

    for exp in EXPERIMENTS:
        if args.exp and exp["name"] != args.exp:
            continue
        if exp["name"] in completed:
            print(f"Skipping {exp['name']} (already done)")
            continue
        run_experiment(exp)

    # Print summary
    if log_path.exists():
        results = json.loads(log_path.read_text())
        print(f"\n{'='*60}")
        print(f"{'Name':<20} {'det':>6} {'cls':>6} {'comb':>6} | {'det_t':>6} {'cls_t':>6} {'comb_t':>6}")
        print("-" * 60)
        print(f"{'baseline(exp1)':20} {'0.9163':>6} {'0.7317':>6} {'0.8610':>6} | {'0.9153':>6} {'0.7522':>6} {'0.8664':>6}")
        for r in results:
            print(f"{r['name']:<20} {r['det']:>6.4f} {r['cls']:>6.4f} {r['combined']:>6.4f} | {r.get('det_tta',0):>6.4f} {r.get('cls_tta',0):>6.4f} {r.get('combined_tta',0):>6.4f}")

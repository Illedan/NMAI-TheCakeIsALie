import torch, json, shutil, contextlib, io, numpy as np
from pathlib import Path
_orig_load = torch.load
torch.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, "weights_only": False})
import os
os.environ["WANDB_DISABLED"] = "true"
from ultralytics import YOLO
import ultralytics.utils.callbacks.raytune
ultralytics.utils.callbacks.raytune.callbacks = {}
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

# Load val ground truth once
VAL_IMAGE_IDS = set()
with open("annotations.json") as f:
    gt_data = json.load(f)
val_dir = Path("dataset/val/images")
for p in val_dir.iterdir():
    if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
        VAL_IMAGE_IDS.add(int(p.stem.split("_")[-1]))

EVAL_EVERY = 10

def eval_val(trainer):
    epoch = trainer.epoch + 1
    if epoch % EVAL_EVERY != 0 and epoch != trainer.epochs:
        return

    # Save checkpoint
    ckpt_dir = Path(trainer.save_dir) / "checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    shutil.copy(trainer.last, ckpt_dir / f"epoch{epoch}.pt")

    # Run inference on val images
    model = YOLO(str(trainer.best if (trainer.best and Path(trainer.best).exists()) else trainer.last))
    predictions = []
    for img in sorted(val_dir.iterdir()):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        image_id = int(img.stem.split("_")[-1])
        results = model(str(img), device="cuda", verbose=False)
        for r in results:
            if r.boxes is None:
                continue
            for i in range(len(r.boxes)):
                x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                predictions.append({
                    "image_id": image_id,
                    "category_id": int(r.boxes.cls[i].item()),
                    "bbox": [round(x1, 1), round(y1, 1), round(x2 - x1, 1), round(y2 - y1, 1)],
                    "score": round(float(r.boxes.conf[i].item()), 3),
                })

    if not predictions:
        print(f"\n[Epoch {epoch}] No predictions on val set")
        return

    # Filter GT to val images only
    gt_val = {
        "images": [img for img in gt_data["images"] if img["id"] in VAL_IMAGE_IDS],
        "annotations": [a for a in gt_data["annotations"] if a["image_id"] in VAL_IMAGE_IDS],
        "categories": gt_data["categories"],
    }

    with contextlib.redirect_stdout(io.StringIO()):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(gt_val, f)
            gt_path = f.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(predictions, f)
            pred_path = f.name

        coco_gt = COCO(gt_path)
        coco_dt = coco_gt.loadRes(pred_path)
        coco_eval = COCOeval(coco_gt, coco_dt, "bbox")
        coco_eval.params.useCats = 0
        coco_eval.params.iouThrs = [0.5]
        coco_eval.evaluate()
        coco_eval.accumulate()

    precision = coco_eval.eval["precision"][0, :, 0, 0, 2]
    mAP = np.mean(precision[precision > -1])
    print(f"\n[Epoch {epoch}] val detection mAP@0.5: {mAP:.4f} ({len(predictions)} preds)")
    os.unlink(gt_path)
    os.unlink(pred_path)

model = YOLO("yolov8s.pt")
model.add_callback("on_fit_epoch_end", eval_val)
model.train(
    data="dataset.yaml",
    epochs=100,
    imgsz=1280,
    batch=4,
    device="cuda",
    project="runs",
    name="yolov8s_1280",
)

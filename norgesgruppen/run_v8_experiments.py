"""Run YOLOv8x experiments with parameter variations.
All sandbox-compatible (ultralytics==8.1.0).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from ultralytics import YOLO

SAVE_DIR = Path("/root/norgesgruppen/yolo_runs")
DATA_YAML = SAVE_DIR / "data" / "dataset.yaml"
LOG_PATH = Path("/root/norgesgruppen/v8_experiments_log.json")

# Best config (Run 10: mAP50=0.811)
BASE = dict(
    epochs=150, imgsz=1920, batch=2, mosaic=1.0, close_mosaic=20,
    mixup=0.15, copy_paste=0.3, hsv_h=0.02, hsv_s=0.7, hsv_v=0.4,
    flipud=0.0, fliplr=0.5, scale=0.9, translate=0.2, degrees=5.0,
    shear=2.0, perspective=0.001, optimizer="SGD", lr0=0.01, lrf=0.01,
    momentum=0.937, weight_decay=5e-4, warmup_epochs=5,
    warmup_momentum=0.8, cos_lr=True, iou=0.5, max_det=500,
)

EXPERIMENTS = [
    # Exp 1: More copy_paste for rare classes
    {"name": "v8x_cp05", "model": "yolov8x.pt", "changes": {"copy_paste": 0.5}},
    # Exp 2: Longer close_mosaic (30 clean epochs)
    {"name": "v8x_cm30", "model": "yolov8x.pt", "changes": {"close_mosaic": 30}},
    # Exp 3: Fine-tune from best with low LR
    {"name": "v8x_finetune", "model": str(SAVE_DIR / "v8x_tuned/weights/best.pt"),
     "changes": {"epochs": 50, "lr0": 0.001, "close_mosaic": 10, "mosaic": 0.5, "copy_paste": 0.1, "warmup_epochs": 2}},
    # Exp 4: Higher resolution 2048 with smaller batch
    {"name": "v8x_2048", "model": "yolov8x.pt", "changes": {"imgsz": 2048, "batch": 1, "epochs": 100}},
    # Exp 5: More augmentation diversity
    {"name": "v8x_augplus", "model": "yolov8x.pt",
     "changes": {"degrees": 10.0, "shear": 5.0, "perspective": 0.002, "mixup": 0.2, "copy_paste": 0.4, "scale": 1.0}},
]


def load_log():
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return []


def save_log(log):
    LOG_PATH.write_text(json.dumps(log, indent=2))
    # Also copy to repo
    repo_log = Path("/workspace/NMAI-TheCakeIsALie/norgesgruppen/v8_experiments_log.json")
    repo_log.write_text(json.dumps(log, indent=2))


def run_experiment(exp):
    name = exp["name"]
    model_path = exp["model"]
    config = {**BASE, **exp["changes"]}

    print(f"\n{'='*60}")
    print(f"EXPERIMENT: {name}")
    print(f"Changes: {exp['changes']}")
    print(f"{'='*60}\n")

    model = YOLO(model_path)
    start = time.time()

    model.train(
        data=str(DATA_YAML), name=name, project=str(SAVE_DIR), seed=42,
        save=True, save_period=50, plots=True, verbose=True, **config,
    )

    duration = time.time() - start
    best_pt = SAVE_DIR / name / "weights" / "best.pt"

    metrics = {"mAP50": 0, "mAP50_95": 0, "precision": 0, "recall": 0}
    model_size = 0

    if best_pt.exists():
        eval_model = YOLO(str(best_pt))
        val = eval_model.val(data=str(DATA_YAML), imgsz=config.get("imgsz", 1920), verbose=False)
        metrics = {
            "mAP50": round(float(val.box.map50), 4),
            "mAP50_95": round(float(val.box.map), 4),
            "precision": round(float(val.box.mp), 4),
            "recall": round(float(val.box.mr), 4),
        }
        model_size = round(best_pt.stat().st_size / 1e6, 1)

        # Clean epoch checkpoints
        for f in (SAVE_DIR / name / "weights").glob("epoch*.pt"):
            f.unlink()

    result = {
        "name": name,
        "changes": exp["changes"],
        "metrics": metrics,
        "duration_min": round(duration / 60, 1),
        "model_size_mb": model_size,
    }

    print(f"\n>>> {name}: mAP50={metrics['mAP50']}, P={metrics['precision']}, R={metrics['recall']} ({result['duration_min']}min, {model_size}MB)")
    return result


def main():
    log = load_log()
    completed = {e["name"] for e in log}

    for exp in EXPERIMENTS:
        if exp["name"] in completed:
            print(f"Skipping {exp['name']} (already done)")
            continue

        result = run_experiment(exp)
        log.append(result)
        save_log(log)

    print(f"\n{'='*60}")
    print(f"{'Name':<20} {'mAP50':>8} {'P':>8} {'R':>8} {'mAP95':>8} {'Size':>6} {'Time':>6}")
    print("-" * 65)
    print(f"{'baseline(Run10)':<20} {'0.8110':>8} {'0.792':>8} {'0.760':>8} {'0.516':>8} {'132':>6} {'-':>6}")
    for e in log:
        m = e["metrics"]
        print(f"{e['name']:<20} {m['mAP50']:>8.4f} {m['precision']:>8.3f} {m['recall']:>8.3f} {m['mAP50_95']:>8.4f} {e['model_size_mb']:>6} {e['duration_min']:>5.0f}m")


if __name__ == "__main__":
    main()

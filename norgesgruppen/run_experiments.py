"""Run a series of hyperparameter experiments and log results.

Each experiment varies one or two parameters from the best config (Run 9).
Results are written to experiments_log.json for comparison.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from ultralytics import YOLO

SAVE_DIR = Path("/root/norgesgruppen/yolo_runs")
DATA_YAML = SAVE_DIR / "data" / "dataset.yaml"
LOG_PATH = Path("/root/norgesgruppen/experiments_log.json")

# Best config from Run 9 (mAP50=0.806)
BEST_CONFIG = {
    "model": "yolo11x.pt",
    "epochs": 150,
    "imgsz": 1920,
    "batch": 2,
    "mosaic": 1.0,
    "close_mosaic": 20,
    "mixup": 0.15,
    "copy_paste": 0.3,
    "hsv_h": 0.02,
    "hsv_s": 0.7,
    "hsv_v": 0.4,
    "flipud": 0.0,
    "fliplr": 0.5,
    "scale": 0.9,
    "translate": 0.2,
    "degrees": 5.0,
    "shear": 2.0,
    "perspective": 0.001,
    "optimizer": "SGD",
    "lr0": 0.01,
    "lrf": 0.01,
    "momentum": 0.937,
    "weight_decay": 5e-4,
    "warmup_epochs": 5,
    "warmup_momentum": 0.8,
    "cos_lr": True,
    "iou": 0.5,
    "max_det": 500,
}

EXPERIMENTS = [
    # Exp 1: More copy_paste (help rare classes more)
    {"name": "exp_copypaste05", "changes": {"copy_paste": 0.5}},
    # Exp 2: Even more aggressive scale
    {"name": "exp_scale1", "changes": {"scale": 1.0, "translate": 0.3}},
    # Exp 3: Higher close_mosaic (more clean fine-tuning epochs)
    {"name": "exp_closemosaic30", "changes": {"close_mosaic": 30}},
    # Exp 4: Lower LR for longer training
    {"name": "exp_lowlr", "changes": {"lr0": 0.005, "epochs": 200}},
    # Exp 5: AdamW optimizer instead of SGD
    {"name": "exp_adamw", "changes": {"optimizer": "AdamW", "lr0": 0.001, "weight_decay": 0.01}},
    # Exp 6: More rotation/perspective for shelf angles
    {"name": "exp_rotation", "changes": {"degrees": 10.0, "shear": 5.0, "perspective": 0.002}},
    # Exp 7: Resume from best with lower LR fine-tuning
    {"name": "exp_finetune", "changes": {
        "model": str(SAVE_DIR / "shelf_tuned_11x" / "weights" / "best.pt"),
        "epochs": 50, "lr0": 0.001, "close_mosaic": 10, "mosaic": 0.5, "copy_paste": 0.1,
    }},
]


def load_log() -> list[dict]:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return []


def save_log(log: list[dict]):
    LOG_PATH.write_text(json.dumps(log, indent=2))


def run_experiment(exp: dict) -> dict:
    name = exp["name"]
    changes = exp["changes"]

    config = {**BEST_CONFIG, **changes}
    model_path = config.pop("model")

    print(f"\n{'='*60}")
    print(f"EXPERIMENT: {name}")
    print(f"Changes: {changes}")
    print(f"{'='*60}\n")

    model = YOLO(model_path)
    start_time = time.time()

    results = model.train(
        data=str(DATA_YAML),
        name=name,
        project=str(SAVE_DIR),
        seed=42,
        save=True,
        save_period=50,
        plots=True,
        verbose=True,
        **config,
    )

    duration = time.time() - start_time

    # Get best metrics
    best_pt = SAVE_DIR / name / "weights" / "best.pt"
    if best_pt.exists():
        eval_model = YOLO(str(best_pt))
        val_results = eval_model.val(data=str(DATA_YAML), imgsz=config.get("imgsz", 1920), verbose=False)
        metrics = {
            "mAP50": round(float(val_results.box.map50), 4),
            "mAP50_95": round(float(val_results.box.map), 4),
            "precision": round(float(val_results.box.mp), 4),
            "recall": round(float(val_results.box.mr), 4),
        }
    else:
        metrics = {"mAP50": 0, "mAP50_95": 0, "precision": 0, "recall": 0}

    result = {
        "name": name,
        "changes": changes,
        "metrics": metrics,
        "duration_min": round(duration / 60, 1),
        "model_size_mb": round(best_pt.stat().st_size / 1e6, 1) if best_pt.exists() else 0,
    }

    print(f"\nRESULT: {name} -> mAP50={metrics['mAP50']}, duration={result['duration_min']}min")

    # Clean epoch checkpoints
    for f in (SAVE_DIR / name / "weights").glob("epoch*.pt"):
        f.unlink()

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

        # Copy log to repo
        repo_log = Path("/workspace/NMAI-TheCakeIsALie/norgesgruppen/experiments_log.json")
        repo_log.write_text(json.dumps(log, indent=2))

    # Print summary
    print(f"\n{'='*60}")
    print("EXPERIMENT SUMMARY")
    print(f"{'='*60}")
    print(f"{'Name':<25} {'mAP50':>8} {'mAP50-95':>10} {'Time':>8}")
    print("-" * 55)
    baseline = {"name": "Run9_baseline", "metrics": {"mAP50": 0.806, "mAP50_95": 0.519}, "duration_min": 0}
    for e in [baseline] + log:
        m = e["metrics"]
        print(f"{e['name']:<25} {m['mAP50']:>8.4f} {m['mAP50_95']:>10.4f} {e.get('duration_min',0):>6.1f}m")


if __name__ == "__main__":
    main()

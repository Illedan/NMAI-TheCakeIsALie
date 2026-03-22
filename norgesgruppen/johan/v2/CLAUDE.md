# NorgesGruppen Grocery Product Detection

## Task
Detect and classify products on grocery shelf images. 210 training images, ~20k annotations, 356 product categories.

## Scoring
`combined = 0.7 * detection_mAP@0.5 + 0.3 * classification_mAP@0.5`
- Detection: category-agnostic bounding box matching (IoU ≥ 0.5)
- Classification: category-aware (IoU ≥ 0.5 AND correct category_id)

## Current best
- **0.9126** local val (exp1_strong_aug + TTA + conf=0.001): det=0.9528, cls=0.8189
- **0.8888** on actual eval server (old submission — pre-bugfix, with FP16 ONNX)
- Bottleneck has SHIFTED: det≈0.95 is strong, **cls≈0.78–0.81 is now the bottleneck**

## Critical evaluator bug (fixed)
Previous evaluate.py had two bugs that made every score wrong:
1. **maxDets capped at 100** (pycocotools default) — fix: `ev.params.maxDets = [1, 10, 1500]`
2. **Only category 0 evaluated for cls** — fix: `prec = ev.eval["precision"][0, :, :, 0, 2]`

Impact: buggy scores showed det≈0.825, cls≈1.000 (fake perfect). Fixed scores: det≈0.947, cls≈0.781.
All 5 eval scripts have been patched (evaluate.py, evaluate_tta.py, evaluate_conf_sweep.py, evaluate_ensemble.py, train_4x4090.py).

## How to run
```bash
./run.sh                    # full pipeline: prepare → train → eval → submission
./run.sh --skip-train       # reuse existing training, just eval + submission
./run.sh --epochs 120       # custom epochs
./run.sh --name exp_name    # custom run name
```

## Infrastructure
- **Training**: vast.ai 4x RTX 4090 (SSH configured in run.sh)
- **Testing**: GCP L4 instance `test-l4` (matches submission sandbox)
- Training takes ~10s/epoch on 4x4090, so 60 epochs ≈ 10 minutes

## Submission sandbox constraints
- L4 GPU (24GB), ultralytics==8.1.0, onnxruntime-gpu==1.20.0, torch==2.6.0
- ONNX export required (models trained with 8.4.24 won't load on 8.1.0 as .pt)
- Max 420MB zip, 300s timeout, no network, blocked imports (os, subprocess, etc.)
- Use pathlib, not os. Use json, not yaml.

## What works
- YOLOv8x at imgsz=1280 is the best model for this task
- Best training config (exp1): `copy_paste=0.3, mixup=0.3, erasing=0.4, degrees=10, flipud=0.5, epochs=150, patience=0, cos_lr=True`
- **TTA helps**: `augment=True` at inference gives +0.002 combined (old "TTA hurts" was a bug artifact)
- **conf=0.001** is optimal (det is flat 0.001–0.020, cls is sensitive to conf)
- FP32 ONNX (not FP16 — FP16 is actually slower on L4)
- Frozen backbone (freeze=10) gives marginal +0.001 over exp1
- Converges around epoch 55; 150ep is sweet spot

## Experiment results (fixed evaluator)
| experiment | det | cls | combined | notes |
|---|---|---|---|---|
| baseline 60ep | 0.9467 | 0.7813 | 0.8971 | yolov8x, COCO pretrain |
| exp1: 150ep strong aug | 0.9530 | 0.8091 | 0.9098 | best static model |
| exp7: frozen backbone | 0.9542 | 0.8093 | 0.9107 | freeze=10, marginal gain |
| exp1 + TTA | 0.9528 | 0.8161 | 0.9118 | TTA helps |
| **exp1 + TTA + conf=0.001** | **0.9528** | **0.8189** | **0.9126** | **BEST** |
| exp6: imgsz=1920 | 0.9502 | 0.8138 | 0.9093 | cls↑ but det↓, net neutral |
| exp5: cls_loss=2.0 | 0.9516 | 0.7992 | 0.9059 | hurt both metrics |
| exp8: label_smoothing=0.1 | 0.9524 | 0.8045 | 0.9080 | backfired on small dataset |
| exp4: exp1 + 100ep ext | 0.9464 | 0.7944 | 0.9008 | overfit |
| ensemble exp1+exp6 | 0.9509 | 0.8180 | 0.9111 | worse than TTA alone |
| ensemble exp1+exp7 | 0.9505 | 0.8108 | 0.9086 | too similar, no diversity |

## What failed (don't repeat)
- SAHI/tiling: destroyed detection mAP (0.84 → 0.64)
- RT-DETR: OOM + 0 mAP after 30 epochs
- imgsz=1920: neutral (cls↑ but det↓ cancels out)
- YOLO11x: slightly worse than YOLOv8x in practice (on ONNX)
- Training on all images (no val split): inflates scores
- SK-110K pretraining → 356-class finetune: broken (1→356 class cold-start, mAP≈0)
- WBF ensemble between similar models (exp1+exp6, exp1+exp7): no diversity gain

## What to try next (cls is the bottleneck, not det)
- Classifier head improvements: larger cls head, cls_loss weight tuning
- More diverse augmentation targeting appearance variation (color jitter, blur)
- Test-time ensemble with models trained on different random seeds (for diversity)
- Multi-scale training schedules
- Pseudo-labeling on unlabeled data if available

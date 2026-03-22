# Training Log - NorgesGruppen Product Detection

## Dataset
- 210 images on disk (248 in annotations)
- 22,731 annotations, 356 categories
- Score = 0.7 * det_AP50 + 0.3 * cls_AP50
- Submission: <420MB zip, L4 GPU, 300s timeout, ultralytics==8.1.0 available

## Model Progression Plan

| Priority | Model | Expected Score | Size | Status |
|----------|-------|---------------|------|--------|
| 1 | Faster R-CNN ResNet50 FPN v2 | ~0.35 | 173MB | Run 2 running |
| 2 | YOLOv8m (img=1280, mosaic+mixup) | ~0.40-0.50 | ~50MB | Queued |
| 3 | YOLOv8l (img=1280) | ~0.45-0.55 | ~90MB | Queued |
| 4 | YOLOv8x (img=1280) | ~0.50-0.60 | ~130MB | If time allows |
| 5 | YOLOv8 + crop classifier | ~0.55+ | ~150MB | Phase 2 |

## Run 1: Faster R-CNN ResNet50 FPN v2 (baseline)
- **Model:** torchvision fasterrcnn_resnet50_fpn_v2
- **Config:** 30 epochs, batch=8, img=1333, lr=0.005, SGD, cosine decay
- **Issues:** Eval had numpy bug, reported 0.0 but raw AP50=0.423 (det) / 0.134 (cls)
- **Real score estimate:** 0.7*0.423 + 0.3*0.134 = **~0.336**
- **Status:** Completed

## Run 2: Faster R-CNN ResNet50 FPN v2 (fixed eval + improvements)
- **Model:** torchvision fasterrcnn_resnet50_fpn_v2
- **Config:** 50 epochs, batch=8, img=1333, lr=0.005, SGD, cosine (eta_min=1e-5), 3-epoch warmup
- **Improvements:** Color jitter augmentation, LR warmup, box clamping
- **Results:** det_AP50=0.2055, cls_AP50=0.2127, **score=0.2076**
- **Loss:** 8.95 → 1.08
- **Checkpoint:** 180.7MB
- **Status:** Completed

## Run 3: YOLOv8m
- **Model:** ultralytics YOLOv8m
- **Config:** 100 epochs, img=1280, batch=8, mosaic+mixup+copy_paste, SGD, cosine LR
- **Results:** mAP50=0.765, P=0.755, R=0.745
- **Best checkpoint:** 51MB
- **Status:** Completed

## Run 4: YOLOv8l
- **Model:** ultralytics YOLOv8l
- **Config:** 100 epochs, img=1280, batch=4, mosaic+mixup
- **Results:** mAP50=0.778, P=0.771, R=0.735, mAP50-95=0.519
- **Best checkpoint:** 85MB
- **Status:** Completed

## Run 5: YOLOv8x
- **Model:** ultralytics YOLOv8x
- **Config:** 100 epochs, img=1280, batch=4, mosaic+mixup
- **Results:** mAP50=0.768, P=0.737, R=0.755, mAP50-95=0.512
- **Best checkpoint:** 132MB
- **Note:** WORSE than YOLOv8l — overfitting on 210 images. YOLOv8l is the sweet spot.
- **Status:** Completed

## Run 6: YOLO11x at 1280
- **Model:** ultralytics YOLO11x (57M params)
- **Config:** 100 epochs, img=1280, batch=4, mosaic+mixup
- **Results:** mAP50=0.778 — same as YOLOv8l, no gain from architecture alone at this resolution
- **Best checkpoint:** 110MB
- **Status:** Completed

## Run 7: YOLO11x imgsz=1920
- **Model:** ultralytics YOLO11x trained at near-native resolution
- **Config:** 100 epochs, img=1920, batch=2
- **Results:** mAP50=0.783, mAP50-95=0.535, P=0.773, R=0.754
- **Best checkpoint:** 111MB
- **Status:** Completed

## Run 8: YOLO11x imgsz=1920 continued
- **Model:** Resume from Run 7 best.pt
- **Config:** 200 more epochs, img=1920, batch=2
- **Results:** mAP50=0.787, mAP50-95=0.529
- **Note:** Only +0.004 over Run 7 — diminishing returns from more epochs
- **Status:** Completed

## Run 9: YOLO11x tuned ★ NEW BEST
- **Model:** YOLO11x with optimized hyperparameters
- **Config:** 150 epochs, img=1920, batch=2, close_mosaic=20, copy_paste=0.3, mixup=0.15, scale=0.9, degrees=5, shear=2
- **Results:** mAP50=0.806, P=0.777, R=0.770, mAP50-95=0.519
- **Best checkpoint:** 111MB
- **Status:** Completed

## Best Model: YOLO11x tuned Run 9 — mAP50=0.806, 111MB
## IMPORTANT: Sandbox only supports YOLOv8 (ultralytics==8.1.0)
- YOLO11 models will NOT load in sandbox
- Must use YOLOv8 (s/m/l/x) OR export YOLO11 to ONNX
- ONNX export of YOLO11x tuned: 230.7MB (fits 420MB limit)

## Run 10: YOLOv8x tuned at 1920 ★ BEST SANDBOX-COMPATIBLE
- **Model:** YOLOv8x with tuned hyperparams
- **Config:** 150 epochs, img=1920, batch=2, close_mosaic=20, copy_paste=0.3, scale=0.9, degrees=5
- **Results:** mAP50=0.811, P=0.792, R=0.760, mAP50-95=0.516
- **Best checkpoint:** 132MB (fits 420MB zip)
- **Status:** Completed

## YOLOv8x Experiments (running)
Testing parameter variations from the best config (Run 10, mAP50=0.811):

| Exp | Change | Hypothesis |
|-----|--------|-----------|
| v8x_cp05 | copy_paste 0.3→0.5 | More synthetic data for 41 single-instance classes |
| v8x_cm30 | close_mosaic 20→30 | More clean fine-tuning epochs |
| v8x_finetune | Resume best.pt, lr=0.001 | Fine-tune with low LR |
| v8x_2048 | imgsz 1920→2048 | Higher resolution (images avg 2800px) |
| v8x_augplus | degrees=10,shear=5,mixup=0.2 | More augmentation diversity |

Results will be logged to v8_experiments_log.json.

## Next: SAHI inference should push well past 0.80+

---

## How to Run (if server goes down)

### Prerequisites
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu128
pip install ultralytics pycocotools pillow sahi
```

### Training
```bash
cd /root/norgesgruppen

# Prepare data: put images in data/train/images/ and annotations.json in data/train/

# Option 1: Standard YOLO training
python3 train_yolo.py --model yolo11x.pt --epochs 100 --img-size 1920 --batch-size 2 --name shelf_det

# Option 2: Tuned hyperparameters (recommended)
python3 train_tuned.py --model yolo11x.pt --epochs 150 --img-size 1920 --batch-size 2 --name shelf_tuned

# Option 3: Train on ALL data for final submission (no val split)
python3 train_tuned.py --model yolo11x.pt --epochs 150 --img-size 1920 --batch-size 2 --name shelf_final --all-data
```

### Inference
```bash
# Standard inference
python3 run_frcnn.py --input /path/to/images --output predictions.json --weights weights/best_inference.pt

# YOLO inference with SAHI (recommended for competition)
python3 run_yolo_sahi.py --input /path/to/images --output predictions.json --weights yolo_runs/shelf_tuned/weights/best.pt --imgsz 1920

# YOLO inference without SAHI
python3 run_yolo_sahi.py --input /path/to/images --output predictions.json --weights yolo_runs/shelf_tuned/weights/best.pt --imgsz 1920 --no-sahi
```

### Tripletex Server
```bash
cd /path/to/repo/tripletex
cp ../.env .env  # or create .env with keys
npm install
npx tsx src/server.ts

# In another terminal, start tunnel:
cloudflared tunnel --url http://localhost:3000
```

## Inference Strategy: SAHI
- **Key insight:** Friend got 0.84 with SAHI at imgsz=1920
- SAHI slices large images into overlapping tiles, runs detection per tile, merges results
- Critical for our large shelf images (up to 5712x4284)
- Combined with full-image inference + NMS merge

## Best Model: YOLOv8l (Run 4) — mAP50=0.778, 85MB
## Target: >0.84 with YOLO11x + SAHI + imgsz=1920

## Key Insights
- Detection is 70% of score — prioritize recall and box quality
- 356 classes with 210 images = extreme long tail (41 classes have only 1 box)
- Mosaic augmentation effectively 4x the training data
- Two-stage approach (detector + classifier) likely needed for best cls_AP50
- Reference product images in NM_NGD_product_images/ can boost classifier

## YOLOv8x Experiment Results

| Exp | Change | mAP50 | vs Baseline |
|---|---|---|---|
| **baseline** | close_mosaic=20, copy_paste=0.3, scale=0.9, degrees=5 | **0.811** | **best** |
| v8x_cp05 | copy_paste 0.5 | 0.797 | -0.014 |
| v8x_cm30 | close_mosaic 30 | 0.802 | -0.009 |
| v8x_finetune | resume best, lr=0.001 | 0.801 | -0.010 |
| v8x_2048 | imgsz 2048 | 0.775 | -0.036 |
| v8x_augplus | degrees=10, shear=5, mixup=0.2 | 0.786 | -0.025 |

**Conclusion:** Original tuned config is optimal. No parameter variation improved results.

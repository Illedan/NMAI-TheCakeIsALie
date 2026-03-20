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
- **Improvements:** Fixed numpy eval, color jitter augmentation, LR warmup, box clamping
- **Status:** Running (epoch ~25/50)

## Run 3: YOLOv8m (planned)
- **Model:** ultralytics YOLOv8m
- **Config:** 100 epochs, img=1280, batch=8, mosaic+mixup+copy_paste, SGD, cosine LR
- **Why:** Better dense detection, built-in augmentation (mosaic=4x data), faster inference
- **Note:** Sandbox has ultralytics==8.1.0 pre-installed

## Run 4: YOLOv8l (planned)
- **Model:** ultralytics YOLOv8l
- **Config:** Same as Run 3 but larger backbone
- **Why:** More capacity for 356 classes

## Key Insights
- Detection is 70% of score — prioritize recall and box quality
- 356 classes with 210 images = extreme long tail (41 classes have only 1 box)
- Mosaic augmentation effectively 4x the training data
- Two-stage approach (detector + classifier) likely needed for best cls_AP50
- Reference product images in NM_NGD_product_images/ can boost classifier

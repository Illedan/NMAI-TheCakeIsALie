# Training Plan: Push Beyond 0.89

## Current State
- Best online: 0.89 (det=0.95, cls=0.82)
- Best local val: 0.9126 (det=0.9528, cls=0.8189)
- Bottleneck: Classification (cls=0.82), NOT detection (det=0.95)
- Our best (separate training): 0.811 mAP50 on YOLOv8x

## Key Insights from Johan's CLAUDE.md
- SAHI DESTROYS detection (don't use it!)
- YOLOv8x at imgsz=1280 is optimal
- conf=0.001 at inference is critical
- TTA helps (+0.002)
- ONNX FP32, not FP16
- Copy_paste=0.3, mixup=0.3, erasing=0.4, degrees=10, flipud=0.5
- patience=0, cos_lr=True, 150 epochs

## What to Try (Classification-focused)

### 1. Multi-seed ensemble (most promising)
Train same config with different seeds (42, 123, 456).
Average predictions. Different random initializations → diversity on cls.

### 2. Stronger classification augmentation
- RandomErasing 0.5 (up from 0.4)
- Color jitter stronger
- CutMix
- Label smoothing (tried 0.1, failed — try 0.05?)

### 3. Use product reference images
- NM_NGD_product_images/ has 344 product folders, ~1599 reference images
- Could use as extra training data for classification
- Map reference folder names to category IDs
- Crop-paste reference images onto shelf backgrounds

### 4. Two-stage: detector + classifier
- Use YOLOv8x for detection (det=0.95 is strong)
- Train separate EfficientNet/ConvNeXt classifier on crops
- Classify detected boxes with second model
- Could boost cls from 0.82 to 0.88+

### 5. Knowledge distillation
- Train a teacher model (e.g., YOLOv8x at high resolution)
- Distill into student model

## Priority Order
1. Retrain with Johan's best config on our GPU (quick win)
2. Multi-seed ensemble
3. Reference image integration
4. Two-stage classifier

## Hardware
- RTX 5090 (32GB) available
- Single GPU training (no DDP needed for 210 images)

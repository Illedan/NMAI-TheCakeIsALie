# Training Log - NorgesGruppen Product Detection

## Dataset
- 210 images on disk (248 in annotations)
- 22,731 annotations
- 356 categories
- Score = 0.7 * det_AP50 + 0.3 * cls_AP50

## Run 1: Faster R-CNN ResNet50 FPN v2 (baseline)
- **Model:** torchvision fasterrcnn_resnet50_fpn_v2
- **Config:** 30 epochs, batch=8, img=1333, lr=0.005, SGD, cosine decay
- **Issues:** Eval had numpy bug, reported 0.0 but raw AP50=0.423 (det) / 0.134 (cls)
- **Status:** Completed, checkpoint saved (173MB)

## Run 2: Faster R-CNN ResNet50 FPN v2 (fixed eval)
- **Model:** torchvision fasterrcnn_resnet50_fpn_v2
- **Config:** 50 epochs, batch=8, img=1333, lr=0.005, SGD, cosine decay (eta_min=1e-5), 3-epoch warmup
- **Improvements:** Fixed numpy eval, better augmentation (color jitter), LR warmup, box clamping
- **Status:** Running...

## Run 3: YOLOv8 (planned)
- **Model:** ultralytics YOLOv8m or YOLOv8l
- **Config:** img=1280, 100 epochs
- **Why:** Faster, better at dense detection, pre-installed in submission sandbox

## Run 4: Larger backbone (planned)
- **Model:** Faster R-CNN with Swin-T or ResNet101 backbone
- **Why:** Stronger feature extraction for fine-grained classification

## Model Size Budget
- Submission zip must be < 420MB uncompressed
- Sandbox: L4 GPU, 24GB VRAM, 300s timeout

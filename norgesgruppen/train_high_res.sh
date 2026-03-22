#!/bin/bash
# Train YOLO11x at higher resolution (1920) for better small object detection
# Then evaluate with SAHI

set -e
cd /root/norgesgruppen

echo "=== Training YOLO11x at imgsz=1920 ==="
python3 train_yolo.py \
    --model yolo11x.pt \
    --epochs 100 \
    --img-size 1920 \
    --batch-size 2 \
    --name shelf_det_11x_1920

echo "=== Training YOLO11l at imgsz=1920 ==="
python3 train_yolo.py \
    --model yolo11l.pt \
    --epochs 100 \
    --img-size 1920 \
    --batch-size 4 \
    --name shelf_det_11l_1920

echo "=== Done ==="

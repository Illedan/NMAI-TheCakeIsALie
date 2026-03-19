#!/bin/bash
set -e

echo "=== Installing dependencies ==="
pip install pycocotools pillow

echo "=== Checking GPU ==="
python3 -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')"

echo "=== Checking torchvision ==="
python3 -c "import torchvision; print(f'torchvision: {torchvision.__version__}')"

echo "=== Verifying data ==="
python3 -c "
import json
from pathlib import Path
data_dir = Path('data/train')
ann = json.loads((data_dir / 'annotations.json').read_text())
imgs = list((data_dir / 'images').glob('*.jpg'))
print(f'Images on disk: {len(imgs)}')
print(f'Images in annotations: {len(ann[\"images\"])}')
print(f'Annotations: {len(ann[\"annotations\"])}')
print(f'Categories: {len(ann[\"categories\"])}')
"

echo ""
echo "=== Ready to train ==="
echo "Run: python3 train.py --epochs 30 --batch-size 4 --img-size 1024"
echo "Or with more VRAM: python3 train.py --epochs 30 --batch-size 8 --img-size 1333"

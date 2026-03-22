Implement a PyTorch training and inference pipeline for the NorgesGruppen Data object detection competition.

Requirements:

- Use torch==2.6.0 and torchvision==0.21.0 compatibility.
- Use torchvision Faster R-CNN ResNet50 FPN v2 as the baseline detector.
- Build a custom COCO dataset loader for shelf images and annotations.json.
- Convert COCO boxes [x, y, w, h] to xyxy for training.
- Support category mapping from competition category_id to internal model labels and back.
- Use a reproducible train/val split.
- Add moderate detection-safe augmentations.
- Train with AMP, SGD, cosine or step scheduler, checkpoint best model by validation score.
- Implement validation metrics matching the competition:
  - detection AP50 ignoring category
  - classification AP50 with category
  - final score = 0.7 _ det_ap50 + 0.3 _ cls_ap50
- Save state_dict checkpoints only.
- Create a sandbox-safe submission run.py that:
  - accepts --input and --output
  - loads the checkpoint
  - uses pathlib instead of os
  - uses json instead of yaml
  - runs inference on all images
  - writes predictions.json in the required format
- Avoid blocked imports in submission code.
- Keep submission package simple and compatible with the sandbox.

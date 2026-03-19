# NorgesGruppen Data Object Detection - Solution Ideas

## What is in the local folder

- `data/train/annotations.json` exists and contains `248` images, `22,731` annotations, and `356` categories.
- `data/train/images/` contains the shelf photos.
- `data/NM_NGD_product_images/` contains `344` product reference folders and about `1,599` reference images across views such as `front`, `back`, `left`, `right`, `top`, `bottom`, and `main`.
- The local copy does not exactly match the task text (`254` images, `~22,300` annotations, `357` categories), so any scripts should trust the files on disk, not the brief.

## Key observations

- This is a very small detection dataset for `356` classes. The long tail is severe.
- All classes appear at least once, but many barely appear:
  - `41` classes have only `1` box
  - `84` classes have `<= 5` boxes
  - `115` classes have `<= 10` boxes
- Image sizes vary a lot, so the pipeline should normalize this carefully.
- The score is dominated by detection (`70%`), so a strong detector with imperfect classification can still do well.
- The reference product image catalog is likely the main lever for improving the classification part beyond a plain detector.

## Best high-level strategy

Build the system in two stages:

1. Train a strong shelf-product detector that is optimized first for recall and box quality.
2. Add a second-stage classifier or retrieval model on detected crops to improve `category_id`.

This is safer than asking one detector to learn `356` classes from only `248` shelf images.

## Approach 1: Strong detection-first baseline

Use this first because it should produce a competitive score quickly.

- Train YOLOv8 with either:
  - class-agnostic detection if you want the fastest path to a decent score
  - full `356`-class detection if you want a single-model baseline for comparison
- Start with `yolov8m` or `yolov8l`.
  - `yolov8s` is a speed baseline.
  - `yolov8x` may be unnecessary unless validation clearly improves.
- Train at a larger image size such as `1280` or `1536` because shelf products are small and dense.
- Use tiling during training and inference if full-image detection misses small products.
  - Example: split each image into overlapping tiles, run inference per tile, then merge boxes.
- Favor recall:
  - low confidence threshold before NMS
  - class-agnostic NMS is worth testing
  - keep more proposals for the classifier stage

Why this matters:

- Detection mAP alone is worth `70%`.
- A detector that finds most items gives the second stage a chance to fix labels later.

## Approach 2: Detection + crop classifier

This is the most practical path to a stronger total score.

- Train detector to output boxes.
- Crop each predicted box.
- Train a separate image classifier on product crops.

Classifier training data ideas:

- Use ground-truth shelf crops from the training set.
- Expand with the reference product images in `NM_NGD_product_images/`.
- If the reference folders can be mapped to class ids, mix them directly into classifier training.
- If no mapping exists yet, treat that as a data integration task to solve early.

Good classifier options:

- EfficientNet / ConvNeXt / ViT image classifier
- Metric-learning model for nearest-neighbor retrieval
- CLIP-like embedding model if you want retrieval over the reference catalog

Why a separate classifier is attractive:

- The classifier sees tighter crops than the detector.
- Shelf detection and fine-grained package recognition are different problems.
- You can iterate on classification without retraining the detector.

## Approach 3: Detection + retrieval against product reference images

This may be better than a standard closed-set classifier because the task is fine-grained and the reference packshots are high signal.

Idea:

- Precompute embeddings for all reference product images.
- For each detected crop, compute its embedding.
- Assign the category of the nearest matching reference image or nearest product cluster.

Useful variants:

- Use multiple views per product (`front`, `left`, `right`, etc.) as separate gallery images.
- Average embeddings per product to create one prototype.
- Use top-k nearest products and combine with detector logits.

Why this may work:

- Many grocery products differ mostly by packaging details.
- The reference catalog provides cleaner supervision than the shelf photos.

Main risk:

- The reference folders appear to be SKU-like codes, while `annotations.json` categories are product names. You may need metadata to map these together.

## Approach 4: Hybrid scoring model

A strong competition setup is likely:

- Detector proposes boxes and coarse class scores.
- Crop model produces refined class probabilities.
- Final score combines both.

For example:

- Use detector confidence for objectness.
- Use classifier softmax for category.
- Multiply or blend them, then clamp each output score to a minimum of `0.01` to satisfy the submission rule.

This can outperform either model alone if the detector is good at localization and the classifier is better at fine-grained identity.

## Validation strategy

Do not rely on a single random split.

- Use grouped folds at image level, never crop-level leakage.
- Prefer `3`-fold or `5`-fold cross-validation.
- Track:
  - detection mAP@0.5 with category ignored
  - classification mAP@0.5 with category enforced
  - recall at low confidence thresholds
- Save out visualizations of false negatives, duplicate detections, and label confusions.

Important:

- With only `248` images, leaderboard overfitting is a real risk.
- Ensemble only if it meaningfully improves local CV, because submission slots are limited.

## Data work that is likely worth it

### 1. Convert COCO to YOLO cleanly

- Build a deterministic converter from `annotations.json` to YOLO labels.
- Keep category id mapping stable.
- Validate boxes after conversion.

### 2. Crop extraction for classifier training

- Create a script that extracts ground-truth product crops from shelf images.
- Optionally pad the crop a little around each box.
- Save metadata: image id, category id, original bbox, crop path.

### 3. Use the reference catalog aggressively

- Normalize the product reference images.
- Remove backgrounds if they hurt retrieval or classifier quality.
- Generate synthetic shelf-like crops:
  - perspective warp
  - blur
  - glare
  - occlusion
  - partial visibility

### 4. Long-tail handling

- Reweight rare classes.
- Oversample minority classes in the classifier.
- Consider focal loss or class-balanced loss for the classification stage.

## Augmentation ideas

For detector:

- Mosaic and mixup, but verify they do not destroy realistic shelf geometry.
- Random crop, scale, color jitter, blur, compression, and lighting changes.
- Mild rotation and perspective augmentation.

For classifier:

- Stronger crop-level augmentation is fine.
- Simulate occlusion from neighboring products.
- Add label smoothing.

One thing to avoid:

- Overly aggressive augmentations that destroy brand text and package layout, since those details matter for class identity.

## Inference ideas for `run.py`

The sandbox constraints suggest a compact, predictable inference path.

- Load models once at process start.
- Use `pathlib`, not `os` or `subprocess`.
- Run detector first.
- If using tiling:
  - tile image
  - infer per tile
  - merge detections back to full-image coordinates
- For each final box:
  - classify crop or retrieve nearest product
  - output COCO prediction fields
- Enforce `score >= 0.01` for every prediction.

Possible fast inference variants:

- YOLOv8 PyTorch end-to-end if speed is already within budget.
- Export detector and classifier to ONNX if startup or inference time becomes tight.

## Packaging constraints to design around

- `run.py` must be at zip root.
- Uncompressed zip contents must stay below `420 MB`.
- Sandbox has `300s` timeout, `4` vCPU, `8 GB RAM`, and one NVIDIA L4 (`24 GB VRAM`).
- The environment already has `PyTorch`, `onnxruntime-gpu`, and `ultralytics==8.1.0`.

Practical implications:

- Keep the number of models small.
- Avoid huge ensembles unless local timing proves they fit comfortably.
- Prefer one strong detector plus one compact classifier over many medium models.

## Recommended experiment order

### Phase 1: Fast baseline

- Convert data to YOLO format.
- Train `yolov8m` and `yolov8l`.
- Evaluate full-image inference vs tiled inference.
- Submit the best detector-only version if needed for an early baseline.

### Phase 2: Classification upgrade

- Extract training crops from ground truth.
- Train a crop classifier.
- Compare:
  - detector class directly
  - classifier-only on detected crops
  - blended detector + classifier score

### Phase 3: Reference-image leverage

- Build a retrieval prototype using the product image catalog.
- Test whether retrieval beats the classifier on rare classes.
- If it helps, use retrieval as:
  - primary classifier for all boxes, or
  - fallback only for low-confidence detector/classifier outputs

### Phase 4: Submission hardening

- Profile `run.py` end-to-end.
- Verify package size.
- Verify no forbidden imports.
- Verify score floor handling.
- Generate COCO output exactly as expected.

## Likely strongest final submission

If I were optimizing for leaderboard performance with this dataset, I would prioritize this stack:

- `yolov8l` detector trained for high recall
- tiled inference on large shelf images
- crop classifier trained on shelf crops plus mapped product reference images
- optional retrieval fallback for rare or confusing classes
- lightweight ensembling only if timing allows

## Open questions to resolve early

- How do the `NM_NGD_product_images` folder names map to the `annotations.json` category ids?
- Is there hidden test distribution shift across stores, camera angles, or shelf types?
- Are some categories visually near-identical variants where barcode-level matching is required?
- Does the evaluator allow multiple detections per object without heavy penalty, or should precision be tightened late?

## Concrete deliverables to build next

- `prepare_yolo_data.py`
- `prepare_crop_classification_data.py`
- `train_detector.py`
- `train_classifier.py`
- `run.py`
- `validate_submission.py`

If you want, the next step should be building the data-prep scripts and a first YOLO baseline in this folder.

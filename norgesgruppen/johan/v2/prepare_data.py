"""
Convert downloaded data into YOLO format.

Input:  data/annotations.json, data/images/*.jpg  (as downloaded from competition)
Output: dataset/{train,val}/{images,labels}/, dataset.yaml
"""
import json, random
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent
ANN_FILE = ROOT / "data" / "annotations.json"
IMG_DIR = ROOT / "data" / "images"
OUT_DIR = ROOT / "dataset"

with open(ANN_FILE) as f:
    data = json.load(f)

images = {img["id"]: img for img in data["images"]}
anns_by_image = defaultdict(list)
for ann in data["annotations"]:
    anns_by_image[ann["image_id"]].append(ann)

# Only include images that exist on disk
existing = {int(p.stem.split("_")[-1]) for p in IMG_DIR.iterdir() if p.suffix == ".jpg"}
image_ids = sorted(existing & set(images.keys()))

# 90/10 split
random.seed(42)
random.shuffle(image_ids)
split = int(0.9 * len(image_ids))
splits = {"train": set(image_ids[:split]), "val": set(image_ids[split:])}

for subset, ids in splits.items():
    (OUT_DIR / subset / "images").mkdir(parents=True, exist_ok=True)
    (OUT_DIR / subset / "labels").mkdir(parents=True, exist_ok=True)
    for img_id in ids:
        info = images[img_id]
        w, h = info["width"], info["height"]
        src = (IMG_DIR / info["file_name"]).resolve()
        dst = OUT_DIR / subset / "images" / info["file_name"]
        if not dst.exists():
            dst.symlink_to(src)
        lines = []
        for ann in anns_by_image.get(img_id, []):
            bx, by, bw, bh = ann["bbox"]
            lines.append(f"{ann['category_id']} {(bx+bw/2)/w:.6f} {(by+bh/2)/h:.6f} {bw/w:.6f} {bh/h:.6f}")
        (OUT_DIR / subset / "labels" / f"{Path(info['file_name']).stem}.txt").write_text("\n".join(lines))

# Write dataset.yaml
names = {cat["id"]: cat["name"] for cat in data["categories"]}
lines = [f"path: {OUT_DIR.resolve()}", "train: train/images", "val: val/images", f"nc: {len(names)}", "names:"]
for i in sorted(names):
    lines.append(f"  {i}: {names[i]}")
(ROOT / "dataset.yaml").write_text("\n".join(lines))

print(f"Train: {len(splits['train'])}  Val: {len(splits['val'])}  Categories: {len(names)}")

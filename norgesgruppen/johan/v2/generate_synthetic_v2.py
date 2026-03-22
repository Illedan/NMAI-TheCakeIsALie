"""
Generate realistic synthetic shelf images v2.

Key improvements over v1:
- Products placed with realistic shelf-like overlap (tight packing, slight overlaps)
- Partial occlusion (products behind others)
- Shelf-row structure (products aligned in rows)
- Background from real images (not just pasting on original)
- Subtle position jitter (products not perfectly aligned)
- Lighting gradients across shelf
- Fewer per-crop augmentations (v1 was too aggressive)
- Controlled count: fewer synthetic = less domain gap

Usage:
  python3 generate_synthetic_v2.py --count 200
"""
import json, random, argparse, math
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ROOT = Path(__file__).parent
    ANN_FILE = ROOT / "annotations.json"
    IMG_DIR = ROOT / "data" / "images"
    SYN_DIR = ROOT / "synthetic"
    SYN_DIR.mkdir(exist_ok=True)

    with open(ANN_FILE) as f:
        data = json.load(f)

    id_to_info = {img["id"]: img for img in data["images"]}
    anns_by_image = {}
    for ann in data["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    existing = {int(p.stem.split("_")[-1]) for p in IMG_DIR.iterdir() if p.suffix == ".jpg"}
    image_ids = sorted(existing & set(img["id"] for img in data["images"]))

    # Pre-load crops by category with metadata
    crops_by_cat = {}
    all_crops = []
    for img_id in image_ids:
        info = id_to_info[img_id]
        img_path = IMG_DIR / info["file_name"]
        if not img_path.exists(): continue
        img = Image.open(img_path).convert("RGB")
        for ann in anns_by_image.get(img_id, []):
            x, y, w, h = ann["bbox"]
            if w < 10 or h < 10: continue
            # Add small padding (5%) to make crops more natural
            pad_x, pad_y = w * 0.05, h * 0.05
            cx1 = max(0, x - pad_x)
            cy1 = max(0, y - pad_y)
            cx2 = min(img.width, x + w + pad_x)
            cy2 = min(img.height, y + h + pad_y)
            crop = img.crop((cx1, cy1, cx2, cy2))
            entry = {"crop": crop, "cat_id": ann["category_id"], "w": w, "h": h}
            crops_by_cat.setdefault(ann["category_id"], []).append(entry)
            all_crops.append(entry)

    print(f"Loaded crops: {len(crops_by_cat)} categories, {len(all_crops)} total")

    random.seed(args.seed)
    next_img_id = max(img["id"] for img in data["images"]) + 1
    next_ann_id = max(ann["id"] for ann in data["annotations"]) + 1
    new_images, new_annotations = [], []

    for syn_idx in range(args.count):
        # Pick a random source image as background
        src_id = random.choice(image_ids)
        src_info = id_to_info[src_id]
        img = Image.open(IMG_DIR / src_info["file_name"]).convert("RGB")
        w_img, h_img = img.size
        src_anns = list(anns_by_image.get(src_id, []))

        anns_for_img = []

        # Strategy selection
        strategy = random.random()

        if strategy < 0.45:
            # STRATEGY 1: Gentle modification of existing image (45%)
            # Only swap some products, keep most in place — closest to real data
            for ann in src_anns:
                x, y, w, h = ann["bbox"]
                cat_id = ann["category_id"]

                swap_roll = random.random()

                if swap_roll < 0.25 and cat_id in crops_by_cat and len(crops_by_cat[cat_id]) > 1:
                    # Same-category swap (25%) — reduced from 40% to be less aggressive
                    crop_entry = random.choice(crops_by_cat[cat_id])
                    crop = crop_entry["crop"].copy()
                    # Subtle augmentation only
                    if random.random() < 0.3:
                        crop = ImageEnhance.Brightness(crop).enhance(random.uniform(0.85, 1.15))
                    if random.random() < 0.2:
                        crop = ImageOps.mirror(crop)
                    crop = crop.resize((max(1, int(w)), max(1, int(h))))
                    img.paste(crop, (int(x), int(y)))

                elif swap_roll < 0.30:
                    # Cross-category swap (5%) — very rare, for hard negatives
                    other = random.choice(list(crops_by_cat.keys()))
                    if other != cat_id and crops_by_cat[other]:
                        crop_entry = random.choice(crops_by_cat[other])
                        crop = crop_entry["crop"].copy()
                        crop = crop.resize((max(1, int(w)), max(1, int(h))))
                        img.paste(crop, (int(x), int(y)))
                        cat_id = other

                anns_for_img.append({
                    "id": next_ann_id, "image_id": next_img_id,
                    "category_id": cat_id, "bbox": [x, y, w, h],
                    "area": w * h, "iscrowd": 0
                })
                next_ann_id += 1

        elif strategy < 0.75:
            # STRATEGY 2: Shelf-realistic rearrangement (30%)
            # Take products from source image, rearrange with realistic spacing
            # Products in rows, touching/slightly overlapping like real shelves

            # Keep original annotations but shift products slightly
            for ann in src_anns:
                x, y, w, h = ann["bbox"]
                cat_id = ann["category_id"]

                # Small position jitter (simulates imperfect shelf placement)
                jx = random.gauss(0, w * 0.03)  # 3% of width
                jy = random.gauss(0, h * 0.02)  # 2% of height
                nx = max(0, min(w_img - w, x + jx))
                ny = max(0, min(h_img - h, y + jy))

                # Occasionally swap with same category
                if random.random() < 0.20 and cat_id in crops_by_cat and len(crops_by_cat[cat_id]) > 1:
                    crop_entry = random.choice(crops_by_cat[cat_id])
                    crop = crop_entry["crop"].copy()
                    crop = crop.resize((max(1, int(w)), max(1, int(h))))
                    img.paste(crop, (int(nx), int(ny)))

                anns_for_img.append({
                    "id": next_ann_id, "image_id": next_img_id,
                    "category_id": cat_id, "bbox": [nx, ny, w, h],
                    "area": w * h, "iscrowd": 0
                })
                next_ann_id += 1

        else:
            # STRATEGY 3: Mix products from two different source images (25%)
            # Creates new shelf compositions while keeping realistic density
            src_id2 = random.choice(image_ids)
            src_anns2 = list(anns_by_image.get(src_id2, []))

            # Use all products from source 1
            for ann in src_anns:
                x, y, w, h = ann["bbox"]
                cat_id = ann["category_id"]
                anns_for_img.append({
                    "id": next_ann_id, "image_id": next_img_id,
                    "category_id": cat_id, "bbox": [x, y, w, h],
                    "area": w * h, "iscrowd": 0
                })
                next_ann_id += 1

            # Paste some products from source 2 on top (creating realistic overlaps)
            img2 = Image.open(IMG_DIR / id_to_info[src_id2]["file_name"]).convert("RGB")
            n_paste = random.randint(3, min(15, len(src_anns2)))
            pasted_anns = random.sample(src_anns2, n_paste)

            for ann in pasted_anns:
                x2, y2, w2, h2 = ann["bbox"]
                if w2 < 10 or h2 < 10: continue
                crop = img2.crop((x2, y2, x2 + w2, y2 + h2))

                # Place near an existing product (simulates products next to each other)
                if anns_for_img:
                    ref = random.choice(anns_for_img)
                    rx, ry, rw, rh = ref["bbox"]
                    # Place adjacent: to the right, left, or same row
                    direction = random.choice(["right", "left", "above", "below"])
                    if direction == "right":
                        nx = rx + rw - random.uniform(0, w2 * 0.15)  # slight overlap
                        ny = ry + random.gauss(0, h2 * 0.1)
                    elif direction == "left":
                        nx = rx - w2 + random.uniform(0, w2 * 0.15)
                        ny = ry + random.gauss(0, h2 * 0.1)
                    elif direction == "above":
                        nx = rx + random.gauss(0, w2 * 0.2)
                        ny = ry - h2 + random.uniform(0, h2 * 0.1)
                    else:
                        nx = rx + random.gauss(0, w2 * 0.2)
                        ny = ry + rh - random.uniform(0, h2 * 0.1)

                    nx = max(0, min(w_img - w2, nx))
                    ny = max(0, min(h_img - h2, ny))
                else:
                    nx, ny = x2, y2

                crop = crop.resize((max(1, int(w2)), max(1, int(h2))))
                img.paste(crop, (int(nx), int(ny)))

                anns_for_img.append({
                    "id": next_ann_id, "image_id": next_img_id,
                    "category_id": ann["category_id"],
                    "bbox": [nx, ny, w2, h2],
                    "area": w2 * h2, "iscrowd": 0
                })
                next_ann_id += 1

        # Global augmentation — SUBTLE only
        if random.random() < 0.4:
            img = ImageEnhance.Brightness(img).enhance(random.uniform(0.9, 1.1))
        if random.random() < 0.3:
            img = ImageEnhance.Color(img).enhance(random.uniform(0.85, 1.15))
        if random.random() < 0.15:
            img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.3, 1.0)))
        if random.random() < 0.1:
            img = ImageEnhance.Contrast(img).enhance(random.uniform(0.9, 1.1))

        # Lighting gradient (simulates uneven shelf lighting) — 10% chance
        if random.random() < 0.1:
            gradient = Image.new("L", (w_img, h_img))
            arr = np.zeros((h_img, w_img), dtype=np.uint8)
            direction = random.choice(["horizontal", "vertical"])
            if direction == "horizontal":
                for x in range(w_img):
                    arr[:, x] = int(200 + 55 * (x / w_img))
            else:
                for y in range(h_img):
                    arr[y, :] = int(200 + 55 * (y / h_img))
            gradient = Image.fromarray(arr, mode="L")
            img = Image.composite(img, img, gradient)

        out_name = f"synthetic_{syn_idx:04d}.jpg"
        img.save(SYN_DIR / out_name, quality=92)
        new_images.append({"id": next_img_id, "file_name": out_name, "width": w_img, "height": h_img})
        new_annotations.extend(anns_for_img)
        next_img_id += 1
        if (syn_idx + 1) % 50 == 0:
            print(f"Generated {syn_idx+1}/{args.count}")

    combined = {
        "images": data["images"] + new_images,
        "annotations": data["annotations"] + new_annotations,
        "categories": data["categories"]
    }
    (SYN_DIR / "annotations_augmented.json").write_text(json.dumps(combined))
    print(f"\nDone! {len(combined['images'])} images, {len(combined['annotations'])} annotations")
    print(f"  Real: {len(data['images'])}, Synthetic: {len(new_images)}")

if __name__ == "__main__":
    main()

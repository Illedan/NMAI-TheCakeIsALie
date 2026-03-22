"""
Generate synthetic shelf images by copy-pasting GT crops.

Techniques:
- Same-category product swapping (40% per box)
- Cross-category swapping for hard negatives (15%)
- Random zoom/crop (30% - simulates distance variation)
- Mirror flip on swaps (30%)
- Global brightness/contrast/color/blur/sharpen augmentation
- Preserves exact bounding box annotations

Usage:
  python3 generate_synthetic.py --count 500
  
Results:
  200 synthetic → 0.9361 combined (Johan eval), 0.9013 online
  500 synthetic → training...
"""
import json, random, argparse
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

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

    # Pre-load crops by category
    crops_by_cat = {}
    for img_id in image_ids:
        info = id_to_info[img_id]
        img_path = IMG_DIR / info["file_name"]
        if not img_path.exists(): continue
        img = Image.open(img_path).convert("RGB")
        for ann in anns_by_image.get(img_id, []):
            x, y, w, h = ann["bbox"]
            if w < 10 or h < 10: continue
            crop = img.crop((x, y, x+w, y+h))
            crops_by_cat.setdefault(ann["category_id"], []).append(crop)

    print(f"Loaded crops: {len(crops_by_cat)} categories, {sum(len(v) for v in crops_by_cat.values())} total")

    random.seed(args.seed)
    next_img_id = max(img["id"] for img in data["images"]) + 1
    next_ann_id = max(ann["id"] for ann in data["annotations"]) + 1
    new_images, new_annotations = [], []

    for syn_idx in range(args.count):
        src_id = random.choice(image_ids)
        src_info = id_to_info[src_id]
        img = Image.open(IMG_DIR / src_info["file_name"]).convert("RGB")
        w_img, h_img = img.size
        src_anns = list(anns_by_image.get(src_id, []))

        # Random zoom (30%)
        if random.random() < 0.3:
            zoom = random.uniform(1.1, 1.5)
            cw, ch = int(w_img/zoom), int(h_img/zoom)
            cx, cy = random.randint(0, w_img-cw), random.randint(0, h_img-ch)
            img = img.crop((cx, cy, cx+cw, cy+ch)).resize((w_img, h_img))
            new_anns = []
            for ann in src_anns:
                x, y, w, h = ann["bbox"]
                nx, ny, nw, nh = (x-cx)*zoom, (y-cy)*zoom, w*zoom, h*zoom
                if nx >= 0 and ny >= 0 and nx+nw <= w_img and ny+nh <= h_img:
                    new_anns.append({**ann, "bbox": [nx, ny, nw, nh]})
            src_anns = new_anns

        anns_for_img = []
        for ann in src_anns:
            x, y, w, h = ann["bbox"]
            cat_id = ann["category_id"]

            # Same-category swap (40%)
            if random.random() < 0.4 and cat_id in crops_by_cat and len(crops_by_cat[cat_id]) > 1:
                crop = random.choice(crops_by_cat[cat_id])
                crop = crop.rotate(random.uniform(-8, 8), expand=False, fillcolor=(200,200,200))
                crop = ImageEnhance.Brightness(crop).enhance(random.uniform(0.7, 1.3))
                crop = ImageEnhance.Contrast(crop).enhance(random.uniform(0.8, 1.2))
                if random.random() < 0.3: crop = ImageOps.mirror(crop)
                crop = crop.resize((max(1,int(w)), max(1,int(h))))
                img.paste(crop, (int(x), int(y)))

            # Cross-category swap (15%)
            elif random.random() < 0.15:
                other = random.choice(list(crops_by_cat.keys()))
                if other != cat_id and crops_by_cat[other]:
                    crop = random.choice(crops_by_cat[other])
                    crop = crop.resize((max(1,int(w)), max(1,int(h))))
                    img.paste(crop, (int(x), int(y)))
                    cat_id = other

            anns_for_img.append({"id": next_ann_id, "image_id": next_img_id,
                "category_id": cat_id, "bbox": [x, y, w, h], "area": w*h, "iscrowd": 0})
            next_ann_id += 1

        # Global augmentation
        if random.random() < 0.5: img = ImageEnhance.Brightness(img).enhance(random.uniform(0.8, 1.2))
        if random.random() < 0.5: img = ImageEnhance.Color(img).enhance(random.uniform(0.7, 1.3))
        if random.random() < 0.3: img = img.filter(ImageFilter.GaussianBlur(random.uniform(0.5, 2.0)))
        if random.random() < 0.2: img = ImageEnhance.Sharpness(img).enhance(random.uniform(0.5, 2.0))

        out_name = f"synthetic_{syn_idx:04d}.jpg"
        img.save(SYN_DIR / out_name, quality=90)
        new_images.append({"id": next_img_id, "file_name": out_name, "width": w_img, "height": h_img})
        new_annotations.extend(anns_for_img)
        next_img_id += 1
        if (syn_idx+1) % 50 == 0: print(f"Generated {syn_idx+1}/{args.count}")

    combined = {"images": data["images"] + new_images, "annotations": data["annotations"] + new_annotations, "categories": data["categories"]}
    (SYN_DIR / "annotations_augmented.json").write_text(json.dumps(combined))
    print(f"\nDone! {len(combined['images'])} images, {len(combined['annotations'])} annotations")

if __name__ == "__main__":
    main()

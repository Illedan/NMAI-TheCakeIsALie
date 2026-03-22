import json
from PIL import Image, ImageDraw

image = Image.open("../data/train/images/img_00001.jpg")
draw = ImageDraw.Draw(image)

with open("safer_submission.json") as f:
    preds = [p for p in json.load(f) if p["image_id"] == 1]

with open("annotations.json") as f:
    gt = [a for a in json.load(f)["annotations"] if a["image_id"] == 1]

for a in gt:
    x, y, w, h = a["bbox"]
    draw.rectangle([x, y, x + w, y + h], outline="green", width=2)

for p in preds:
    x, y, w, h = p["bbox"]
    draw.rectangle([x, y, x + w, y + h], outline="red", width=2)
    draw.text((x, y - 12), f'{p["score"]:.2f}', fill="red")

image.show()

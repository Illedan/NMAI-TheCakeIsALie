from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torchvision
from torchvision.models.detection import fasterrcnn_resnet50_fpn_v2
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision import transforms as T
from PIL import Image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_WEIGHTS = Path(__file__).resolve().parent / "weights" / "best_inference.pt"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    p.add_argument("--conf", type=float, default=0.05)
    p.add_argument("--max-det", type=int, default=300)
    return p.parse_args()


def pick_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def build_model(num_classes: int, device: str) -> torch.nn.Module:
    model = fasterrcnn_resnet50_fpn_v2(weights=None, min_size=800, max_size=1333)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    return model


def iter_images(input_dir: Path) -> list[Path]:
    return sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def parse_image_id(image_path: Path) -> int:
    return int(image_path.stem.split("_")[-1])


def main() -> None:
    args = parse_args()
    if not args.weights.exists():
        raise FileNotFoundError(f"Weights not found: {args.weights}")

    device = pick_device()
    ckpt = torch.load(str(args.weights), map_location=device, weights_only=False)

    num_classes = ckpt["num_classes"]
    label_to_cat = {int(k): v for k, v in ckpt["label_to_cat"].items()}

    model = build_model(num_classes, device)
    model.load_state_dict(ckpt["model"])
    model.to(device)
    model.eval()

    to_tensor = T.ToTensor()
    predictions: list[dict] = []

    for image_path in iter_images(args.input):
        image_id = parse_image_id(image_path)
        img = Image.open(image_path).convert("RGB")
        img_tensor = to_tensor(img).to(device)

        with torch.no_grad():
            outputs = model([img_tensor])[0]

        boxes = outputs["boxes"].cpu()
        scores = outputs["scores"].cpu()
        pred_labels = outputs["labels"].cpu()

        for i in range(min(len(boxes), args.max_det)):
            score = float(scores[i])
            if score < args.conf:
                continue
            x1, y1, x2, y2 = boxes[i].tolist()
            cat_id = label_to_cat.get(int(pred_labels[i]), 0)
            predictions.append({
                "image_id": image_id,
                "category_id": cat_id,
                "bbox": [
                    round(x1, 1),
                    round(y1, 1),
                    round(x2 - x1, 1),
                    round(y2 - y1, 1),
                ],
                "score": round(max(0.01, score), 4),
            })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions))
    print(f"Wrote {len(predictions)} predictions to {args.output}")


if __name__ == "__main__":
    main()

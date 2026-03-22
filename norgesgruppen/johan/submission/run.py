from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO

WEIGHTS = Path(__file__).resolve().parent / "best.onnx"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = YOLO(str(WEIGHTS), task="detect")
    predictions: list[dict] = []

    for img in sorted(args.input.iterdir()):
        if not img.is_file() or img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            continue
        image_id = int(img.stem.split("_")[-1])
        results = model.predict(
            source=str(img),
            device=device,
            imgsz=1280,
            conf=0.01,
            max_det=1000,
            verbose=False,
        )
        for r in results:
            if r.boxes is None:
                continue
            for i in range(len(r.boxes)):
                x1, y1, x2, y2 = r.boxes.xyxy[i].tolist()
                confidence = max(0.01, float(r.boxes.conf[i].item()))
                predictions.append({
                    "image_id": image_id,
                    "category_id": int(r.boxes.cls[i].item()),
                    "bbox": [
                        round(x1, 1),
                        round(y1, 1),
                        round(x2 - x1, 1),
                        round(y2 - y1, 1),
                    ],
                    "score": round(confidence, 4),
                })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions))


if __name__ == "__main__":
    main()

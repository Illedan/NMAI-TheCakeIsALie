#!/usr/bin/env python3
"""
Inference script for Astar Island ML model.

Usage:
  # From initial state JSON + query results -> prediction JSON
  python3 infer.py --initial seed_0.json --queries queries.json --output prediction.json

  # From initial state JSON only (no queries, blind prediction)
  python3 infer.py --initial seed_0.json --output prediction.json

  # Evaluate against ground truth
  python3 infer.py --initial seed_0.json --queries queries.json --ground-truth analysis.json
"""

import argparse
import json
import math
import numpy as np
import torch
from pathlib import Path

from model import UNet
from dataset import AstarDataset
from generate_data import (
    make_initial_onehot, make_distance_features,
    load_real_queries, simulate_queries, terrain_to_class,
    TERRAIN_OCEAN, TERRAIN_MOUNTAIN, NUM_CLASSES
)

SCRIPT_DIR = Path(__file__).parent
CHECKPOINT_DIR = SCRIPT_DIR / "checkpoints"


def build_input_tensor(initial_grid, obs_freq, obs_count, obs_mask):
    """Build the 19-channel input tensor from components."""
    initial_onehot = make_initial_onehot(initial_grid)
    coast_dist, forest_dist, settle_dist = make_distance_features(initial_grid)

    obs_count_norm = obs_count.astype(np.float32) / max(obs_count.max(), 1)

    input_tensor = np.concatenate([
        initial_onehot,                              # 8 channels
        obs_freq,                                    # 6 channels
        obs_count_norm[:, :, None],                  # 1 channel
        obs_mask.astype(np.float32)[:, :, None],     # 1 channel
        coast_dist[:, :, None],                      # 1 channel
        forest_dist[:, :, None],                     # 1 channel
        settle_dist[:, :, None],                     # 1 channel
    ], axis=-1)  # (H, W, 19)

    return torch.from_numpy(input_tensor).permute(2, 0, 1).float().unsqueeze(0)  # (1, 19, H, W)


def load_model(checkpoint_path=None, device="cpu"):
    """Load trained model."""
    if checkpoint_path is None:
        checkpoint_path = CHECKPOINT_DIR / "best.pt"

    model = UNet(
        in_channels=AstarDataset.input_channels(),
        out_channels=AstarDataset.output_channels(),
        base_filters=64,
    )
    state = torch.load(checkpoint_path, map_location=device, weights_only=True)
    if "model_state_dict" in state:
        model.load_state_dict(state["model_state_dict"])
    else:
        model.load_state_dict(state)
    model.to(device)
    model.eval()
    return model


def predict(model, initial_grid, obs_freq=None, obs_count=None, obs_mask=None,
            device="cpu", eps=0.01):
    """Run inference and return (H, W, 6) probability tensor."""
    H, W = initial_grid.shape

    if obs_freq is None:
        obs_freq = np.zeros((H, W, NUM_CLASSES), dtype=np.float32)
        obs_count = np.zeros((H, W), dtype=np.int32)
        obs_mask = np.zeros((H, W), dtype=bool)

    input_tensor = build_input_tensor(initial_grid, obs_freq, obs_count, obs_mask)
    input_tensor = input_tensor.to(device)

    with torch.no_grad():
        probs = model.predict_probs(input_tensor, eps=eps)  # (1, 6, H, W)

    pred = probs[0].cpu().numpy()  # (6, H, W)
    pred = pred.transpose(1, 2, 0)  # (H, W, 6)

    # Force ocean and mountain cells
    for y in range(H):
        for x in range(W):
            t = initial_grid[y, x]
            if t == TERRAIN_OCEAN:
                pred[y, x] = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            elif t == TERRAIN_MOUNTAIN:
                pred[y, x] = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    # Re-normalize
    for y in range(H):
        for x in range(W):
            s = pred[y, x].sum()
            if s > 0:
                pred[y, x] /= s

    return pred


def score_prediction(prediction, ground_truth):
    """Score prediction using entropy-weighted KL divergence (matches competition)."""
    H, W = prediction.shape[:2]
    total_kl = 0.0
    total_entropy = 0.0

    for y in range(H):
        for x in range(W):
            p = ground_truth[y, x]
            q = prediction[y, x]

            # Entropy of ground truth
            h = 0.0
            for c in range(NUM_CLASSES):
                if p[c] > 1e-8:
                    h -= p[c] * math.log(p[c])

            if h < 1e-8:
                continue  # Skip static cells

            # KL divergence
            kl = 0.0
            for c in range(NUM_CLASSES):
                if p[c] > 1e-8:
                    kl += p[c] * math.log(p[c] / max(q[c], 1e-8))

            total_kl += h * kl
            total_entropy += h

    if total_entropy == 0:
        return 100.0

    weighted_kl = total_kl / total_entropy
    return max(0, min(100, 100 * math.exp(-3 * weighted_kl)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initial", required=True, help="Initial state JSON")
    parser.add_argument("--queries", default=None, help="Query results JSON")
    parser.add_argument("--output", default=None, help="Output prediction JSON")
    parser.add_argument("--ground-truth", default=None, help="Analysis JSON for scoring")
    parser.add_argument("--checkpoint", default=None, help="Model checkpoint path")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    if args.device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    else:
        device = args.device

    # Load initial state
    with open(args.initial) as f:
        initial = json.load(f)
    grid = np.array(initial["grid"], dtype=np.int32)
    H, W = grid.shape

    # Load queries if provided
    if args.queries:
        obs_freq, obs_count, obs_mask = load_real_queries(args.queries, H, W)
    else:
        obs_freq = None
        obs_count = None
        obs_mask = None

    # Load model
    model = load_model(args.checkpoint, device=device)
    print(f"Model loaded, device={device}")

    # Predict
    pred = predict(model, grid, obs_freq, obs_count, obs_mask, device=device)
    print(f"Prediction shape: {pred.shape}")

    # Score if ground truth provided
    if args.ground_truth:
        with open(args.ground_truth) as f:
            analysis = json.load(f)
        gt = np.array(analysis["ground_truth"], dtype=np.float32)
        score = score_prediction(pred, gt)
        print(f"Score: {score:.2f}")

    # Save prediction
    if args.output:
        with open(args.output, "w") as f:
            json.dump(pred.tolist(), f)
        print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

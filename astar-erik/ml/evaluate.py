#!/usr/bin/env python3
"""
Evaluate the ML model against all rounds with ground truth.

Mirrors what ./astar --fast does for the C++ model:
- For each round, run prediction on all 5 seeds
- Compare against ground truth analysis
- Report per-round and overall scores

Supports two modes:
  --blind: predict from initial grid only (no queries)
  --queries N: simulate N queries from ground truth (default: 50)
"""

import argparse
import json
import numpy as np
import torch
from pathlib import Path

from model import UNet
from dataset import AstarDataset
from infer import load_model, predict, score_prediction
from generate_data import (
    simulate_queries, TERRAIN_OCEAN, TERRAIN_MOUNTAIN, NUM_CLASSES
)

SCRIPT_DIR = Path(__file__).parent
ISLAND_DIR = SCRIPT_DIR.parent.parent / "astar-island"


def discover_rounds():
    """Find all rounds with ground truth analysis."""
    analysis_dir = ISLAND_DIR / "analysis"
    is_dir = ISLAND_DIR / "initial_states"

    # Map round_id -> initial_states dir
    round_to_is = {}
    for d in sorted(is_dir.iterdir()):
        summary = d / "summary.json"
        if summary.exists():
            with open(summary) as f:
                s = json.load(f)
            rid = s.get("round_id", "")
            rnum = s.get("round_number", 0)
            if rid and rid not in round_to_is:
                round_to_is[rid] = (d, rnum)

    # Map round_id -> {seed: analysis_path}
    round_analysis = {}
    for af in sorted(analysis_dir.glob("*.json")):
        parts = af.name.replace(".json", "").split("_")
        rid = None
        for p in parts:
            if len(p) == 36 and p.count("-") == 4:
                rid = p
                break
        if not rid:
            continue
        seed = None
        for i, p in enumerate(parts):
            if p == "seed" and i + 1 < len(parts):
                seed = int(parts[i + 1])
                break
        if seed is None:
            continue
        if rid not in round_analysis:
            round_analysis[rid] = {}
        round_analysis[rid][seed] = af

    # Build rounds list
    rounds = []
    for rid, seeds in sorted(round_analysis.items()):
        if rid not in round_to_is:
            continue
        is_path, rnum = round_to_is[rid]
        rounds.append({
            "round_id": rid,
            "round_number": rnum,
            "is_dir": is_path,
            "seeds": seeds,
        })

    rounds.sort(key=lambda r: r["round_number"])
    return rounds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind", action="store_true", help="No queries (predict from map only)")
    parser.add_argument("--queries", type=int, default=50, help="Number of simulated queries per seed 0")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--max-rounds", type=int, default=0)
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

    model = load_model(args.checkpoint, device=device)
    print(f"Model loaded, device={device}")

    rounds = discover_rounds()
    if args.max_rounds > 0:
        rounds = rounds[:args.max_rounds]

    print(f"Found {len(rounds)} rounds with ground truth\n")

    rng = np.random.default_rng(42)
    total_score = 0.0
    total_seeds = 0

    for r in rounds:
        rid_short = r["round_id"][:8]
        print(f"Round {r['round_number']} ({rid_short})")

        round_score = 0.0
        round_count = 0

        for seed, af in sorted(r["seeds"].items()):
            with open(af) as f:
                analysis = json.load(f)
            gt = np.array(analysis["ground_truth"], dtype=np.float32)
            grid = np.array(analysis["initial_grid"], dtype=np.int32)
            H, W = grid.shape

            if args.blind or seed != 0:
                # No queries
                pred = predict(model, grid, device=device)
            else:
                # Simulate queries from ground truth (like C++ local test)
                obs_freq, obs_count, obs_mask = simulate_queries(
                    gt, grid, args.queries, rng)
                pred = predict(model, grid, obs_freq, obs_count, obs_mask, device=device)

            score = score_prediction(pred, gt)
            tag = "(blind)" if args.blind or seed != 0 else f"({args.queries}q)"
            print(f"  Seed {seed}: {score:.2f} {tag}")

            round_score += score
            round_count += 1
            total_score += score
            total_seeds += 1

        if round_count > 0:
            print(f"  Avg: {round_score / round_count:.2f}")
        print()

    if total_seeds > 0:
        print(f"{'='*40}")
        print(f"OVERALL: {total_score / total_seeds:.2f} avg across {total_seeds} seeds")


if __name__ == "__main__":
    main()

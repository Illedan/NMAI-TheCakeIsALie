#!/usr/bin/env python3
"""
Hill-climb MC simulator parameters to match observed query responses.

Runs MC sims on a 19x19 area (15x15 tile + 2 padding) via C++ --tune mode,
compares the distribution to the 50 observed queries, and tunes transition
multipliers to minimize KL divergence.

Usage:
  python3 tune_params.py predictions/round8_c5cdf100
"""

import argparse
import json
import subprocess
import random
import math
import os
import time
from pathlib import Path
from copy import deepcopy

SCRIPT_DIR = Path(__file__).parent
NUM_CLASSES = 6

TERRAIN_OCEAN = 10
TERRAIN_MOUNTAIN = 5


def terrain_to_class(t):
    return {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}.get(t, 0)


def build_empirical_dist(queries, initial_grid, vx, vy, vw, vh):
    """Build empirical probability distribution from query responses."""
    H, W = len(initial_grid), len(initial_grid[0])
    counts = {}

    for qr in queries:
        resp_grid = qr["response"]["grid"]
        for y in range(len(resp_grid)):
            for x in range(len(resp_grid[0])):
                gy, gx = vy + y, vx + x
                if gy >= H or gx >= W:
                    continue
                if (gy, gx) not in counts:
                    counts[(gy, gx)] = [0] * NUM_CLASSES
                c = terrain_to_class(resp_grid[y][x])
                counts[(gy, gx)][c] += 1

    empirical = {}
    for key, cnts in counts.items():
        total = sum(cnts)
        if total > 0:
            empirical[key] = [c / total for c in cnts]

    return empirical


def kl_divergence(p, q, floor=0.01):
    """KL(p || q) with floor."""
    kl = 0
    for i in range(len(p)):
        pi = max(p[i], floor)
        qi = max(q[i], floor)
        kl += pi * math.log(pi / qi)
    return kl


def entropy(p, floor=0.001):
    h = 0
    for pi in p:
        pi = max(pi, floor)
        h -= pi * math.log(pi)
    return h


def score_prediction(mc_dist, empirical, initial_grid):
    """Score MC distribution against empirical using entropy-weighted KL."""
    total_kl = 0
    total_weight = 0

    for (gy, gx), emp in empirical.items():
        t = initial_grid[gy][gx]
        if t == TERRAIN_OCEAN or t == TERRAIN_MOUNTAIN:
            continue

        mc = mc_dist.get((gy, gx))
        if mc is None:
            continue

        h = entropy(emp)
        w = max(h, 0.01)
        total_kl += w * kl_divergence(emp, mc)
        total_weight += w

    if total_weight == 0:
        return 0

    weighted_kl = total_kl / total_weight
    return 100 * math.exp(-3 * weighted_kl)


def run_mc_cpp(initial_grid, params, num_sims, tile_x, tile_y, tile_w, tile_h, pad=2):
    """Run MC simulation via C++ --tune mode and return distribution on tile."""
    H, W = len(initial_grid), len(initial_grid[0])

    px = max(0, tile_x - pad)
    py = max(0, tile_y - pad)
    pw = min(W, tile_x + tile_w + pad) - px
    ph = min(H, tile_y + tile_h + pad) - py

    solver_input = {
        "grid": initial_grid,
        "num_sims": num_sims,
        "params": params,
        "tile": {"x": tile_x, "y": tile_y, "w": tile_w, "h": tile_h},
        "pad": {"x": px, "y": py, "w": pw, "h": ph},
    }

    input_path = "/tmp/tune_input.json"
    output_path = "/tmp/tune_output.json"

    with open(input_path, "w") as f:
        json.dump(solver_input, f)

    solver_bin = SCRIPT_DIR / "astar"
    proc = subprocess.run(
        [str(solver_bin), "--tune", input_path, output_path],
        capture_output=True, text=True, timeout=60
    )

    if proc.returncode != 0:
        print(f"Solver error: {proc.stderr}")
        return None

    with open(output_path) as f:
        result = json.load(f)

    mc_dist = {}
    for entry in result:
        mc_dist[(entry["y"], entry["x"])] = entry["probs"]

    return mc_dist


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", help="Predictions directory (e.g. predictions/round8_c5cdf100)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--mc-sims", type=int, default=1000)
    parser.add_argument("--pad", type=int, default=2)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    initial = json.load(open(run_dir / f"seed_{args.seed}_initial.json"))
    queries = json.load(open(run_dir / f"seed_{args.seed}_queries.json"))

    grid = initial["grid"]
    vp = queries[0]["viewport"]
    vx, vy, vw, vh = vp["x"], vp["y"], vp["w"], vp["h"]

    print(f"Tile: ({vx}, {vy}) {vw}x{vh}")
    print(f"Queries: {len(queries)}")
    print(f"Pad: {args.pad} (sim area: {vw+2*args.pad}x{vh+2*args.pad})")

    empirical = build_empirical_dist(queries, grid, vx, vy, vw, vh)
    non_static = sum(1 for (gy,gx) in empirical if grid[gy][gx] not in (TERRAIN_OCEAN, TERRAIN_MOUNTAIN))
    print(f"Empirical cells: {len(empirical)} ({non_static} non-static)")

    # Print empirical stats by initial terrain
    terrain_names = {0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin", 4: "Forest", 11: "Plains"}
    class_names = ["Empty", "Settle", "Port", "Ruin", "Forest", "Mount"]
    by_terrain = {}
    for (gy, gx), probs in empirical.items():
        t = grid[gy][gx]
        if t == TERRAIN_OCEAN or t == TERRAIN_MOUNTAIN:
            continue
        if t not in by_terrain:
            by_terrain[t] = {"n": 0, "totals": [0.0] * NUM_CLASSES}
        by_terrain[t]["n"] += 1
        for c in range(NUM_CLASSES):
            by_terrain[t]["totals"][c] += probs[c]

    print("\n=== Empirical by initial terrain ===")
    for t in sorted(by_terrain.keys()):
        info = by_terrain[t]
        n = info["n"]
        avgs = [info["totals"][c]/n for c in range(NUM_CLASSES)]
        print(f"  {terrain_names.get(t, t):>10} (n={n:2d}): " +
              "  ".join(f"{class_names[c]}={avgs[c]:.3f}" for c in range(NUM_CLASSES)))

    # Default params (all multipliers = 1.0)
    best_params = {
        "settle_ruin_mult": 1.0,
        "empty_settle_mult": 1.0,
        "forest_settle_mult": 1.0,
        "ruin_rebuild_mult": 1.0,
        "settle_port_mult": 1.0,
        "port_ruin_mult": 1.0,
    }

    # Run baseline
    print("\n=== Running baseline (all mults = 1.0) ===")
    mc_dist = run_mc_cpp(grid, best_params, args.mc_sims, vx, vy, vw, vh, args.pad)
    if mc_dist is None:
        print("Failed to run C++ --tune mode. Aborting.")
        return

    best_score = score_prediction(mc_dist, empirical, grid)
    print(f"Baseline score: {best_score:.4f}")

    # Print MC stats by terrain for comparison
    print("\n=== MC baseline by initial terrain ===")
    by_terrain_mc = {}
    for (gy, gx), probs in mc_dist.items():
        t = grid[gy][gx]
        if t == TERRAIN_OCEAN or t == TERRAIN_MOUNTAIN:
            continue
        if t not in by_terrain_mc:
            by_terrain_mc[t] = {"n": 0, "totals": [0.0] * NUM_CLASSES}
        by_terrain_mc[t]["n"] += 1
        for c in range(NUM_CLASSES):
            by_terrain_mc[t]["totals"][c] += probs[c]

    for t in sorted(by_terrain_mc.keys()):
        info = by_terrain_mc[t]
        n = info["n"]
        avgs = [info["totals"][c]/n for c in range(NUM_CLASSES)]
        print(f"  {terrain_names.get(t, t):>10} (n={n:2d}): " +
              "  ".join(f"{class_names[c]}={avgs[c]:.3f}" for c in range(NUM_CLASSES)))

    # Hill climbing
    print(f"\n=== Hill climbing ({args.iterations} iterations) ===")
    param_keys = list(best_params.keys())
    step_size = 0.15  # initial perturbation
    no_improve = 0

    for it in range(args.iterations):
        # Pick a random parameter to perturb
        key = random.choice(param_keys)
        delta = random.uniform(-step_size, step_size)
        trial_params = deepcopy(best_params)
        trial_params[key] = max(0.3, min(3.0, trial_params[key] + delta))

        mc_dist = run_mc_cpp(grid, trial_params, args.mc_sims, vx, vy, vw, vh, args.pad)
        if mc_dist is None:
            continue

        score = score_prediction(mc_dist, empirical, grid)

        if score > best_score:
            improvement = score - best_score
            best_score = score
            best_params = trial_params
            no_improve = 0
            print(f"  [{it+1:3d}] {key}={trial_params[key]:.3f}  score={score:.4f} (+{improvement:.4f})")
        else:
            no_improve += 1

        # Shrink step size if stuck
        if no_improve >= 10:
            step_size = max(0.02, step_size * 0.8)
            no_improve = 0

    print(f"\n=== Final results ===")
    print(f"Best score: {best_score:.4f}")
    print(f"Best params:")
    for k, v in best_params.items():
        print(f"  {k}: {v:.4f}")

    # Run final MC with more sims for accurate comparison
    print(f"\n=== Final MC with 2000 sims ===")
    mc_dist = run_mc_cpp(grid, best_params, 2000, vx, vy, vw, vh, args.pad)
    if mc_dist:
        final_score = score_prediction(mc_dist, empirical, grid)
        print(f"Final score (2000 sims): {final_score:.4f}")

        print("\n=== Final MC by initial terrain ===")
        by_terrain_mc = {}
        for (gy, gx), probs in mc_dist.items():
            t = grid[gy][gx]
            if t == TERRAIN_OCEAN or t == TERRAIN_MOUNTAIN:
                continue
            if t not in by_terrain_mc:
                by_terrain_mc[t] = {"n": 0, "totals": [0.0] * NUM_CLASSES}
            by_terrain_mc[t]["n"] += 1
            for c in range(NUM_CLASSES):
                by_terrain_mc[t]["totals"][c] += probs[c]

        for t in sorted(by_terrain_mc.keys()):
            info = by_terrain_mc[t]
            n = info["n"]
            avgs = [info["totals"][c]/n for c in range(NUM_CLASSES)]
            emp_info = by_terrain.get(t)
            print(f"  {terrain_names.get(t, t):>10} (n={n:2d}): " +
                  "  ".join(f"{class_names[c]}={avgs[c]:.3f}" for c in range(NUM_CLASSES)))
            if emp_info:
                emp_avgs = [emp_info["totals"][c]/emp_info["n"] for c in range(NUM_CLASSES)]
                print(f"  {'(empirical)':>10}        : " +
                      "  ".join(f"{class_names[c]}={emp_avgs[c]:.3f}" for c in range(NUM_CLASSES)))

    # Save best params
    out_path = run_dir / "tuned_params.json"
    with open(out_path, "w") as f:
        json.dump({"score": best_score, "params": best_params}, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()

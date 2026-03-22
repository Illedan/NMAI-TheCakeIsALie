#!/usr/bin/env python3
"""
Generate training data for the ML model.

Two sources:
1. Real data: initial_states + ground_truth from completed rounds (9 rounds × 5 seeds = 45 samples)
2. Synthetic data: random TuneParams → run our C++ simulator many times → get probability tensors

Each training sample is saved as a .npz file containing:
  - initial_grid: (40, 40) int array — terrain codes
  - initial_onehot: (40, 40, 8) float — one-hot terrain channels
  - obs_freq: (40, 40, 6) float — empirical observed class frequencies (from queries)
  - obs_count: (40, 40) int — number of observations per cell
  - obs_mask: (40, 40) bool — whether cell was observed
  - target: (40, 40, 6) float — ground truth probability distribution
  - coast_dist: (40, 40) float — distance to nearest ocean cell
  - forest_dist: (40, 40) float — distance to nearest forest cell
  - settle_dist: (40, 40) float — distance to nearest initial settlement

For synthetic data, we also generate simulated queries by sampling from the target distribution.
"""

import json
import numpy as np
import subprocess
import sys
import os
from pathlib import Path
from scipy.ndimage import distance_transform_edt

SCRIPT_DIR = Path(__file__).parent
ASTAR_DIR = SCRIPT_DIR.parent
ISLAND_DIR = ASTAR_DIR.parent / "astar-island"
SOLVER_BIN = ASTAR_DIR / "astar"
DATA_DIR = SCRIPT_DIR / "data"

# Terrain codes
TERRAIN_EMPTY = 0
TERRAIN_SETTLEMENT = 1
TERRAIN_PORT = 2
TERRAIN_RUIN = 3
TERRAIN_FOREST = 4
TERRAIN_MOUNTAIN = 5
TERRAIN_OCEAN = 10
TERRAIN_PLAINS = 11

NUM_CLASSES = 6
MAX_VIEWPORT = 15


def terrain_to_class(t):
    return {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}.get(t, 0)


def make_initial_onehot(grid):
    """Convert terrain grid to one-hot channels."""
    H, W = grid.shape
    # 8 channels: ocean, plains/empty, settlement, port, ruin, forest, mountain, coast_adj
    onehot = np.zeros((H, W, 8), dtype=np.float32)
    onehot[:, :, 0] = (grid == TERRAIN_OCEAN).astype(np.float32)
    onehot[:, :, 1] = np.isin(grid, [TERRAIN_EMPTY, TERRAIN_PLAINS]).astype(np.float32)
    onehot[:, :, 2] = (grid == TERRAIN_SETTLEMENT).astype(np.float32)
    onehot[:, :, 3] = (grid == TERRAIN_PORT).astype(np.float32)
    onehot[:, :, 4] = (grid == TERRAIN_RUIN).astype(np.float32)
    onehot[:, :, 5] = (grid == TERRAIN_FOREST).astype(np.float32)
    onehot[:, :, 6] = (grid == TERRAIN_MOUNTAIN).astype(np.float32)

    # Coast adjacency
    from scipy.ndimage import binary_dilation
    ocean_mask = (grid == TERRAIN_OCEAN)
    dilated = binary_dilation(ocean_mask, structure=np.ones((3, 3)))
    onehot[:, :, 7] = (dilated & ~ocean_mask).astype(np.float32)
    return onehot


def make_distance_features(grid):
    """Compute distance-to-terrain features."""
    ocean_mask = (grid == TERRAIN_OCEAN)
    forest_mask = (grid == TERRAIN_FOREST)
    settle_mask = np.isin(grid, [TERRAIN_SETTLEMENT, TERRAIN_PORT])

    # Distance transform: distance from non-X to nearest X
    coast_dist = distance_transform_edt(~ocean_mask).astype(np.float32)
    forest_dist = distance_transform_edt(~forest_mask).astype(np.float32)
    settle_dist = distance_transform_edt(~settle_mask).astype(np.float32)

    # Normalize to [0, 1] range
    for arr in [coast_dist, forest_dist, settle_dist]:
        m = arr.max()
        if m > 0:
            arr /= m

    return coast_dist, forest_dist, settle_dist


def simulate_queries(target, initial_grid, n_queries, rng):
    """Simulate queries by sampling from ground truth distribution.

    Returns obs_freq, obs_count, obs_mask arrays.
    """
    H, W = initial_grid.shape
    vw = min(MAX_VIEWPORT, W)
    vh = min(MAX_VIEWPORT, H)

    obs_counts = np.zeros((H, W, NUM_CLASSES), dtype=np.int32)
    obs_total = np.zeros((H, W), dtype=np.int32)

    # Choose query positions: mix of random and best-tile
    positions = []
    for _ in range(n_queries):
        vx = rng.integers(0, W - vw + 1)
        vy = rng.integers(0, H - vh + 1)
        positions.append((vx, vy))

    for vx, vy in positions:
        for y in range(vy, vy + vh):
            for x in range(vx, vx + vw):
                # Sample a class from ground truth distribution
                probs = target[y, x]
                cls = rng.choice(NUM_CLASSES, p=probs)
                obs_counts[y, x, cls] += 1
                obs_total[y, x] += 1

    obs_mask = (obs_total > 0)
    obs_freq = np.zeros((H, W, NUM_CLASSES), dtype=np.float32)
    valid = obs_total > 0
    for c in range(NUM_CLASSES):
        obs_freq[:, :, c] = np.where(valid, obs_counts[:, :, c] / np.maximum(obs_total, 1), 0.0)

    return obs_freq, obs_total, obs_mask


def load_real_queries(query_file, H, W):
    """Load actual API query results into obs tensors."""
    with open(query_file) as f:
        queries = json.load(f)

    obs_counts = np.zeros((H, W, NUM_CLASSES), dtype=np.int32)
    obs_total = np.zeros((H, W), dtype=np.int32)

    for qr in queries:
        vp = qr["viewport"]
        vx, vy = vp["x"], vp["y"]
        grid = qr["response"]["grid"]
        for y in range(len(grid)):
            for x in range(len(grid[0])):
                gy, gx = vy + y, vx + x
                if gy < H and gx < W:
                    cls = terrain_to_class(grid[y][x])
                    obs_counts[gy, gx, cls] += 1
                    obs_total[gy, gx] += 1

    obs_mask = (obs_total > 0)
    obs_freq = np.zeros((H, W, NUM_CLASSES), dtype=np.float32)
    valid = obs_total > 0
    for c in range(NUM_CLASSES):
        obs_freq[:, :, c] = np.where(valid, obs_counts[:, :, c] / np.maximum(obs_total, 1), 0.0)

    return obs_freq, obs_total, obs_mask


def save_sample(path, initial_grid, initial_onehot, obs_freq, obs_count, obs_mask,
                target, coast_dist, forest_dist, settle_dist, round_id="", seed_idx=0):
    np.savez_compressed(
        path,
        initial_grid=initial_grid,
        initial_onehot=initial_onehot,
        obs_freq=obs_freq,
        obs_count=obs_count,
        obs_mask=obs_mask,
        target=target,
        coast_dist=coast_dist,
        forest_dist=forest_dist,
        settle_dist=settle_dist,
        round_id=round_id,
        seed_idx=seed_idx,
    )


def generate_real_data():
    """Generate training samples from real round data."""
    print("=== Generating real data ===")

    # Discover rounds with ground truth
    analysis_dir = ISLAND_DIR / "analysis"
    is_dirs = sorted((ISLAND_DIR / "initial_states").iterdir())

    # Map round_id -> initial_states dir
    round_to_is = {}
    for d in is_dirs:
        summary_path = d / "summary.json"
        if summary_path.exists():
            with open(summary_path) as f:
                s = json.load(f)
            rid = s.get("round_id", "")
            if rid and rid not in round_to_is:
                round_to_is[rid] = d

    # Map round_id -> analysis files per seed
    round_to_analysis = {}
    for af in sorted(analysis_dir.glob("*.json")):
        name = af.name
        # Extract round_id (UUID at end of filename)
        parts = name.replace(".json", "").split("_")
        # Find UUID (36 chars with dashes)
        for p in parts:
            if len(p) == 36 and p.count("-") == 4:
                rid = p
                break
        else:
            continue
        # Extract seed index
        for i, p in enumerate(parts):
            if p == "seed" and i + 1 < len(parts):
                seed = int(parts[i + 1])
                break
        else:
            continue
        if rid not in round_to_analysis:
            round_to_analysis[rid] = {}
        round_to_analysis[rid][seed] = af

    # Check for real query files
    pred_dir = ASTAR_DIR / "predictions"
    round_queries = {}  # round_id[:8] -> {seed: path}
    if pred_dir.exists():
        for d in pred_dir.iterdir():
            if not d.is_dir():
                continue
            for qf in d.glob("seed_*_queries.json"):
                seed = int(qf.name.split("_")[1])
                short_id = d.name.split("_")[1] if "_" in d.name else ""
                if short_id not in round_queries:
                    round_queries[short_id] = {}
                round_queries[short_id][seed] = qf

    real_dir = DATA_DIR / "real"
    real_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    count = 0

    for rid, analysis_seeds in sorted(round_to_analysis.items()):
        if rid not in round_to_is:
            print(f"  Skipping {rid[:8]}: no initial_states")
            continue

        is_dir = round_to_is[rid]
        short = rid[:8]

        for seed, af in sorted(analysis_seeds.items()):
            # Load analysis (ground truth)
            with open(af) as f:
                analysis = json.load(f)
            target = np.array(analysis["ground_truth"], dtype=np.float32)
            initial_grid = np.array(analysis["initial_grid"], dtype=np.int32)

            H, W = initial_grid.shape

            # Build features
            initial_onehot = make_initial_onehot(initial_grid)
            coast_dist, forest_dist, settle_dist = make_distance_features(initial_grid)

            # Check for real query data
            has_real_queries = short in round_queries and seed in round_queries[short]

            if has_real_queries:
                obs_freq, obs_count, obs_mask = load_real_queries(
                    round_queries[short][seed], H, W)
                tag = "real_queries"
            else:
                # Simulate queries from ground truth
                n_queries = rng.choice([10, 20, 30, 50])
                obs_freq, obs_count, obs_mask = simulate_queries(
                    target, initial_grid, n_queries, rng)
                tag = f"sim_{n_queries}q"

            out_path = real_dir / f"{short}_seed{seed}_{tag}.npz"
            save_sample(out_path, initial_grid, initial_onehot, obs_freq,
                        obs_count, obs_mask, target, coast_dist, forest_dist, settle_dist,
                        round_id=rid, seed_idx=seed)
            count += 1
            print(f"  {short} seed {seed}: {tag} -> {out_path.name}")

    print(f"  Generated {count} real samples")
    return count


def generate_augmented_data(n_augments_per_sample=5):
    """Generate augmented versions of real data with different query patterns.

    For each real sample, create multiple versions with:
    - Different numbers of queries (5, 10, 20, 50)
    - Different query positions (random, center, coastal, etc.)
    - This teaches the model to handle varying observation patterns.
    """
    print(f"\n=== Generating augmented data ({n_augments_per_sample} per sample) ===")

    analysis_dir = ISLAND_DIR / "analysis"
    is_dirs = sorted((ISLAND_DIR / "initial_states").iterdir())

    round_to_is = {}
    for d in is_dirs:
        summary_path = d / "summary.json"
        if summary_path.exists():
            with open(summary_path) as f:
                s = json.load(f)
            rid = s.get("round_id", "")
            if rid and rid not in round_to_is:
                round_to_is[rid] = d

    round_to_analysis = {}
    for af in sorted(analysis_dir.glob("*.json")):
        name = af.name
        parts = name.replace(".json", "").split("_")
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
        if rid not in round_to_analysis:
            round_to_analysis[rid] = {}
        round_to_analysis[rid][seed] = af

    aug_dir = DATA_DIR / "augmented"
    aug_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(123)
    count = 0

    query_configs = [
        (5, "sparse"),
        (10, "medium"),
        (20, "focused"),
        (50, "dense"),
        (0, "blind"),
    ]

    for rid, analysis_seeds in sorted(round_to_analysis.items()):
        if rid not in round_to_is:
            continue
        short = rid[:8]

        for seed, af in sorted(analysis_seeds.items()):
            with open(af) as f:
                analysis = json.load(f)
            target = np.array(analysis["ground_truth"], dtype=np.float32)
            initial_grid = np.array(analysis["initial_grid"], dtype=np.int32)
            H, W = initial_grid.shape

            initial_onehot = make_initial_onehot(initial_grid)
            coast_dist, forest_dist, settle_dist = make_distance_features(initial_grid)

            for aug_idx in range(n_augments_per_sample):
                n_queries, label = query_configs[aug_idx % len(query_configs)]

                if n_queries == 0:
                    obs_freq = np.zeros((H, W, NUM_CLASSES), dtype=np.float32)
                    obs_count = np.zeros((H, W), dtype=np.int32)
                    obs_mask = np.zeros((H, W), dtype=bool)
                else:
                    obs_freq, obs_count, obs_mask = simulate_queries(
                        target, initial_grid, n_queries, rng)

                out_path = aug_dir / f"{short}_seed{seed}_aug{aug_idx}_{label}_{n_queries}q.npz"
                save_sample(out_path, initial_grid, initial_onehot, obs_freq,
                            obs_count, obs_mask, target, coast_dist, forest_dist, settle_dist,
                            round_id=rid, seed_idx=seed)
                count += 1

        print(f"  {short}: {len(analysis_seeds)} seeds × {n_augments_per_sample} augments")

    print(f"  Generated {count} augmented samples")
    return count


def generate_synthetic_data(n_rounds=50):
    """Generate synthetic training data using our C++ simulator with random params.

    For each synthetic round:
    1. Pick a real initial grid (we reuse the 45 we have)
    2. Sample random TuneParams
    3. Run C++ MC simulation to get target probabilities
    4. Generate simulated queries
    """
    print(f"\n=== Generating {n_rounds} synthetic rounds ===")

    # We need the solver binary
    if not SOLVER_BIN.exists():
        print(f"  ERROR: {SOLVER_BIN} not found. Run 'make' first.")
        return 0

    # Collect all initial grids
    analysis_dir = ISLAND_DIR / "analysis"
    grids = []
    for af in sorted(analysis_dir.glob("*.json")):
        with open(af) as f:
            analysis = json.load(f)
        grids.append(np.array(analysis["initial_grid"], dtype=np.int32))

    if not grids:
        print("  No grids found")
        return 0

    syn_dir = DATA_DIR / "synthetic"
    syn_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(456)
    count = 0

    # Parameter ranges for random sampling (wider than HC ranges)
    param_ranges = {
        "es_base": (0.0005, 0.05),
        "es_ns_coeff": (0.05, 1.0),
        "sr_base": (0.02, 0.25),
        "sr_support": (0.01, 0.30),
        "fs_base": (0.001, 0.03),
        "sp_base": (0.005, 0.15),
        "ruin_settle": (0.1, 0.8),
        "ruin_empty": (0.1, 0.7),
    }

    for round_idx in range(n_rounds):
        # Pick a random real grid
        grid = grids[round_idx % len(grids)]
        H, W = grid.shape

        # Sample random params
        params = {}
        for key, (lo, hi) in param_ranges.items():
            params[key] = rng.uniform(lo, hi)

        # Write temp input for C++ solver
        tmp_input = "/tmp/ml_synth_input.json"
        tmp_output = "/tmp/ml_synth_output.json"

        solver_input = {
            "grid": grid.tolist(),
            "num_sims": 200,
            "params": params,
            "tile": {"x": 0, "y": 0, "w": W, "h": H},
            "pad": {"x": 0, "y": 0, "w": W, "h": H},
        }
        with open(tmp_input, "w") as f:
            json.dump(solver_input, f)

        # Run C++ MC to get target probabilities
        proc = subprocess.run(
            [str(SOLVER_BIN), "--tune", tmp_input, tmp_output],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            print(f"  Round {round_idx}: solver failed")
            continue

        # Parse output (list of {x, y, probs})
        with open(tmp_output) as f:
            result = json.load(f)

        target = np.full((H, W, NUM_CLASSES), 1.0 / NUM_CLASSES, dtype=np.float32)
        for entry in result:
            y, x = entry["y"], entry["x"]
            target[y, x] = np.array(entry["probs"], dtype=np.float32)

        # Force ocean/mountain
        for y in range(H):
            for x in range(W):
                t = grid[y, x]
                if t == TERRAIN_OCEAN:
                    target[y, x] = [1, 0, 0, 0, 0, 0]
                elif t == TERRAIN_MOUNTAIN:
                    target[y, x] = [0, 0, 0, 0, 0, 1]

        # Build features
        initial_onehot = make_initial_onehot(grid)
        coast_dist, forest_dist, settle_dist = make_distance_features(grid)

        # Simulate queries
        n_queries = rng.choice([5, 10, 20, 50])
        obs_freq, obs_count, obs_mask = simulate_queries(target, grid, n_queries, rng)

        out_path = syn_dir / f"syn_{round_idx:04d}_{n_queries}q.npz"
        save_sample(out_path, grid, initial_onehot, obs_freq, obs_count, obs_mask,
                    target, coast_dist, forest_dist, settle_dist,
                    round_id=f"synthetic_{round_idx}", seed_idx=0)
        count += 1

        if (round_idx + 1) % 10 == 0:
            print(f"  Generated {round_idx + 1}/{n_rounds} synthetic rounds")

    print(f"  Generated {count} synthetic samples")
    return count


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    n_real = generate_real_data()
    n_aug = generate_augmented_data(n_augments_per_sample=5)
    n_syn = generate_synthetic_data(n_rounds=50)

    print(f"\n{'='*50}")
    print(f"Total: {n_real} real + {n_aug} augmented + {n_syn} synthetic = {n_real + n_aug + n_syn} samples")
    print(f"Data directory: {DATA_DIR}")


if __name__ == "__main__":
    main()

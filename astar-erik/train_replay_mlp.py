#!/usr/bin/env python3
"""Train an MLP on per-step transition data from replays.

Instead of training on initial_state → final_state (50 steps), this trains
on per-step transitions: state_t → state_{t+1}. Then we compose 50 steps
to get the full prediction.

But for the cross-round MLP (which predicts final state from initial),
we still want initial→final. The key improvement here is:
1. More data: 560 replays × 50 steps ≈ many more samples
2. Better features: add global features (settlement count, density)
3. Per-step transition matrices that capture dynamics better

Actually, for direct use as a cross-round MLP replacement, we train
initial_state → final_state but with MORE replays (560 vs ~95 analysis files)
and richer features.
"""

import json
import os
import glob
import numpy as np
from collections import deque
from train_cross_mlp import (
    NUM_CLASSES, FEAT_DIM, HIDDEN, TERRAIN_MAP, terrain_to_class,
    extract_features, MLP
)

REPLAY_DIR = "../astar-island/simulations"
INITIAL_DIR = "../astar-island/initial_states"

# Extended feature dim: 14 local + 3 global = 17
EXT_FEAT_DIM = 17
EXT_HIDDEN = 96

def extract_extended_features(grid):
    """Extract features with global context."""
    H, W = grid.shape
    base_features = extract_features(grid)  # (H, W, 14)

    # Global features
    n_settle = 0
    n_land = 0
    n_forest = 0
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            if t != 10 and c != 5:
                n_land += 1
                if c in (1, 2):
                    n_settle += 1
                elif c == 4:
                    n_forest += 1

    settle_density = n_settle / max(n_land, 1)
    forest_ratio = n_forest / max(n_land, 1)
    settle_count_norm = min(n_settle / 80.0, 1.0)  # normalize to [0,1]

    # Extended features: (H, W, 17)
    ext = np.zeros((H, W, EXT_FEAT_DIM), dtype=np.float32)
    ext[:, :, :14] = base_features
    ext[:, :, 14] = settle_density
    ext[:, :, 15] = forest_ratio
    ext[:, :, 16] = settle_count_norm

    return ext


def collect_replay_data():
    """Collect initial→final training data from ALL replays."""
    X_all, Y_all = [], []

    # Find all replay directories
    sim_dirs = sorted(glob.glob(os.path.join(REPLAY_DIR, "*")))

    n_replays = 0
    for sim_dir in sim_dirs:
        replay_dir = os.path.join(sim_dir, "replays")
        if not os.path.isdir(replay_dir):
            continue

        replay_files = sorted(glob.glob(os.path.join(replay_dir, "*.json")))
        for rf in replay_files:
            try:
                with open(rf) as f:
                    data = json.load(f)

                frames = data["frames"]
                if len(frames) < 51:
                    continue

                # Initial grid (frame 0)
                init_grid = np.array(frames[0]["grid"])
                # Final grid (frame 50)
                final_grid = np.array(frames[50]["grid"])

                H, W = init_grid.shape
                features = extract_extended_features(init_grid)

                for y in range(H):
                    for x in range(W):
                        t = int(init_grid[y, x])
                        c = terrain_to_class(t)
                        if c == 5 or t == 10:  # mountain or ocean
                            continue

                        # Target: one-hot final class
                        final_c = terrain_to_class(int(final_grid[y, x]))
                        target = np.zeros(NUM_CLASSES, dtype=np.float32)
                        target[final_c] = 1.0

                        X_all.append(features[y, x])
                        Y_all.append(target)

                n_replays += 1

            except Exception as e:
                print(f"  Error: {e}")
                continue

        basename = os.path.basename(sim_dir)
        print(f"  {basename}: {len(replay_files)} replays processed")

    print(f"\nTotal: {n_replays} replays, {len(X_all)} cell samples")
    return np.array(X_all), np.array(Y_all)


def collect_replay_prob_data():
    """Collect initial→final_distribution training data.

    Instead of one-hot targets from individual replays,
    aggregate multiple replays per seed to get probability distributions.
    """
    X_all, Y_all = [], []

    sim_dirs = sorted(glob.glob(os.path.join(REPLAY_DIR, "*")))

    for sim_dir in sim_dirs:
        replay_dir = os.path.join(sim_dir, "replays")
        if not os.path.isdir(replay_dir):
            continue

        replay_files = sorted(glob.glob(os.path.join(replay_dir, "*.json")))

        # Group by seed
        seed_replays = {}
        for rf in replay_files:
            basename = os.path.basename(rf)
            # seed_0_replay_3.json → seed 0
            parts = basename.split("_")
            seed_idx = int(parts[1])
            if seed_idx not in seed_replays:
                seed_replays[seed_idx] = []
            seed_replays[seed_idx].append(rf)

        for seed_idx, rfs in seed_replays.items():
            if len(rfs) < 3:
                continue

            # Load initial grid from first replay
            with open(rfs[0]) as f:
                first_data = json.load(f)
            init_grid = np.array(first_data["frames"][0]["grid"])
            H, W = init_grid.shape
            features = extract_extended_features(init_grid)

            # Accumulate final class counts across replays
            counts = np.zeros((H, W, NUM_CLASSES), dtype=np.float32)
            n_valid = 0

            for rf in rfs:
                try:
                    with open(rf) as f:
                        data = json.load(f)
                    final_grid = np.array(data["frames"][50]["grid"])
                    for y in range(H):
                        for x in range(W):
                            fc = terrain_to_class(int(final_grid[y, x]))
                            counts[y, x, fc] += 1
                    n_valid += 1
                except:
                    continue

            if n_valid < 3:
                continue

            # Convert counts to probabilities
            probs = counts / n_valid

            for y in range(H):
                for x in range(W):
                    t = int(init_grid[y, x])
                    c = terrain_to_class(t)
                    if c == 5 or t == 10:
                        continue
                    X_all.append(features[y, x])
                    Y_all.append(probs[y, x])

        basename = os.path.basename(sim_dir)
        print(f"  {basename}: {len(seed_replays)} seeds")

    print(f"\nTotal: {len(X_all)} cell samples (probability targets)")
    return np.array(X_all), np.array(Y_all)


def train_and_export(X, Y, name, path, prefix, feat_dim, hidden):
    """Train MLP and export weights."""
    print(f"\n=== Training {name} MLP ===")
    print(f"Dataset: {X.shape[0]} cells, {X.shape[1]} features")

    y_hard = Y.argmax(axis=1)
    for c in range(NUM_CLASSES):
        n = (y_hard == c).sum()
        print(f"  Class {c}: {n} ({100*n/len(y_hard):.1f}%)")

    idx = np.random.permutation(len(X))
    split = int(0.9 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    Y_train, Y_val = Y[idx[:split]], Y[idx[split:]]

    model = MLP(feat_dim, hidden, NUM_CLASSES)
    model.weight_decay = 1e-4
    batch_size = 512
    n_epochs = 300
    best_val_loss = float('inf')
    best_weights = None
    patience = 0

    for epoch in range(n_epochs):
        perm = np.random.permutation(len(X_train))
        X_train = X_train[perm]
        Y_train = Y_train[perm]
        lr = 0.001 * (1.0 - 0.5 * epoch / n_epochs)

        train_loss = 0
        n_batches = 0
        for i in range(0, len(X_train), batch_size):
            loss = model.train_step(X_train[i:i+batch_size], Y_train[i:i+batch_size], lr)
            train_loss += loss
            n_batches += 1
        train_loss /= n_batches

        val_probs, _, _ = model.forward(X_val)
        eps = 1e-8
        val_loss = np.mean(np.sum(Y_val * np.log((Y_val + eps) / (val_probs + eps)), axis=1))

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = (model.w1.copy(), model.b1.copy(),
                          model.w2.copy(), model.b2.copy(),
                          model.w3.copy(), model.b3.copy())
            patience = 0
        else:
            patience += 1

        if epoch % 20 == 0:
            print(f"Epoch {epoch}: train={train_loss:.4f} val={val_loss:.4f}")

        if patience > 50:
            print(f"Early stopping at epoch {epoch}")
            break

    model.w1, model.b1, model.w2, model.b2, model.w3, model.b3 = best_weights
    print(f"Best val loss: {best_val_loss:.4f}")
    model.export_cpp(path, prefix=prefix)
    print(f"Exported to {path}")
    return best_val_loss


def collect_analysis_data_ext():
    """Collect analysis data with extended features."""
    from train_cross_mlp import ANALYSIS_DIR, load_analysis, load_initial

    X_all, Y_all = [], []

    round_dirs = {}
    for d in sorted(glob.glob(os.path.join(INITIAL_DIR, "*"))):
        if os.path.isdir(d):
            round_dirs[os.path.basename(d)] = d

    analysis_files = sorted(glob.glob(os.path.join(ANALYSIS_DIR, "*.json")))
    processed = set()

    for af in analysis_files:
        basename = os.path.basename(af)
        parts = basename.replace(".json", "").split("_")
        seed_idx = int(parts[parts.index("seed") + 1])
        seed_pos = basename.index("seed_") + len(f"seed_{seed_idx}_")
        round_id = basename[seed_pos:].replace(".json", "")

        key = (round_id, seed_idx)
        if key in processed:
            continue
        processed.add(key)

        init_path = None
        for rd_key, rd_path in round_dirs.items():
            if round_id in rd_key:
                init_file = os.path.join(rd_path, f"seed_{seed_idx}.json")
                if os.path.exists(init_file):
                    init_path = init_file
                    break
        if init_path is None:
            for rd_key, rd_path in round_dirs.items():
                if round_id[:8] in rd_key:
                    init_file = os.path.join(rd_path, f"seed_{seed_idx}.json")
                    if os.path.exists(init_file):
                        init_path = init_file
                        break
        if init_path is None:
            continue

        try:
            gt = load_analysis(af)
            grid = load_initial(init_path)
            features = extract_extended_features(grid)

            H, W = grid.shape
            for y in range(H):
                for x in range(W):
                    t = int(grid[y, x])
                    c = terrain_to_class(t)
                    if c == 5 or t == 10:
                        continue
                    X_all.append(features[y, x])
                    Y_all.append(gt[y, x])
        except Exception as e:
            print(f"  Error: {e}")
            continue

    print(f"Collected {len(X_all)} cells from {len(processed)} round-seeds")
    return np.array(X_all), np.array(Y_all)


def main():
    np.random.seed(42)

    print("=" * 60)
    print("Collecting analysis data with extended features...")
    print("=" * 60)
    X_ext, Y_ext = collect_analysis_data_ext()

    if len(X_ext) > 0:
        # Train 14-feat on analysis data (baseline comparison)
        train_and_export(
            X_ext[:, :14], Y_ext,
            "analysis (14 feat)", "cross_mlp_weights.h", "cross",
            FEAT_DIM, HIDDEN)

        # Train 17-feat on analysis data
        train_and_export(
            X_ext, Y_ext,
            "analysis (17 feat)", "cross_mlp_ext_weights.h", "crossext",
            EXT_FEAT_DIM, EXT_HIDDEN)


if __name__ == "__main__":
    main()

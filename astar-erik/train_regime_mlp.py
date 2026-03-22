#!/usr/bin/env python3
"""Train regime-specific cross-round MLPs.

Classifies rounds into regimes based on ground truth settlement patterns,
then trains separate MLPs for each regime.

Regime classification from ground truth:
- "localized": settlement probability concentrated near initial settlements (steep d3/d1)
- "diffuse": settlement probability spread broadly across map
- "collapse": settlement probability decreases (fewer settlements than initial)

Outputs: Two C++ headers with pre-trained weights.
"""

import json
import os
import glob
import numpy as np
from collections import deque
from train_cross_mlp import (
    ANALYSIS_DIR, INITIAL_DIR, NUM_CLASSES, FEAT_DIM, HIDDEN,
    TERRAIN_MAP, terrain_to_class, load_analysis, load_initial,
    extract_features, MLP
)

def classify_round(gt, grid):
    """Classify a round's regime from ground truth.
    Returns (regime, d3d1_ratio, growth_ratio)."""
    H, W = grid.shape

    # BFS distance from initial settlements
    dist = np.full((H, W), 999, dtype=int)
    queue = deque()
    init_settle = 0
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            if t in (1, 2, 3):  # settlement, port, ruin
                dist[y, x] = 0
                queue.append((y, x))
            if t in (1, 2):
                init_settle += 1
    while queue:
        cy, cx = queue.popleft()
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dy == 0 and dx == 0: continue
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < H and 0 <= nx < W:
                    nd = dist[cy, cx] + 1
                    if nd < dist[ny, nx]:
                        dist[ny, nx] = nd
                        queue.append((ny, nx))

    # Compute settlement probability at different distances
    settle_at_d = {}
    count_at_d = {}
    total_settle_prob = 0
    total_land = 0
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            if t == 10 or c == 5:  # ocean or mountain
                continue
            d = min(dist[y, x], 15)
            if d not in settle_at_d:
                settle_at_d[d] = 0.0
                count_at_d[d] = 0
            settle_at_d[d] += gt[y, x, 1] + gt[y, x, 2]  # settle + port
            count_at_d[d] += 1
            total_settle_prob += gt[y, x, 1] + gt[y, x, 2]
            total_land += 1

    # d3/d1 ratio
    frac_d1 = settle_at_d.get(1, 0) / max(count_at_d.get(1, 1), 1)
    frac_d3 = settle_at_d.get(3, 0) / max(count_at_d.get(3, 1), 1)
    d3d1 = frac_d3 / max(frac_d1, 0.01)

    # Growth ratio
    gt_settle_frac = total_settle_prob / max(total_land, 1)
    init_settle_frac = init_settle / max(total_land, 1)
    growth_ratio = gt_settle_frac / max(init_settle_frac, 0.01)

    if growth_ratio < 0.5:
        regime = "collapse"
    elif d3d1 < 0.15:
        regime = "localized"
    else:
        regime = "diffuse"

    return regime, d3d1, growth_ratio

def collect_classified_data():
    """Collect data classified by regime."""
    regime_data = {"localized": ([], []), "diffuse": ([], []), "collapse": ([], [])}

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
            features = extract_features(grid)
            regime, d3d1, gr = classify_round(gt, grid)

            H, W = grid.shape
            X_round, Y_round = [], []
            for y in range(H):
                for x in range(W):
                    t = int(grid[y, x])
                    c = terrain_to_class(t)
                    if c == 5 or t == 10:
                        continue
                    X_round.append(features[y, x])
                    Y_round.append(gt[y, x])

            regime_data[regime][0].extend(X_round)
            regime_data[regime][1].extend(Y_round)
            print(f"  {round_id[:8]} seed{seed_idx}: {regime} (d3d1={d3d1:.3f} gr={gr:.2f}) {len(X_round)} cells")

        except Exception as e:
            print(f"  Error: {e}")
            continue

    return regime_data

def train_and_export(X, Y, name, path, prefix="cross"):
    """Train MLP and export weights."""
    X, Y = np.array(X), np.array(Y)
    print(f"\n=== Training {name} MLP ===")
    print(f"Dataset: {X.shape[0]} cells")

    y_hard = Y.argmax(axis=1)
    for c in range(NUM_CLASSES):
        n = (y_hard == c).sum()
        print(f"  Class {c}: {n} ({100*n/len(y_hard):.1f}%)")

    idx = np.random.permutation(len(X))
    split = int(0.9 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    Y_train, Y_val = Y[idx[:split]], Y[idx[split:]]

    model = MLP(FEAT_DIM, HIDDEN, NUM_CLASSES)
    model.weight_decay = 1e-5
    batch_size = 256
    n_epochs = 400
    best_val_loss = float('inf')
    best_weights = None

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

        if epoch % 20 == 0:
            print(f"Epoch {epoch}: train={train_loss:.4f} val={val_loss:.4f}")

    model.w1, model.b1, model.w2, model.b2, model.w3, model.b3 = best_weights
    print(f"Best val loss: {best_val_loss:.4f}")
    model.export_cpp(path, prefix=prefix)
    print(f"Exported to {path}")
    return best_val_loss

def main():
    np.random.seed(42)
    print("Collecting and classifying training data...")
    regime_data = collect_classified_data()

    for regime, (X, Y) in regime_data.items():
        print(f"\n{regime}: {len(X)} cells")

    # Skip overall — trained separately by train_cross_mlp.py

    # Train localized (for burst growth rounds like R7/R12)
    if len(regime_data["localized"][0]) > 100:
        train_and_export(
            regime_data["localized"][0], regime_data["localized"][1],
            "localized", "cross_mlp_local_weights.h", "local")

    # Train diffuse growth
    if len(regime_data["diffuse"][0]) > 100:
        train_and_export(
            regime_data["diffuse"][0], regime_data["diffuse"][1],
            "diffuse", "cross_mlp_diffuse_weights.h", "diffuse")

    # Train collapse
    if len(regime_data["collapse"][0]) > 100:
        train_and_export(
            regime_data["collapse"][0], regime_data["collapse"][1],
            "collapse", "cross_mlp_collapse_weights.h", "collapse")

if __name__ == "__main__":
    main()

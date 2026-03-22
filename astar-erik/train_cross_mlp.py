#!/usr/bin/env python3
"""Train a cross-round MLP on ALL ground truth analysis data.

Features per cell (from initial grid only, no query data needed):
  0-4: initial terrain one-hot (empty, settle, port, ruin, forest)
  5: settlement neighbor count / 8
  6: forest neighbor count / 8
  7: ruin neighbor count / 8
  8: settle r2 density / 16
  9: ocean adjacency
  10: BFS distance from settlements / 15
  11: mountain neighbor fraction / 8
  12: land connectivity / 8
  13: plains neighbor fraction / 8

Target: 6-class probability distribution from ground truth

Outputs: C++ header with pre-trained weights.
"""

import json
import os
import glob
import numpy as np
from collections import deque

ANALYSIS_DIR = "../astar-island/analysis"
INITIAL_DIR = "../astar-island/initial_states"
NUM_CLASSES = 6
FEAT_DIM = 14  # Local features only (no global — causes round overfitting)
HIDDEN = 96

TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}

def terrain_to_class(t):
    return TERRAIN_MAP.get(t, 0)

def load_analysis(path):
    with open(path) as f:
        data = json.load(f)
    gt = data["ground_truth"]
    H, W = len(gt), len(gt[0])
    # GT is [y][x][class] probabilities
    gt_arr = np.zeros((H, W, NUM_CLASSES))
    for y in range(H):
        for x in range(W):
            for c in range(NUM_CLASSES):
                gt_arr[y, x, c] = gt[y][x][c]
    return gt_arr

def load_initial(path):
    with open(path) as f:
        data = json.load(f)
    grid = data["grid"]
    H, W = len(grid), len(grid[0])
    return np.array(grid)

def extract_features(grid):
    """Extract per-cell features from initial grid."""
    H, W = grid.shape
    features = np.zeros((H, W, FEAT_DIM), dtype=np.float32)

    # BFS distance from settlements
    dist = np.full((H, W), 999, dtype=int)
    queue = deque()
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            if t in (1, 2, 3):  # settlement, port, ruin
                dist[y, x] = 0
                queue.append((y, x))
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


    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)

            # One-hot terrain
            for i in range(5):
                features[y, x, i] = 1.0 if c == i else 0.0

            # Neighbor counts
            ns = nf = nr = nm = np_ = 0
            n_land = 0
            has_ocean = False
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if dy == 0 and dx == 0: continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W:
                        nc = terrain_to_class(int(grid[ny, nx]))
                        if nc in (1, 2): ns += 1
                        elif nc == 4: nf += 1
                        elif nc == 3: nr += 1
                        if nc == 5: nm += 1
                        if int(grid[ny, nx]) == 10: has_ocean = True
                        if int(grid[ny, nx]) == 11: np_ += 1
                        if int(grid[ny, nx]) != 10 and nc != 5: n_land += 1

            # r2 settle density
            sr2 = 0
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if abs(dy) <= 1 and abs(dx) <= 1: continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W:
                        nc = terrain_to_class(int(grid[ny, nx]))
                        if nc in (1, 2): sr2 += 1

            features[y, x, 5] = ns / 8.0
            features[y, x, 6] = nf / 8.0
            features[y, x, 7] = nr / 8.0
            features[y, x, 8] = sr2 / 16.0
            features[y, x, 9] = 1.0 if has_ocean else 0.0
            features[y, x, 10] = min(dist[y, x], 15) / 15.0
            features[y, x, 11] = nm / 8.0
            features[y, x, 12] = n_land / 8.0
            features[y, x, 13] = np_ / 8.0

    return features

def collect_data():
    """Collect all training data from analysis files."""
    X_all, Y_all = [], []

    # Find all round directories for initial states
    round_dirs = {}
    for d in sorted(glob.glob(os.path.join(INITIAL_DIR, "*"))):
        if os.path.isdir(d):
            round_id = os.path.basename(d)
            round_dirs[round_id] = d

    # Process each analysis file
    analysis_files = sorted(glob.glob(os.path.join(ANALYSIS_DIR, "*.json")))
    processed = set()

    for af in analysis_files:
        basename = os.path.basename(af)
        # Extract seed index and round_id from filename
        # Format: 03_10_00_analysis_seed_0_75e625c3-60cb-4392-af3e-c86a98bde8c2.json
        parts = basename.replace(".json", "").split("_")
        seed_idx = int(parts[parts.index("seed") + 1])
        # Round ID is everything after seed_N_
        seed_pos = basename.index("seed_") + len(f"seed_{seed_idx}_")
        round_id = basename[seed_pos:].replace(".json", "")

        key = (round_id, seed_idx)
        if key in processed:
            continue
        processed.add(key)

        # Find initial state
        init_path = None
        for rd_key, rd_path in round_dirs.items():
            if round_id in rd_key:
                init_file = os.path.join(rd_path, f"seed_{seed_idx}.json")
                if os.path.exists(init_file):
                    init_path = init_file
                    break

        if init_path is None:
            # Try matching by round_id prefix
            for rd_key, rd_path in round_dirs.items():
                short_id = round_id[:8]
                if short_id in rd_key:
                    init_file = os.path.join(rd_path, f"seed_{seed_idx}.json")
                    if os.path.exists(init_file):
                        init_path = init_file
                        break

        if init_path is None:
            print(f"  No initial state for {round_id} seed {seed_idx}")
            continue

        try:
            gt = load_analysis(af)
            grid = load_initial(init_path)
            features = extract_features(grid)

            H, W = grid.shape
            for y in range(H):
                for x in range(W):
                    t = int(grid[y, x])
                    c = terrain_to_class(t)
                    if c == 5:  # mountain - skip
                        continue
                    if t == 10:  # ocean - skip
                        continue

                    X_all.append(features[y, x])
                    Y_all.append(gt[y, x])

        except Exception as e:
            print(f"  Error loading {af}: {e}")
            continue

    print(f"Collected {len(X_all)} cells from {len(processed)} round-seeds")
    return np.array(X_all), np.array(Y_all)

class MLP:
    def __init__(self, feat_dim, hidden, out_dim):
        self.feat_dim = feat_dim
        self.hidden = hidden
        self.out_dim = out_dim
        scale1 = np.sqrt(2.0 / feat_dim)
        scale2 = np.sqrt(2.0 / hidden)
        scale3 = np.sqrt(2.0 / hidden)
        self.w1 = np.random.randn(hidden, feat_dim).astype(np.float32) * scale1
        self.b1 = np.zeros(hidden, dtype=np.float32)
        self.w2 = np.random.randn(hidden, hidden).astype(np.float32) * scale2
        self.b2 = np.zeros(hidden, dtype=np.float32)
        self.w3 = np.random.randn(out_dim, hidden).astype(np.float32) * scale3
        self.b3 = np.zeros(out_dim, dtype=np.float32)
        # Adam state
        self._params = ['w1', 'b1', 'w2', 'b2', 'w3', 'b3']
        self._m = {k: np.zeros_like(getattr(self, k)) for k in self._params}
        self._v = {k: np.zeros_like(getattr(self, k)) for k in self._params}
        self._t = 0

    def forward(self, X):
        """Batch forward: X is (N, feat_dim)"""
        h1 = np.maximum(0, X @ self.w1.T + self.b1)
        h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
        logits = h2 @ self.w3.T + self.b3
        # Softmax
        logits -= logits.max(axis=1, keepdims=True)
        exp_l = np.exp(logits)
        probs = exp_l / exp_l.sum(axis=1, keepdims=True)
        return probs, h1, h2

    def train_step(self, X, Y, lr, weights=None):
        """Train on batch. Y is (N, 6) probability targets. Uses KL divergence loss."""
        N = X.shape[0]
        probs, h1, h2 = self.forward(X)

        # KL divergence loss: sum_c Y_c * log(Y_c / pred_c)
        # Gradient w.r.t. logits: pred - Y (same as cross-entropy with soft targets)
        eps = 1e-8
        per_sample_loss = np.sum(Y * np.log((Y + eps) / (probs + eps)), axis=1)
        if weights is not None:
            loss = np.sum(per_sample_loss * weights) / np.sum(weights)
        else:
            loss = np.mean(per_sample_loss)

        # Gradient of softmax output
        if weights is not None:
            w_sum = np.sum(weights)
            d_logits = (probs - Y) * weights[:, None] / w_sum  # (N, out_dim)
        else:
            d_logits = (probs - Y) / N  # (N, out_dim)

        # Layer 3
        dw3 = d_logits.T @ h2  # (out_dim, hidden)
        db3 = d_logits.sum(axis=0)
        dh2 = d_logits @ self.w3  # (N, hidden)

        # ReLU
        dh2 *= (h2 > 0)

        # Layer 2
        dw2 = dh2.T @ h1  # (hidden, hidden)
        db2 = dh2.sum(axis=0)
        dh1 = dh2 @ self.w2  # (N, hidden)

        # ReLU
        dh1 *= (h1 > 0)

        # Layer 1
        dw1 = dh1.T @ X  # (hidden, feat_dim)
        db1 = dh1.sum(axis=0)

        # Adam update with weight decay
        grads = {'w1': dw1, 'b1': db1, 'w2': dw2, 'b2': db2, 'w3': dw3, 'b3': db3}
        self._t += 1
        beta1, beta2, eps_adam = 0.9, 0.999, 1e-8
        wd = getattr(self, 'weight_decay', 0.0)
        for k in self._params:
            g = grads[k]
            if wd > 0 and 'w' in k:
                g = g + wd * getattr(self, k)
            self._m[k] = beta1 * self._m[k] + (1 - beta1) * g
            self._v[k] = beta2 * self._v[k] + (1 - beta2) * g**2
            m_hat = self._m[k] / (1 - beta1**self._t)
            v_hat = self._v[k] / (1 - beta2**self._t)
            setattr(self, k, getattr(self, k) - lr * m_hat / (np.sqrt(v_hat) + eps_adam))

        return loss

    def export_cpp(self, path, prefix="cross"):
        """Export weights as C++ header."""
        P = prefix.upper()
        p = prefix.lower()
        with open(path, 'w') as f:
            f.write("#pragma once\n")
            f.write("// Auto-generated cross-round MLP weights\n")
            f.write(f"// Trained on all available ground truth data\n\n")
            f.write(f"static constexpr int {P}_FEAT_DIM = {self.feat_dim};\n")
            f.write(f"static constexpr int {P}_HIDDEN = {self.hidden};\n")
            f.write(f"static constexpr int {P}_OUT = {self.out_dim};\n\n")

            def write_array(name, arr):
                flat = arr.flatten()
                f.write(f"static const float {name}[] = {{\n")
                for i in range(0, len(flat), 8):
                    chunk = flat[i:i+8]
                    f.write("    " + ", ".join(f"{v:.6f}f" for v in chunk) + ",\n")
                f.write("};\n\n")

            write_array(f"{p}_w1", self.w1)
            write_array(f"{p}_b1", self.b1)
            write_array(f"{p}_w2", self.w2)
            write_array(f"{p}_b2", self.b2)
            write_array(f"{p}_w3", self.w3)
            write_array(f"{p}_b3", self.b3)

def main():
    np.random.seed(42)

    print("Collecting training data...")
    X, Y = collect_data()
    print(f"Dataset: {X.shape[0]} cells, {X.shape[1]} features, {Y.shape[1]} classes")

    # Class distribution
    y_hard = Y.argmax(axis=1)
    for c in range(NUM_CLASSES):
        n = (y_hard == c).sum()
        print(f"  Class {c}: {n} ({100*n/len(y_hard):.1f}%)")

    # Shuffle and split (90/10)
    idx = np.random.permutation(len(X))
    split = int(0.9 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    Y_train, Y_val = Y[idx[:split]], Y[idx[split:]]

    model = MLP(FEAT_DIM, HIDDEN, NUM_CLASSES)
    model.weight_decay = 1e-4

    batch_size = 256
    n_epochs = 400
    best_val_loss = float('inf')
    best_weights = None

    for epoch in range(n_epochs):
        # Shuffle training data
        perm = np.random.permutation(len(X_train))
        X_train = X_train[perm]
        Y_train = Y_train[perm]

        lr = 0.001 * (1.0 - 0.5 * epoch / n_epochs)

        train_loss = 0
        n_batches = 0
        for i in range(0, len(X_train), batch_size):
            batch_x = X_train[i:i+batch_size]
            batch_y = Y_train[i:i+batch_size]
            loss = model.train_step(batch_x, batch_y, lr)
            train_loss += loss
            n_batches += 1
        train_loss /= n_batches

        # Validation
        val_probs, _, _ = model.forward(X_val)
        eps = 1e-8
        val_loss = np.mean(np.sum(Y_val * np.log((Y_val + eps) / (val_probs + eps)), axis=1))

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = (model.w1.copy(), model.b1.copy(),
                          model.w2.copy(), model.b2.copy(),
                          model.w3.copy(), model.b3.copy())

        if epoch % 5 == 0:
            print(f"Epoch {epoch}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} lr={lr:.4f}")

    # Restore best weights
    model.w1, model.b1, model.w2, model.b2, model.w3, model.b3 = best_weights
    print(f"\nBest val loss: {best_val_loss:.4f}")

    # Export
    model.export_cpp("cross_mlp_weights.h")
    print(f"Exported weights to cross_mlp_weights.h")

if __name__ == "__main__":
    main()

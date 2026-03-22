#!/usr/bin/env python3
"""Train MLP v5: growth_ratio (log-scaled) + d3d1 + ruin_frac as global features.

Key improvements over v3:
- growth_ratio uses log(1+gr)/log(16) instead of min(gr,3)/3 (preserves info for gr>3)
- Added ruin_fraction as 3rd global feature to capture death-decay dynamics
- 500 epochs, wd=5e-5 (from hyperparameter search)
"""

import json
import os
import glob
import math
import numpy as np
from collections import deque

ANALYSIS_DIR = "../astar-island/analysis"
INITIAL_DIR = "../astar-island/initial_states"
NUM_CLASSES = 6
LOCAL_FEAT_DIM = 14
GLOBAL_FEAT_DIM = 3  # growth_ratio, d3d1, ruin_frac
FEAT_DIM = LOCAL_FEAT_DIM + GLOBAL_FEAT_DIM
HIDDEN = 96

TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}

def terrain_to_class(t):
    return TERRAIN_MAP.get(t, 0)

def load_analysis(path):
    with open(path) as f:
        data = json.load(f)
    gt = data["ground_truth"]
    H, W = len(gt), len(gt[0])
    gt_arr = np.zeros((H, W, NUM_CLASSES))
    for y in range(H):
        for x in range(W):
            for c in range(NUM_CLASSES):
                gt_arr[y, x, c] = gt[y][x][c]
    return gt_arr

def load_initial(path):
    with open(path) as f:
        data = json.load(f)
    return np.array(data["grid"])

def compute_settle_dist(grid):
    H, W = grid.shape
    dist = np.full((H, W), 999, dtype=int)
    queue = deque()
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            if t in (1, 2, 3):
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
    return dist

def extract_local_features(grid):
    H, W = grid.shape
    features = np.zeros((H, W, LOCAL_FEAT_DIM), dtype=np.float32)
    dist = compute_settle_dist(grid)
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            for i in range(5):
                features[y, x, i] = 1.0 if c == i else 0.0
            ns = nf = nr = nm = np_ = 0
            n_land = 0; has_ocean = False
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


def compute_global_features(grid, gt):
    """Compute growth_ratio, d3d1, and ruin_fraction from initial grid and ground truth."""
    H, W = grid.shape
    dist = compute_settle_dist(grid)

    init_s = land = 0
    obs_s = obs_land = 0
    ruin_sum = 0
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            if t == 10 or c == 5: continue
            land += 1
            if c in (1, 2): init_s += 1
            settle_prob = gt[y, x, 1] + gt[y, x, 2]
            obs_s += settle_prob
            obs_land += 1
            ruin_sum += gt[y, x, 3]

    init_frac = init_s / max(land, 1)
    obs_frac = obs_s / max(obs_land, 1)
    growth_ratio = obs_frac / max(init_frac, 0.01)
    ruin_frac = ruin_sum / max(obs_land, 1)

    # d3d1_ratio
    frac_at_d = {}
    total_at_d = {}
    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            if t == 10 or c == 5: continue
            d = min(dist[y, x], 7)
            if d not in total_at_d:
                total_at_d[d] = 0
                frac_at_d[d] = 0
            total_at_d[d] += 1
            frac_at_d[d] += gt[y, x, 1] + gt[y, x, 2]

    f1 = frac_at_d.get(1, 0) / max(total_at_d.get(1, 1), 1)
    f3 = frac_at_d.get(3, 0) / max(total_at_d.get(3, 1), 1)
    d3d1 = f3 / max(f1, 0.01)

    return growth_ratio, d3d1, ruin_frac


def normalize_global(growth_ratio, d3d1, ruin_frac):
    """Normalize global features to ~[0,1] range."""
    return np.array([
        math.log(1 + growth_ratio) / math.log(16),  # 0 → 0, 1 → 0.25, 3 → 0.50, 15 → 1.0
        min(d3d1, 1.0),
        min(ruin_frac * 10.0, 1.0),  # ruin_frac typically 0-0.1, scale to 0-1
    ], dtype=np.float32)


def collect_data():
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
            if round_id in rd_key or round_id[:8] in rd_key:
                init_file = os.path.join(rd_path, f"seed_{seed_idx}.json")
                if os.path.exists(init_file):
                    init_path = init_file
                    break
        if init_path is None:
            continue

        try:
            gt = load_analysis(af)
            grid = load_initial(init_path)
            local_features = extract_local_features(grid)
            growth_ratio, d3d1, ruin_frac = compute_global_features(grid, gt)
            global_feats = normalize_global(growth_ratio, d3d1, ruin_frac)

            print(f"  {os.path.basename(af)[:40]}: gr={growth_ratio:.2f} d3d1={d3d1:.3f} ruin={ruin_frac:.4f}"
                  f" → norm=[{global_feats[0]:.3f}, {global_feats[1]:.3f}, {global_feats[2]:.3f}]")

            H, W = grid.shape
            for y in range(H):
                for x in range(W):
                    t = int(grid[y, x])
                    c = terrain_to_class(t)
                    if c == 5 or t == 10:
                        continue
                    cell_feat = np.concatenate([local_features[y, x], global_feats])
                    X_all.append(cell_feat)
                    Y_all.append(gt[y, x])
        except Exception as e:
            print(f"  Error: {e}")

    print(f"Collected {len(X_all)} cells from {len(processed)} round-seeds")
    return np.array(X_all), np.array(Y_all)


class MLP:
    def __init__(self, feat_dim, hidden, out_dim):
        self.feat_dim = feat_dim
        self.hidden = hidden
        self.out_dim = out_dim
        self.w1 = np.random.randn(hidden, feat_dim).astype(np.float32) * np.sqrt(2.0 / feat_dim)
        self.b1 = np.zeros(hidden, dtype=np.float32)
        self.w2 = np.random.randn(hidden, hidden).astype(np.float32) * np.sqrt(2.0 / hidden)
        self.b2 = np.zeros(hidden, dtype=np.float32)
        self.w3 = np.random.randn(out_dim, hidden).astype(np.float32) * np.sqrt(2.0 / hidden)
        self.b3 = np.zeros(out_dim, dtype=np.float32)
        self._params = ['w1', 'b1', 'w2', 'b2', 'w3', 'b3']
        self._m = {k: np.zeros_like(getattr(self, k)) for k in self._params}
        self._v = {k: np.zeros_like(getattr(self, k)) for k in self._params}
        self._t = 0

    def forward(self, X):
        h1 = np.maximum(0, X @ self.w1.T + self.b1)
        h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
        logits = h2 @ self.w3.T + self.b3
        logits -= logits.max(axis=1, keepdims=True)
        exp_l = np.exp(logits)
        return exp_l / exp_l.sum(axis=1, keepdims=True), h1, h2

    def train_step(self, X, Y, lr):
        N = X.shape[0]
        probs, h1, h2 = self.forward(X)
        eps = 1e-8
        loss = np.mean(np.sum(Y * np.log((Y + eps) / (probs + eps)), axis=1))
        d_logits = (probs - Y) / N
        dw3 = d_logits.T @ h2; db3 = d_logits.sum(axis=0)
        dh2 = d_logits @ self.w3; dh2 *= (h2 > 0)
        dw2 = dh2.T @ h1; db2 = dh2.sum(axis=0)
        dh1 = dh2 @ self.w2; dh1 *= (h1 > 0)
        dw1 = dh1.T @ X; db1 = dh1.sum(axis=0)
        grads = {'w1': dw1, 'b1': db1, 'w2': dw2, 'b2': db2, 'w3': dw3, 'b3': db3}
        self._t += 1
        beta1, beta2 = 0.9, 0.999
        wd = getattr(self, 'weight_decay', 0.0)
        for k in self._params:
            g = grads[k]
            if wd > 0 and 'w' in k:
                g = g + wd * getattr(self, k)
            self._m[k] = beta1 * self._m[k] + (1 - beta1) * g
            self._v[k] = beta2 * self._v[k] + (1 - beta2) * g**2
            m_hat = self._m[k] / (1 - beta1**self._t)
            v_hat = self._v[k] / (1 - beta2**self._t)
            setattr(self, k, getattr(self, k) - lr * m_hat / (np.sqrt(v_hat) + 1e-8))
        return loss

    def export_cpp(self, path):
        with open(path, 'w') as f:
            f.write("#pragma once\n// Auto-generated settle MLP weights (17D: 14 local + 3 global)\n\n")
            f.write(f"static constexpr int SETTLE_FEAT_DIM = {self.feat_dim};\n")
            f.write(f"static constexpr int SETTLE_HIDDEN = {self.hidden};\n")
            f.write(f"static constexpr int SETTLE_OUT = {self.out_dim};\n\n")
            def write_array(name, arr):
                flat = arr.flatten()
                f.write(f"static const float {name}[] = {{\n")
                for i in range(0, len(flat), 8):
                    chunk = flat[i:i+8]
                    f.write("    " + ", ".join(f"{v:.6f}f" for v in chunk) + ",\n")
                f.write("};\n\n")
            write_array("settle_w1", self.w1)
            write_array("settle_b1", self.b1)
            write_array("settle_w2", self.w2)
            write_array("settle_b2", self.b2)
            write_array("settle_w3", self.w3)
            write_array("settle_b3", self.b3)


def main():
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    np.random.seed(seed)
    print(f"Training with seed={seed}")
    print("Collecting data with log(growth) + d3d1 + ruin_frac as global features...")
    X, Y = collect_data()
    print(f"Dataset: {X.shape[0]} cells, {X.shape[1]} features, {Y.shape[1]} classes")

    print(f"\nGlobal feature stats:")
    print(f"  log_growth:  mean={X[:, 14].mean():.3f} std={X[:, 14].std():.3f} min={X[:, 14].min():.3f} max={X[:, 14].max():.3f}")
    print(f"  d3d1:        mean={X[:, 15].mean():.3f} std={X[:, 15].std():.3f}")
    print(f"  ruin_frac:   mean={X[:, 16].mean():.3f} std={X[:, 16].std():.3f}")

    idx = np.random.permutation(len(X))
    split = int(0.9 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    Y_train, Y_val = Y[idx[:split]], Y[idx[split:]]

    # Also train 16D (v3 format) for comparison
    X_v3 = X.copy()
    # Recompute v3 normalization for growth feature
    # We stored log-normalized growth in col 14, need to also compare with v3 normalization
    # (skipping v3 baseline this time for speed)

    print(f"\n=== Training 17D model (log_growth + d3d1 + ruin_frac) ===")
    model = MLP(FEAT_DIM, HIDDEN, NUM_CLASSES)
    model.weight_decay = 5e-5  # best from hyperparameter search
    best_val = float('inf')
    best_weights = None

    for epoch in range(500):
        perm = np.random.permutation(len(X_train))
        X_train = X_train[perm]; Y_train = Y_train[perm]
        lr = 0.001 * (1.0 - 0.5 * epoch / 500)
        train_loss = n = 0
        for i in range(0, len(X_train), 256):
            loss = model.train_step(X_train[i:i+256], Y_train[i:i+256], lr)
            train_loss += loss; n += 1
        train_loss /= n
        val_probs, _, _ = model.forward(X_val)
        eps = 1e-8
        val_loss = np.mean(np.sum(Y_val * np.log((Y_val + eps) / (val_probs + eps)), axis=1))
        if val_loss < best_val:
            best_val = val_loss
            best_weights = tuple(getattr(model, k).copy() for k in model._params)
        if epoch % 25 == 0:
            print(f"  Epoch {epoch}: train={train_loss:.4f} val={val_loss:.4f} best={best_val:.4f}")

    for k, w in zip(model._params, best_weights):
        setattr(model, k, w)
    print(f"\nBest val loss (17D): {best_val:.4f}")

    model.export_cpp("settle_mlp_weights.h")
    print("Exported to settle_mlp_weights.h")


if __name__ == "__main__":
    main()

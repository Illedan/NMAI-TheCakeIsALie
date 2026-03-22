#!/usr/bin/env python3
"""Train MLP with viewport-independent settlement stats.

Features per cell:
  0-13: same local features as cross_mlp
  14: avg_population per alive settlement (/ 5)
  15: survival_rate (alive/total)
  16: avg_defense per alive settlement

Only 3 global features — all per-settlement averages that don't depend
on viewport size or number of queries. Fixes train/inference mismatch.
"""

import json
import os
import glob
import numpy as np
from collections import deque

ANALYSIS_DIR = "../astar-island/analysis"
INITIAL_DIR = "../astar-island/initial_states"
REPLAY_DIR = "../astar-island"
NUM_CLASSES = 6
LOCAL_FEAT_DIM = 14
GLOBAL_FEAT_DIM = 3
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

def extract_local_features(grid):
    H, W = grid.shape
    features = np.zeros((H, W, LOCAL_FEAT_DIM), dtype=np.float32)
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

    for y in range(H):
        for x in range(W):
            t = int(grid[y, x])
            c = terrain_to_class(t)
            for i in range(5):
                features[y, x, i] = 1.0 if c == i else 0.0
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


def extract_viewport_settle_stats(round_id, seed_idx):
    """Load replays and compute per-settlement averages (viewport-independent)."""
    sim_dirs = glob.glob(os.path.join(REPLAY_DIR, "simulations", "*"))
    replay_files = []
    for sd in sim_dirs:
        summary_path = os.path.join(sd, "summary.json")
        if os.path.exists(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)
            if summary.get("round_id", "")[:8] == round_id[:8]:
                seed_file = os.path.join(sd, f"seed_{seed_idx}.json")
                if os.path.exists(seed_file):
                    replay_files.append(seed_file)
    if not replay_files:
        return None

    all_avg_pop = []
    all_survival = []
    all_avg_def = []

    for rf in replay_files:
        try:
            with open(rf) as f:
                data = json.load(f)
        except:
            continue
        if isinstance(data, dict) and "frames" in data:
            frames = data["frames"]
            if frames:
                final = frames[-1]
                settlements = final.get("settlements", [])
                if not settlements:
                    continue
                alive = [s for s in settlements if s.get("alive", True)]
                all_survival.append(len(alive) / max(1, len(settlements)))
                if alive:
                    all_avg_pop.append(np.mean([s.get('population', 0) for s in alive]))
                    all_avg_def.append(np.mean([s.get('defense', 0) for s in alive]))

    if not all_avg_pop:
        return None

    return {
        'avg_pop': np.mean(all_avg_pop),
        'survival': np.mean(all_survival),
        'avg_def': np.mean(all_avg_def),
    }


def collect_data():
    X_all, Y_all = [], []
    round_dirs = {}
    for d in sorted(glob.glob(os.path.join(INITIAL_DIR, "*"))):
        if os.path.isdir(d):
            round_id = os.path.basename(d)
            round_dirs[round_id] = d

    analysis_files = sorted(glob.glob(os.path.join(ANALYSIS_DIR, "*.json")))
    processed = set()
    settle_cache = {}
    stats_found = stats_missing = 0

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

        cache_key = (round_id[:8], seed_idx)
        if cache_key not in settle_cache:
            settle_cache[cache_key] = extract_viewport_settle_stats(round_id, seed_idx)

        stats = settle_cache[cache_key]
        if stats is None:
            stats_missing += 1
            global_feats = np.array([0.2, 1.0, 0.3], dtype=np.float32)
        else:
            stats_found += 1
            global_feats = np.array([
                min(stats['avg_pop'], 5.0) / 5.0,
                stats['survival'],
                min(stats['avg_def'], 1.0),
            ], dtype=np.float32)

        try:
            gt = load_analysis(af)
            grid = load_initial(init_path)
            local_features = extract_local_features(grid)
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

    print(f"Stats: {stats_found} found, {stats_missing} missing")
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
    np.random.seed(42)
    print("Collecting training data (viewport-independent settle stats)...")
    X, Y = collect_data()
    print(f"Dataset: {X.shape[0]} cells, {X.shape[1]} features, {Y.shape[1]} classes")

    X_local = X[:, :LOCAL_FEAT_DIM]
    idx = np.random.permutation(len(X))
    split = int(0.9 * len(X))
    X_train, X_val = X[idx[:split]], X[idx[split:]]
    Y_train, Y_val = Y[idx[:split]], Y[idx[split:]]
    X_train_local, X_val_local = X_local[idx[:split]], X_local[idx[split:]]

    print(f"\n=== Training with settle features ({FEAT_DIM}D) ===")
    model = MLP(FEAT_DIM, HIDDEN, NUM_CLASSES)
    model.weight_decay = 1e-4
    best_val = float('inf')
    best_weights = None

    for epoch in range(300):
        perm = np.random.permutation(len(X_train))
        X_train = X_train[perm]; Y_train = Y_train[perm]
        lr = 0.001 * (1.0 - 0.5 * epoch / 300)
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
        if epoch % 20 == 0:
            print(f"  Epoch {epoch}: train={train_loss:.4f} val={val_loss:.4f}")

    for k, w in zip(model._params, best_weights):
        setattr(model, k, w)
    print(f"Best val loss (settle 17D): {best_val:.4f}")

    # Baseline comparison
    print(f"\n=== Baseline ({LOCAL_FEAT_DIM}D) ===")
    baseline = MLP(LOCAL_FEAT_DIM, HIDDEN, NUM_CLASSES)
    baseline.weight_decay = 1e-4
    best_base_val = float('inf')
    Y_train_b = Y[idx[:split]].copy()
    Y_val_b = Y[idx[split:]]
    for epoch in range(300):
        perm = np.random.permutation(len(X_train_local))
        X_train_local = X_train_local[perm]; Y_train_b = Y_train_b[perm]
        lr = 0.001 * (1.0 - 0.5 * epoch / 300)
        train_loss = n = 0
        for i in range(0, len(X_train_local), 256):
            loss = baseline.train_step(X_train_local[i:i+256], Y_train_b[i:i+256], lr)
            train_loss += loss; n += 1
        train_loss /= n
        val_probs, _, _ = baseline.forward(X_val_local)
        eps = 1e-8
        val_loss = np.mean(np.sum(Y_val_b * np.log((Y_val_b + eps) / (val_probs + eps)), axis=1))
        if val_loss < best_base_val:
            best_base_val = val_loss
        if epoch % 20 == 0:
            print(f"  Epoch {epoch}: train={train_loss:.4f} val={val_loss:.4f}")

    print(f"\nBaseline 14D:  {best_base_val:.4f}")
    print(f"Settle 17D:    {best_val:.4f}")
    print(f"Improvement:   {best_base_val - best_val:.4f}")

    if best_val < best_base_val:
        print("\nSettlement features HELP! Exporting...")
        model.export_cpp("settle_mlp_weights.h")
        print("Exported to settle_mlp_weights.h")
    else:
        print("\nNo improvement. Not exporting.")


if __name__ == "__main__":
    main()

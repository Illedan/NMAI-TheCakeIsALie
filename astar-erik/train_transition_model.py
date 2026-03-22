#!/usr/bin/env python3
"""
Train per-source-class transition models from pre-extracted binary data.
Run extract_transitions first to generate the .bin files.
Exports weights as C header for mean-field integration.
"""
import struct, sys
import numpy as np

NUM_CLASSES = 6
FEAT_DIM = 6
HIDDEN = 24
CLASS_NAMES = ['Empty', 'Settlement', 'Port', 'Ruin', 'Forest', 'Mountain']


def load_binary(path):
    """Load transitions from binary file written by C++ extractor."""
    with open(path, 'rb') as f:
        n, fdim = struct.unpack('ii', f.read(8))
        # n*fdim floats, then n uint8s
        feats = np.frombuffer(f.read(n * fdim * 4), dtype=np.float32).reshape(n, fdim)
        targets = np.frombuffer(f.read(n), dtype=np.uint8).astype(np.int64)
    return feats.copy(), targets.copy()


def main():
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader

    src_classes = ['empty', 'settlement', 'port', 'ruin', 'forest']
    models = {}

    for ci, cname in enumerate(src_classes):
        path = f'transitions_{cname}.bin'
        try:
            X, y = load_binary(path)
        except FileNotFoundError:
            print(f"Skipping {cname}: {path} not found")
            continue

        n = len(X)
        if n < 100:
            print(f"Skipping {cname}: only {n} samples")
            continue

        # Subsample large classes
        MAX_SAMPLES = 2_000_000
        if n > MAX_SAMPLES:
            idx = np.random.choice(n, MAX_SAMPLES, replace=False)
            X, y = X[idx], y[idx]
            n = MAX_SAMPLES

        print(f"\n{'='*50}")
        print(f"{CLASS_NAMES[ci]}: {n:,} transitions")

        # Target distribution
        for tc in range(NUM_CLASSES):
            pct = 100 * (y == tc).mean()
            if pct > 0.01:
                print(f"  → {CLASS_NAMES[tc]}: {pct:.2f}%")

        X_t = torch.from_numpy(X)
        y_t = torch.from_numpy(y)

        perm = torch.randperm(n)
        n_val = max(1000, n // 10)
        train_ds = TensorDataset(X_t[perm[n_val:]], y_t[perm[n_val:]])
        val_ds = TensorDataset(X_t[perm[:n_val]], y_t[perm[:n_val]])
        train_dl = DataLoader(train_ds, batch_size=4096, shuffle=True)
        val_dl = DataLoader(val_ds, batch_size=8192)

        model = nn.Sequential(
            nn.Linear(FEAT_DIM, HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, NUM_CLASSES),
        )

        # Class weights
        counts = torch.bincount(y_t, minlength=NUM_CLASSES).float()
        weights = torch.zeros(NUM_CLASSES)
        for c in range(NUM_CLASSES):
            weights[c] = (n / (NUM_CLASSES * counts[c])).clamp(max=10.0) if counts[c] > 0 else 0.0

        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.CrossEntropyLoss(weight=weights)

        best_val_loss = float('inf')
        best_state = None
        patience = 0

        for epoch in range(40):
            model.train()
            t_loss = 0
            for xb, yb in train_dl:
                loss = criterion(model(xb), yb)
                optimizer.zero_grad(); loss.backward(); optimizer.step()
                t_loss += loss.item() * len(xb)
            t_loss /= len(train_ds)

            model.eval()
            v_loss = 0
            with torch.no_grad():
                for xb, yb in val_dl:
                    v_loss += criterion(model(xb), yb).item() * len(xb)
            v_loss /= len(val_ds)

            if (epoch+1) % 5 == 0 or epoch == 0:
                print(f"  Epoch {epoch+1:2d}: train={t_loss:.5f} val={v_loss:.5f}")

            if v_loss < best_val_loss:
                best_val_loss = v_loss
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                patience = 0
            else:
                patience += 1
                if patience >= 8:
                    print(f"  Early stopping at epoch {epoch+1}")
                    break

        model.load_state_dict(best_state)

        # Calibration
        model.eval()
        all_probs, all_tgts = [], []
        with torch.no_grad():
            for xb, yb in val_dl:
                all_probs.append(torch.softmax(model(xb), 1))
                all_tgts.append(yb)
        all_probs = torch.cat(all_probs)
        all_tgts = torch.cat(all_tgts)

        print("  Calibration:")
        for tc in range(NUM_CLASSES):
            mask = (all_tgts == tc)
            if mask.sum() > 10:
                true_rate = mask.float().mean().item()
                pred_rate = all_probs[:, tc].mean().item()
                mean_p = all_probs[mask, tc].mean().item()
                print(f"    {CLASS_NAMES[tc]:12s}: true={true_rate:.4f} pred={pred_rate:.4f} P(y|y)={mean_p:.4f}")

        models[ci] = model

    # Export weights
    print(f"\n{'='*50}")
    print("Exporting weights to nn_weights.h...")

    with open("nn_weights.h", "w") as f:
        f.write("#pragma once\n")
        f.write("// Auto-generated by train_transition_model.py\n")
        f.write(f"// Per-source-class transition models: {FEAT_DIM} inputs → {HIDDEN} hidden → {NUM_CLASSES} outputs\n\n")
        f.write(f"static constexpr int NN_FEAT_DIM = {FEAT_DIM};\n")
        f.write(f"static constexpr int NN_HIDDEN = {HIDDEN};\n")
        f.write(f"static constexpr int NN_NUM_CLASSES = {NUM_CLASSES};\n\n")

        prefixes = ['NN_EMPTY', 'NN_SETTLEMENT', 'NN_PORT', 'NN_RUIN', 'NN_FOREST']
        for ci in range(5):
            if ci not in models:
                continue
            sd = models[ci].state_dict()
            prefix = prefixes[ci]
            f.write(f"// {CLASS_NAMES[ci]} transitions\n")
            for pt_name, suffix in [("0.weight","W1"),("0.bias","B1"),("2.weight","W2"),("2.bias","B2"),("4.weight","W3"),("4.bias","B3")]:
                tensor = sd[pt_name].numpy().flatten()
                f.write(f"static const float {prefix}_{suffix}[] = {{\n")
                for i in range(0, len(tensor), 8):
                    vals = tensor[i:i+8]
                    f.write("    " + ", ".join(f"{v:.6f}f" for v in vals) + ",\n")
                f.write("};\n")
            f.write("\n")

        f.write("struct NNModel {\n    const float* w1, *b1, *w2, *b2, *w3, *b3;\n};\n\n")
        f.write("static const NNModel NN_MODELS[5] = {\n")
        for ci in range(5):
            p = prefixes[ci]
            if ci in models:
                f.write(f"    {{{p}_W1, {p}_B1, {p}_W2, {p}_B2, {p}_W3, {p}_B3}},\n")
            else:
                f.write(f"    {{nullptr, nullptr, nullptr, nullptr, nullptr, nullptr}},\n")
        f.write("};\n")

    total_params = sum(sum(p.numel() for p in m.parameters()) for m in models.values())
    print(f"Done! {len(models)} models, {total_params} total parameters")


if __name__ == "__main__":
    main()

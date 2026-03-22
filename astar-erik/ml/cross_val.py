#!/usr/bin/env python3 -u
"""
Leave-one-round-out cross-validation.

For each of the 9 rounds:
  1. Train on the other 8 rounds (+ synthetic data)
  2. Evaluate on the held-out round
  3. Report the score

This tells us how well the model generalizes to unseen rounds.
"""

import numpy as np
import torch
from torch.utils.data import DataLoader, ConcatDataset
from pathlib import Path
import time

from dataset import AstarDataset, random_augment
from model import UNet
from train import KLDivLoss, score_from_kl
from evaluate import discover_rounds
from infer import predict, score_prediction
from generate_data import simulate_queries, NUM_CLASSES
import json

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"


def get_round_files(data_dir, round_short_id):
    """Get all .npz files belonging to a specific round."""
    files = []
    for f in data_dir.glob("*.npz"):
        if f.name.startswith(round_short_id):
            files.append(f)
    return files


def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Device: {device}")

    rounds = discover_rounds()
    print(f"Found {len(rounds)} rounds\n")

    # Collect all round short IDs
    round_ids = [(r["round_id"][:8], r["round_id"], r["round_number"]) for r in rounds]

    all_scores = []

    for held_out_short, held_out_full, held_out_num in round_ids:
        print(f"\n{'='*50}")
        print(f"Holding out Round {held_out_num} ({held_out_short})")
        print(f"{'='*50}")

        # Build train set: everything except held-out round (real + augmented)
        # Plus all synthetic data
        train_files = []
        val_files = []

        for subdir in ["real", "augmented"]:
            d = DATA_DIR / subdir
            if not d.exists():
                continue
            for f in d.glob("*.npz"):
                if f.name.startswith(held_out_short):
                    val_files.append(f)
                else:
                    train_files.append(f)

        # Always include synthetic in training
        syn_dir = DATA_DIR / "synthetic"
        if syn_dir.exists():
            train_files.extend(syn_dir.glob("*.npz"))

        print(f"  Train: {len(train_files)}, Val: {len(val_files)}")

        if not val_files:
            print("  No validation files, skipping")
            continue

        # Create datasets
        class FileListDataset(AstarDataset):
            def __init__(self, file_list):
                self.files = file_list
                self.transform = None

        train_set = FileListDataset(train_files)

        class AugmentedDataset(torch.utils.data.Dataset):
            def __init__(self, ds):
                self.ds = ds
            def __len__(self):
                return len(self.ds)
            def __getitem__(self, idx):
                inp, tgt = self.ds[idx]
                return random_augment(inp, tgt)

        train_loader = DataLoader(AugmentedDataset(train_set), batch_size=8, shuffle=True, num_workers=0)

        # Quick train (30 epochs)
        model = UNet(in_channels=19, out_channels=6, base_filters=64).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=50)
        criterion = KLDivLoss(eps=0.01)

        for epoch in range(1, 51):
            model.train()
            epoch_loss = 0
            n = 0
            for inputs, targets in train_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                loss = criterion(model(inputs), targets)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n += 1
            scheduler.step()
            if epoch % 10 == 0:
                avg_loss = epoch_loss / max(n, 1)
                print(f"  Epoch {epoch}: train_kl={avg_loss:.4f} (~{score_from_kl(avg_loss):.1f})")

        # Evaluate on held-out round
        model.eval()
        rng = np.random.default_rng(42)

        # Find the round data
        held_round = next(r for r in rounds if r["round_id"][:8] == held_out_short)
        round_scores = []

        for seed, af in sorted(held_round["seeds"].items()):
            with open(af) as f:
                analysis = json.load(f)
            gt = np.array(analysis["ground_truth"], dtype=np.float32)
            grid = np.array(analysis["initial_grid"], dtype=np.int32)

            # Blind prediction
            pred = predict(model, grid, device=device)
            score = score_prediction(pred, gt)
            round_scores.append(score)
            print(f"  Seed {seed}: {score:.2f} (blind)")

        avg = np.mean(round_scores) if round_scores else 0
        print(f"  Round {held_out_num} avg: {avg:.2f}")
        all_scores.append((held_out_num, held_out_short, avg))

    print(f"\n{'='*50}")
    print("CROSS-VALIDATION SUMMARY")
    print(f"{'='*50}")
    for rnum, short, score in all_scores:
        print(f"  Round {rnum:2d} ({short}): {score:.2f}")
    if all_scores:
        overall = np.mean([s for _, _, s in all_scores])
        print(f"\n  Overall: {overall:.2f}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Train the U-Net model for Astar Island prediction.

Loss: KL divergence between predicted and target probability distributions.
This matches the competition scoring metric.
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, random_split
from pathlib import Path
import time

from dataset import AstarDataset, random_augment
from model import UNet

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
CHECKPOINT_DIR = SCRIPT_DIR / "checkpoints"


class KLDivLoss(nn.Module):
    """Entropy-weighted KL divergence loss matching competition scoring."""

    def __init__(self, eps=0.01):
        super().__init__()
        self.eps = eps

    def forward(self, pred_logits, target):
        """
        pred_logits: (B, 6, H, W) raw logits
        target: (B, 6, H, W) ground truth probabilities
        """
        # Softmax + floor
        pred = F.softmax(pred_logits, dim=1)
        pred = pred * (1 - 6 * self.eps) + self.eps

        # Compute per-cell entropy of target (for weighting)
        target_clamped = target.clamp(min=1e-8)
        entropy = -(target_clamped * target_clamped.log()).sum(dim=1)  # (B, H, W)

        # KL divergence: sum_c p(c) * log(p(c) / q(c))
        kl = (target_clamped * (target_clamped.log() - pred.log())).sum(dim=1)  # (B, H, W)

        # Weight by entropy (only dynamic cells matter)
        weighted_kl = (entropy * kl).sum(dim=(1, 2)) / entropy.sum(dim=(1, 2)).clamp(min=1e-8)

        return weighted_kl.mean()


def score_from_kl(kl_value):
    """Convert KL to competition-style score."""
    import math
    return max(0, min(100, 100 * math.exp(-3 * kl_value)))


def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    n_batches = 0
    for inputs, targets in loader:
        inputs, targets = inputs.to(device), targets.to(device)
        optimizer.zero_grad()
        logits = model(inputs)
        loss = criterion(logits, targets)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


def validate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    n_batches = 0
    with torch.no_grad():
        for inputs, targets in loader:
            inputs, targets = inputs.to(device), targets.to(device)
            logits = model(inputs)
            loss = criterion(logits, targets)
            total_loss += loss.item()
            n_batches += 1
    return total_loss / max(n_batches, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--filters", type=int, default=64)
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    if args.device == "auto":
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    print(f"Device: {device}")

    # Load data from all sources
    data_dirs = [
        DATA_DIR / "real",
        DATA_DIR / "augmented",
        DATA_DIR / "synthetic",
    ]
    dataset = AstarDataset(data_dirs)
    print(f"Total samples: {len(dataset)}")

    if len(dataset) == 0:
        print("No data! Run generate_data.py first.")
        return

    # Split 80/20
    n_val = max(1, len(dataset) // 5)
    n_train = len(dataset) - n_val
    train_set, val_set = random_split(dataset, [n_train, n_val],
                                       generator=torch.Generator().manual_seed(42))

    # Wrap train set with augmentation
    class AugmentedSubset(torch.utils.data.Dataset):
        def __init__(self, subset):
            self.subset = subset
        def __len__(self):
            return len(self.subset)
        def __getitem__(self, idx):
            inp, tgt = self.subset[idx]
            return random_augment(inp, tgt)

    train_loader = DataLoader(AugmentedSubset(train_set), batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False, num_workers=0)

    print(f"Train: {len(train_set)}, Val: {len(val_set)}")

    # Model
    model = UNet(
        in_channels=AstarDataset.input_channels(),
        out_channels=AstarDataset.output_channels(),
        base_filters=args.filters,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model params: {n_params:,}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = KLDivLoss(eps=0.01)

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    best_val = float("inf")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss = validate(model, val_loader, criterion, device)
        scheduler.step()

        dt = time.time() - t0
        score = score_from_kl(val_loss)
        print(f"Epoch {epoch:3d}/{args.epochs}  train_kl={train_loss:.4f}  val_kl={val_loss:.4f}  "
              f"~score={score:.1f}  lr={optimizer.param_groups[0]['lr']:.2e}  {dt:.1f}s")

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), CHECKPOINT_DIR / "best.pt")
            print(f"  -> New best! val_kl={val_loss:.4f} (~score={score:.1f})")

        if epoch % 10 == 0:
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_loss": val_loss,
            }, CHECKPOINT_DIR / f"epoch_{epoch:03d}.pt")

    print(f"\nBest val KL: {best_val:.4f} (~score={score_from_kl(best_val):.1f})")
    print(f"Checkpoint: {CHECKPOINT_DIR / 'best.pt'}")


if __name__ == "__main__":
    main()

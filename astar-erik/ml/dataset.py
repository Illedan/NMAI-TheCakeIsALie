"""
PyTorch dataset for Astar Island ML model.

Each sample provides:
  - input tensor: (C_in, 40, 40) with channels for terrain, observations, distances
  - target tensor: (6, 40, 40) ground truth class probabilities
"""

import numpy as np
import torch
from torch.utils.data import Dataset
from pathlib import Path


def random_augment(input_tensor, target_tensor):
    """Random flips + 90° rotations. Both tensors are (C, H, W)."""
    # Random number of 90° rotations
    k = torch.randint(0, 4, (1,)).item()
    if k > 0:
        input_tensor = torch.rot90(input_tensor, k, dims=(1, 2))
        target_tensor = torch.rot90(target_tensor, k, dims=(1, 2))
    # Random horizontal flip
    if torch.rand(1).item() > 0.5:
        input_tensor = input_tensor.flip(2)
        target_tensor = target_tensor.flip(2)
    # Random vertical flip
    if torch.rand(1).item() > 0.5:
        input_tensor = input_tensor.flip(1)
        target_tensor = target_tensor.flip(1)
    return input_tensor, target_tensor


class AstarDataset(Dataset):
    """Dataset loading .npz training samples."""

    def __init__(self, data_dirs, transform=None):
        """
        Args:
            data_dirs: list of directories containing .npz files
            transform: optional transform applied to (input, target) pair
        """
        self.files = []
        for d in data_dirs:
            d = Path(d)
            if d.exists():
                self.files.extend(sorted(d.glob("*.npz")))
        self.transform = transform

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        data = np.load(self.files[idx])

        # Build input channels: (C, H, W)
        # 8 one-hot terrain + 6 obs_freq + 1 obs_count_norm + 1 obs_mask + 3 distances = 19 channels
        initial_onehot = data["initial_onehot"]  # (H, W, 8)
        obs_freq = data["obs_freq"]              # (H, W, 6)
        obs_count = data["obs_count"]            # (H, W)
        obs_mask = data["obs_mask"]              # (H, W)
        coast_dist = data["coast_dist"]          # (H, W)
        forest_dist = data["forest_dist"]        # (H, W)
        settle_dist = data["settle_dist"]        # (H, W)

        # Normalize obs_count to [0, 1]
        obs_count_norm = obs_count.astype(np.float32) / max(obs_count.max(), 1)

        # Stack all channels: (H, W, C) -> (C, H, W)
        input_tensor = np.concatenate([
            initial_onehot,                              # 8 channels
            obs_freq,                                    # 6 channels
            obs_count_norm[:, :, None],                  # 1 channel
            obs_mask.astype(np.float32)[:, :, None],     # 1 channel
            coast_dist[:, :, None],                      # 1 channel
            forest_dist[:, :, None],                     # 1 channel
            settle_dist[:, :, None],                     # 1 channel
        ], axis=-1)  # (H, W, 19)

        input_tensor = torch.from_numpy(input_tensor).permute(2, 0, 1).float()  # (19, H, W)

        # Target: (6, H, W)
        target = data["target"]  # (H, W, 6)
        target_tensor = torch.from_numpy(target).permute(2, 0, 1).float()  # (6, H, W)

        if self.transform:
            input_tensor, target_tensor = self.transform(input_tensor, target_tensor)

        return input_tensor, target_tensor

    @staticmethod
    def input_channels():
        return 19

    @staticmethod
    def output_channels():
        return 6

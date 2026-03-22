"""
U-Net model for Astar Island prediction.

Simple but effective: takes 19-channel input (terrain + observations + distances),
outputs 6-channel probability distribution per cell.

Start simple — no FiLM/round embedding yet. That's phase 2.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class UNet(nn.Module):
    """Small U-Net for 40x40 maps.

    Encoder: 40->20->10->5
    Decoder: 5->10->20->40
    """

    def __init__(self, in_channels=19, out_channels=6, base_filters=64):
        super().__init__()
        f = base_filters

        # Encoder
        self.enc1 = ConvBlock(in_channels, f)
        self.enc2 = ConvBlock(f, f * 2)
        self.enc3 = ConvBlock(f * 2, f * 4)

        # Bottleneck
        self.bottleneck = ConvBlock(f * 4, f * 8)

        # Decoder
        self.up3 = nn.ConvTranspose2d(f * 8, f * 4, 2, stride=2)
        self.dec3 = ConvBlock(f * 8, f * 4)
        self.up2 = nn.ConvTranspose2d(f * 4, f * 2, 2, stride=2)
        self.dec2 = ConvBlock(f * 4, f * 2)
        self.up1 = nn.ConvTranspose2d(f * 2, f, 2, stride=2)
        self.dec1 = ConvBlock(f * 2, f)

        # Output
        self.out_conv = nn.Conv2d(f, out_channels, 1)

        self.pool = nn.MaxPool2d(2)

    def forward(self, x):
        # Handle non-power-of-2 sizes by padding to 40->40 (already fine for pool2x3)
        # 40 -> 20 -> 10 -> 5, then 5 -> 10 -> 20 -> 40
        e1 = self.enc1(x)       # (B, f, 40, 40)
        e2 = self.enc2(self.pool(e1))  # (B, 2f, 20, 20)
        e3 = self.enc3(self.pool(e2))  # (B, 4f, 10, 10)

        b = self.bottleneck(self.pool(e3))  # (B, 8f, 5, 5)

        d3 = self.up3(b)        # (B, 4f, 10, 10)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))
        d2 = self.up2(d3)       # (B, 2f, 20, 20)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))
        d1 = self.up1(d2)       # (B, f, 40, 40)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))

        logits = self.out_conv(d1)  # (B, 6, 40, 40)
        return logits

    def predict_probs(self, x, eps=0.01):
        """Get probability output with floor."""
        logits = self.forward(x)
        probs = F.softmax(logits, dim=1)  # (B, 6, H, W)
        # Apply floor
        probs = probs * (1 - 6 * eps) + eps
        return probs

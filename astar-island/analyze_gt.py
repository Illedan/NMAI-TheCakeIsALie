import json, numpy as np, random as pyrandom
from prepare import score_fun

with open('analysis/round_7_analysis_seed_0_36e581f1-73f8-453f-ab98-cbe3052b701b.json') as f:
    data = json.load(f)
gt = np.array(data['ground_truth'], dtype=np.float64)

ent = -np.sum(gt * np.log(gt + 1e-12), axis=-1)
print(f'Entropy: min={ent.min():.4f} max={ent.max():.4f} mean={ent.mean():.4f}')
print(f'High-entropy cells (>0.1): {(ent > 0.1).sum()} / 1600')
print(f'High-entropy cells (>0.5): {(ent > 0.5).sum()} / 1600')
print(f'Perfect score: {score_fun(gt, gt):.2f}')
print(f'Uniform score: {score_fun(gt, np.full((40,40,6), 1/6)):.2f}')

# GT with controlled noise
rng = pyrandom.Random(42)
for noise_level in [0.02, 0.05, 0.10, 0.20]:
    noisy = gt.copy()
    for y in range(40):
        for x in range(40):
            for c in range(6):
                noisy[y, x, c] += rng.gauss(0, noise_level)
    noisy = np.maximum(noisy, 0.01)
    noisy /= noisy.sum(axis=-1, keepdims=True)
    print(f'GT + N(0,{noise_level:.2f}) score: {score_fun(gt, noisy):.2f}')

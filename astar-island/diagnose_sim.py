"""Diagnose where simulation predictions diverge from ground truth.
Uses the replay frame 0 (true initial stats) + fitted round 7 params."""

import json
import subprocess
import numpy as np
from prepare import score_fun, RAW_TO_CLASS

ROUND_ID = "36e581f1-73f8-453f-ab98-cbe3052b701b"
H, W, NC = 40, 40, 6

# Load ground truth
with open(f"analysis/round_7_analysis_seed_0_{ROUND_ID}.json") as f:
    gt = np.array(json.load(f)["ground_truth"], dtype=np.float64)

# Load replay frame 0 (true initial stats)
with open(f"replays/round_7_replay_seed_0_{ROUND_ID}.json") as f:
    replay = json.load(f)
frame0 = replay["frames"][0]
final_frame = replay["frames"][-1]

# Use the converged params from evo run
PARAMS = {
    "alpha_pop": 0.098, "alpha_def": 0.135,
    "alpha_plains": 0.023, "alpha_forest": 0.036, "beta": 0.022,
    "mu_spawn": 1.67, "s_spawn": 0.63, "sigma_dist": 0.46,
    "p_multi": 0.127, "hi_food_transfer": 0.145, "mu_f_tier": 0.67,
    "port_thresh": 0.39,
    "p_raid_nonport": 0.043, "sigma_raid_nonport": 1.57,
    "p_raid_port": 0.073, "sigma_raid_port": 2.45,
    "p_raid_success": 0.644, "p_conquest": 0.060,
    "collapse_s": 0.045,
}

# Run with true_sim (single param set, N sims)
def run_true_sim(n_sims=2000):
    lines = [f"{H} {W} {len(frame0['settlements'])} {n_sims} 50"]
    for row in frame0["grid"]:
        lines.append(" ".join(str(v) for v in row))
    for s in frame0["settlements"]:
        lines.append(f"{s['x']} {s['y']} {s['population']} {s['food']} {s['wealth']} "
                     f"{s['defense']} {1 if s['has_port'] else 0} "
                     f"{1 if s['alive'] else 0} {s['owner_id']}")
    p = PARAMS
    lines.append(f"{p['alpha_pop']} {p['alpha_def']} {p['alpha_plains']} {p['alpha_forest']} {p['beta']}")
    lines.append(f"{p['mu_spawn']} {p['s_spawn']} {p['sigma_dist']} {p['p_multi']} {p['hi_food_transfer']} {p['mu_f_tier']}")
    lines.append(f"{p['port_thresh']}")
    lines.append(f"{p['p_raid_nonport']} {p['sigma_raid_nonport']} {p['p_raid_port']} {p['sigma_raid_port']} {p['p_raid_success']} {p['p_conquest']}")
    lines.append(f"{p['collapse_s']}")
    inp = "\n".join(lines) + "\n"

    result = subprocess.run(["./true_sim"], input=inp, capture_output=True, text=True, timeout=120)
    counts = np.array([int(x) for x in result.stdout.strip().split("\n")], dtype=np.float64)
    counts = counts.reshape(H, W, NC)
    alpha = 0.015
    return (counts + alpha) / (n_sims + alpha * NC)

pred = run_true_sim(2000)
score = score_fun(gt, pred)
print(f"Score with true initial stats + converged params: {score:.2f}")

# Compare class distributions
gt_cls = gt.argmax(axis=-1)
pred_cls = pred.argmax(axis=-1)
replay_final_cls = np.zeros((H, W), dtype=int)
fg = final_frame["grid"]
for y in range(H):
    for x in range(W):
        replay_final_cls[y, x] = RAW_TO_CLASS.get(fg[y][x], 0)

# Per-class frequency comparison
print("\nPer-class frequency (fraction of cells where each class is most likely):")
print(f"{'Class':>6} {'GT':>8} {'Pred':>8} {'Replay':>8}")
for c in range(NC):
    gt_f = (gt_cls == c).sum() / (H*W)
    pr_f = (pred_cls == c).sum() / (H*W)
    rp_f = (replay_final_cls == c).sum() / (H*W)
    print(f"{c:>6} {gt_f:>8.3f} {pr_f:>8.3f} {rp_f:>8.3f}")

# Per-class mean probability
print("\nMean probability per class across all cells:")
print(f"{'Class':>6} {'GT':>8} {'Pred':>8} {'Diff':>8}")
for c in range(NC):
    gt_m = gt[:, :, c].mean()
    pr_m = pred[:, :, c].mean()
    print(f"{c:>6} {gt_m:>8.4f} {pr_m:>8.4f} {pr_m - gt_m:>+8.4f}")

# Find cells with biggest KL divergence
kl = np.sum(gt * np.log((gt + 1e-12) / (pred + 1e-12)), axis=-1)
ent = -np.sum(gt * np.log(gt + 1e-12), axis=-1)
weighted_kl = ent * kl

print(f"\nTop 20 cells by weighted KL divergence:")
print(f"{'(x,y)':>8} {'wKL':>8} {'KL':>8} {'ent':>6} {'gt_argmax':>9} {'pred_argmax':>11} gt_dist -> pred_dist")
flat_idx = np.argsort(weighted_kl.flatten())[::-1]
for i in range(20):
    idx = flat_idx[i]
    y, x = divmod(idx, W)
    gt_str = " ".join(f"{gt[y,x,c]:.2f}" for c in range(NC))
    pr_str = " ".join(f"{pred[y,x,c]:.2f}" for c in range(NC))
    print(f"({x:2d},{y:2d}) {weighted_kl[y,x]:8.3f} {kl[y,x]:8.3f} {ent[y,x]:6.3f} "
          f"{gt_cls[y,x]:>9d} {pred_cls[y,x]:>11d}  [{gt_str}] -> [{pr_str}]")

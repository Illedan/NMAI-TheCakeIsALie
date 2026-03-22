"""Compare simulation with evo-optimized vs replay-fitted params."""
import json, subprocess, numpy as np
from prepare import score_fun, RAW_TO_CLASS

ROUND_ID = "36e581f1-73f8-453f-ab98-cbe3052b701b"
H, W, NC = 40, 40, 6

with open(f"analysis/round_7_analysis_seed_0_{ROUND_ID}.json") as f:
    gt = np.array(json.load(f)["ground_truth"], dtype=np.float64)
with open(f"replays/round_7_replay_seed_0_{ROUND_ID}.json") as f:
    frame0 = json.load(f)["frames"][0]

# Get round 7 food params from our regression
# From the earlier analysis: 36e581f1  a_plains=0.02462  a_forest=0.02466  beta=0.04745

PARAM_SETS = {
    "replay-fitted": {
        "alpha_pop": 0.10, "alpha_def": 0.104,
        "alpha_plains": 0.0246, "alpha_forest": 0.0247, "beta": 0.0475,
        "mu_spawn": 1.893, "s_spawn": 0.29, "sigma_dist": 2.623,
        "p_multi": 0.051, "hi_food_transfer": 0.091, "mu_f_tier": 0.645,
        "port_thresh": 0.430,
        "p_raid_nonport": 0.134, "sigma_raid_nonport": 1.65,
        "p_raid_port": 0.108, "sigma_raid_port": 2.89,
        "p_raid_success": 0.622, "p_conquest": 0.162,
        "collapse_s": 0.104,
    },
    "evo-optimized": {
        "alpha_pop": 0.098, "alpha_def": 0.135,
        "alpha_plains": 0.023, "alpha_forest": 0.036, "beta": 0.022,
        "mu_spawn": 1.67, "s_spawn": 0.63, "sigma_dist": 0.46,
        "p_multi": 0.127, "hi_food_transfer": 0.145, "mu_f_tier": 0.67,
        "port_thresh": 0.39,
        "p_raid_nonport": 0.043, "sigma_raid_nonport": 1.57,
        "p_raid_port": 0.073, "sigma_raid_port": 2.45,
        "p_raid_success": 0.644, "p_conquest": 0.060,
        "collapse_s": 0.045,
    },
}

def run_sim(params, n_sims=3000):
    lines = [f"{H} {W} {len(frame0['settlements'])} {n_sims} 50"]
    for row in frame0["grid"]:
        lines.append(" ".join(str(v) for v in row))
    for s in frame0["settlements"]:
        lines.append(f"{s['x']} {s['y']} {s['population']} {s['food']} {s['wealth']} "
                     f"{s['defense']} {1 if s['has_port'] else 0} "
                     f"{1 if s['alive'] else 0} {s['owner_id']}")
    p = params
    lines.append(f"{p['alpha_pop']} {p['alpha_def']} {p['alpha_plains']} {p['alpha_forest']} {p['beta']}")
    lines.append(f"{p['mu_spawn']} {p['s_spawn']} {p['sigma_dist']} {p['p_multi']} {p['hi_food_transfer']} {p['mu_f_tier']}")
    lines.append(f"{p['port_thresh']}")
    lines.append(f"{p['p_raid_nonport']} {p['sigma_raid_nonport']} {p['p_raid_port']} {p['sigma_raid_port']} {p['p_raid_success']} {p['p_conquest']}")
    lines.append(f"{p['collapse_s']}")
    result = subprocess.run(["./true_sim"], input="\n".join(lines)+"\n", capture_output=True, text=True, timeout=120)
    counts = np.array([int(x) for x in result.stdout.strip().split("\n")], dtype=np.float64).reshape(H, W, NC)
    alpha = 0.015
    return (counts + alpha) / (n_sims + alpha * NC)

for name, params in PARAM_SETS.items():
    pred = run_sim(params)
    score = score_fun(gt, pred)
    print(f"\n{name}: score={score:.2f}")
    print(f"  Mean prob per class: ", end="")
    for c in range(NC):
        print(f"c{c}={pred[:,:,c].mean():.4f}", end=" ")
    print()
    print(f"  GT mean prob:        ", end="")
    for c in range(NC):
        print(f"c{c}={gt[:,:,c].mean():.4f}", end=" ")
    print()
    # Diff
    print(f"  Diff (pred-gt):      ", end="")
    for c in range(NC):
        d = pred[:,:,c].mean() - gt[:,:,c].mean()
        print(f"c{c}={d:+.4f}", end=" ")
    print()

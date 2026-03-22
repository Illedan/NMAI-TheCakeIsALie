"""Run C++ true_sim on round 1 with hardcoded params, compare to ground truth."""

import json
import subprocess
import numpy as np
from prepare import score_fun

ROUND_ID = "71451d74-be9f-471f-aacd-a41f3b68a9cd"
ANALYSIS_DIR = "analysis"
REPLAY_DIR = "replays"
N_SIMULATIONS = 1500
N_STEPS = 50
NUM_CLASSES = 6
CPP_BINARY = "./true_sim"

# Round 1 (71451d74) hardcoded params from fit_priors
PARAMS = {
    "alpha_pop": 0.10, "alpha_def": 0.058,
    "alpha_plains": 0.0153, "alpha_forest": 0.0183, "beta": 0.0255,
    "mu_spawn": 1.997, "s_spawn": 0.32, "sigma_dist": 2.8647,
    "p_multi": 0.067, "hi_food_transfer": 0.047, "mu_f_tier": 0.645,
    "port_thresh": 0.506,
    "p_raid_nonport": 0.133, "sigma_raid_nonport": 1.81,
    "p_raid_port": 0.151, "sigma_raid_port": 2.73,
    "p_raid_success": 0.578, "p_conquest": 0.108,
    "collapse_s": 0.1064,
}


def load_ground_truth(seed_idx):
    path = f"{ANALYSIS_DIR}/round_1_analysis_seed_{seed_idx}_{ROUND_ID}.json"
    with open(path) as f:
        data = json.load(f)
    return np.array(data["ground_truth"], dtype=np.float64)


def load_replay_frame0(seed_idx):
    path = f"{REPLAY_DIR}/round_1_replay_seed_{seed_idx}_{ROUND_ID}.json"
    with open(path) as f:
        data = json.load(f)
    return data["frames"][0]


def build_input(seed_idx):
    """Build text input for the C++ binary."""
    frame = load_replay_frame0(seed_idx)
    grid = frame["grid"]
    settlements = frame["settlements"]
    H, W = len(grid), len(grid[0])

    lines = []
    lines.append(f"{H} {W} {len(settlements)} {N_SIMULATIONS} {N_STEPS}")

    for row in grid:
        lines.append(" ".join(str(v) for v in row))

    for s in settlements:
        lines.append(f"{s['x']} {s['y']} {s['population']} {s['food']} {s['wealth']} "
                     f"{s['defense']} {1 if s['has_port'] else 0} "
                     f"{1 if s['alive'] else 0} {s['owner_id']}")

    p = PARAMS
    lines.append(f"{p['alpha_pop']} {p['alpha_def']} {p['alpha_plains']} {p['alpha_forest']} {p['beta']}")
    lines.append(f"{p['mu_spawn']} {p['s_spawn']} {p['sigma_dist']} {p['p_multi']} {p['hi_food_transfer']} {p['mu_f_tier']}")
    lines.append(f"{p['port_thresh']}")
    lines.append(f"{p['p_raid_nonport']} {p['sigma_raid_nonport']} {p['p_raid_port']} {p['sigma_raid_port']} {p['p_raid_success']} {p['p_conquest']}")
    lines.append(f"{p['collapse_s']}")

    return "\n".join(lines) + "\n"


def run_simulation(seed_idx):
    """Run C++ simulation, return H×W×6 prediction array."""
    input_text = build_input(seed_idx)
    result = subprocess.run(
        [CPP_BINARY],
        input=input_text, capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"C++ error: {result.stderr}")
        raise RuntimeError("C++ simulation failed")

    counts = np.array([int(x) for x in result.stdout.strip().split("\n")], dtype=np.float64)
    H, W = 40, 40
    counts = counts.reshape(H, W, NUM_CLASSES)

    # Normalize with Laplace smoothing
    alpha = 0.015
    prediction = (counts + alpha) / (N_SIMULATIONS + alpha * NUM_CLASSES)
    return prediction


def main():
    print(f"Running {N_SIMULATIONS} C++ simulations per seed...")

    scores = []
    for seed_idx in range(5):
        gt = load_ground_truth(seed_idx)
        prediction = run_simulation(seed_idx)
        score = score_fun(gt, prediction)
        scores.append(score)
        print(f"  Seed {seed_idx}: score = {score:.2f}")

    mean_score = sum(scores) / len(scores)
    print(f"\nMean score: {mean_score:.2f}")
    print(f"(Original round 1 score from analysis was ~21.7)")


if __name__ == "__main__":
    main()

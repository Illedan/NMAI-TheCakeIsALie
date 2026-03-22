"""Evolutionary parameter search using full ground truth likelihood.

Instead of viewport queries, scores each particle against the full H×W×6
ground truth distribution. Top survivors are kept, distributions refitted,
and population resampled. Iterates until convergence.
"""

import json
import glob
import os
import random
import subprocess
import sys
import math

import numpy as np

from prepare import score_fun, RAW_TO_CLASS

# ── Configuration ──
ROUND_ID = "36e581f1-73f8-453f-ab98-cbe3052b701b"
SEED_IDX = 0
N_POP = 1000
N_STEPS = 50
N_ITERS = 30
SURVIVAL_RATE = 0.10
N_FINAL = 10000
H, W = 40, 40
NUM_CLASSES = 6
EVO_BIN = "./evo_sim"

INITIAL_STATES_DIR = "initial_states"
ANALYSIS_DIR = "analysis"
REPLAY_DIR = "replays"

# ── Parameter priors (name, E, std, lo, hi) ──
PARAM_SPEC = [
    ("alpha_pop",        0.10,   0.05,   0.01,  0.30),
    ("alpha_def",        0.083,  0.032,  0.01,  0.20),
    ("alpha_plains",     0.0183, 0.0036, 0.0,   0.06),
    ("alpha_forest",     0.0220, 0.0046, 0.0,   0.06),
    ("beta",             0.0431, 0.0163, 0.0,   0.15),
    ("mu_spawn",         2.184,  0.288,  0.5,   4.0),
    ("s_spawn",          0.432,  0.166,  0.01,  1.5),
    ("sigma_dist",       1.52,   0.89,   0.3,   6.0),
    ("p_multi",          0.076,  0.030,  0.0,   0.5),
    ("hi_food_transfer", 0.092,  0.077, -0.1,   0.4),
    ("mu_f_tier",        0.645,  0.131,  0.1,   1.5),
    ("port_thresh",      0.454,  0.182,  0.0,   1.0),
    ("p_raid_nonport",   0.126,  0.063,  0.001, 0.5),
    ("sigma_raid_nonport", 1.67, 0.10,   0.5,   5.0),
    ("p_raid_port",      0.139,  0.092,  0.001, 0.5),
    ("sigma_raid_port",  2.52,   0.51,   0.5,   8.0),
    ("p_raid_success",   0.605,  0.048,  0.1,   0.95),
    ("p_conquest",       0.230,  0.161,  0.0,   0.8),
    ("collapse_s",       0.158,  0.038,  0.01,  0.5),
]
PARAM_NAMES = [s[0] for s in PARAM_SPEC]


def load_initial_state():
    for d in os.listdir(INITIAL_STATES_DIR):
        sp = os.path.join(INITIAL_STATES_DIR, d, "summary.json")
        if os.path.isfile(sp):
            with open(sp) as f:
                s = json.load(f)
            if s["round_id"] == ROUND_ID:
                with open(os.path.join(INITIAL_STATES_DIR, d, f"seed_{SEED_IDX}.json")) as f:
                    return json.load(f)
    raise FileNotFoundError(f"No initial state for {ROUND_ID}")


def load_ground_truth():
    files = glob.glob(os.path.join(ANALYSIS_DIR, f"*_analysis_seed_{SEED_IDX}_{ROUND_ID}.json"))
    with open(files[0]) as f:
        data = json.load(f)
    return np.array(data["ground_truth"], dtype=np.float64)


def sample_params(rng, means=None, stds=None):
    params = {}
    for i, (name, e, s, lo, hi) in enumerate(PARAM_SPEC):
        mu = means[i] if means is not None else e
        sd = stds[i] if stds is not None else s
        params[name] = max(lo, min(hi, rng.gauss(mu, sd)))
    return params


def sample_initial_stats(rng, n_settle):
    return [
        (rng.uniform(0.50, 1.50), rng.uniform(0.30, 0.80),
         rng.uniform(0.10, 0.50), rng.uniform(0.20, 0.60))
        for _ in range(n_settle)
    ]


def build_input(grid, positions, population):
    n_settle = len(positions)
    n_sims = len(population)
    lines = [f"{H} {W} {n_settle} {n_sims} {N_STEPS}"]
    for row in grid:
        lines.append(" ".join(str(v) for v in row))
    for p in positions:
        lines.append(f"{p['x']} {p['y']} {1 if p.get('has_port', False) else 0}")
    for stats, params in population:
        for pop, food, wealth, defense in stats:
            lines.append(f"{pop} {food} {wealth} {defense}")
        p = params
        lines.append(f"{p['alpha_pop']} {p['alpha_def']} {p['alpha_plains']} {p['alpha_forest']} {p['beta']}")
        lines.append(f"{p['mu_spawn']} {p['s_spawn']} {p['sigma_dist']} {p['p_multi']} {p['hi_food_transfer']} {p['mu_f_tier']}")
        lines.append(f"{p['port_thresh']}")
        lines.append(f"{p['p_raid_nonport']} {p['sigma_raid_nonport']} {p['p_raid_port']} {p['sigma_raid_port']} {p['p_raid_success']} {p['p_conquest']}")
        lines.append(f"{p['collapse_s']}")
    return "\n".join(lines) + "\n"


def run_simulations(grid, positions, population):
    input_text = build_input(grid, positions, population)
    result = subprocess.run(
        [EVO_BIN], input=input_text.encode(), capture_output=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"C++ error: {result.stderr.decode()}", file=sys.stderr)
        raise RuntimeError("evo_sim failed")
    n_sims = len(population)
    data = np.frombuffer(result.stdout, dtype=np.uint8)
    if len(data) != n_sims * H * W:
        raise RuntimeError(f"Expected {n_sims * H * W} bytes, got {len(data)}")
    return data.reshape(n_sims, H, W)


def score_likelihood(grids, gt, eps=1e-12):
    """Score each simulation grid against the ground truth distribution.

    For each particle i, compute:
      LL_i = sum over (y,x) of log(gt[y, x, grid_i[y,x]])

    This is the log-likelihood of the particle's final grid under the
    ground truth distribution. Higher = better match.
    """
    n = grids.shape[0]
    # Precompute log(gt) clamped
    log_gt = np.log(np.maximum(gt, eps))  # (H, W, 6)

    scores = np.zeros(n, dtype=np.float64)
    for i in range(n):
        # Fancy index: for each cell, look up log_gt[y, x, class]
        yy, xx = np.mgrid[:H, :W]
        scores[i] = log_gt[yy, xx, grids[i]].sum()
    return scores


def refit_and_resample(population, scores, rng, target_n, survival_rate):
    n_survive = max(2, int(len(population) * survival_rate))
    top_idx = np.argsort(scores)[-n_survive:]
    survivors = [population[i] for i in top_idx]

    # Refit param distributions
    param_values = np.array([[s[1][name] for name in PARAM_NAMES] for s in survivors])
    means = param_values.mean(axis=0)
    stds = np.maximum(param_values.std(axis=0), 1e-6)

    # Refit initial stat distributions
    n_settle = len(survivors[0][0])
    stat_means = np.zeros((n_settle, 4))
    stat_stds = np.zeros((n_settle, 4))
    for j in range(n_settle):
        vals = np.array([s[0][j] for s in survivors])
        stat_means[j] = vals.mean(axis=0)
        stat_stds[j] = np.maximum(vals.std(axis=0), 1e-4)

    new_pop = list(survivors)
    while len(new_pop) < target_n:
        params = sample_params(rng, means, stds)
        stats = []
        for j in range(n_settle):
            pop = max(0.50, min(1.50, rng.gauss(stat_means[j, 0], stat_stds[j, 0])))
            food = max(0.30, min(0.80, rng.gauss(stat_means[j, 1], stat_stds[j, 1])))
            wealth = max(0.10, min(0.50, rng.gauss(stat_means[j, 2], stat_stds[j, 2])))
            defense = max(0.20, min(0.60, rng.gauss(stat_means[j, 3], stat_stds[j, 3])))
            stats.append((pop, food, wealth, defense))
        new_pop.append((stats, params))
    return new_pop[:target_n]


def grids_to_prediction(grids):
    n = grids.shape[0]
    counts = np.zeros((H, W, NUM_CLASSES), dtype=np.float64)
    for c in range(NUM_CLASSES):
        counts[:, :, c] = np.sum(grids == c, axis=0)
    alpha = 0.015
    return (counts + alpha) / (n + alpha * NUM_CLASSES)


def main():
    rng = random.Random(42)

    print("Loading initial state...")
    seed_data = load_initial_state()
    grid = seed_data["grid"]
    positions = seed_data["settlements"]
    n_settle = len(positions)

    gt = load_ground_truth()
    print(f"  Grid: {H}×{W}, {n_settle} settlements")

    # Initialize
    print(f"\nInitializing {N_POP} particles from priors...")
    population = []
    for _ in range(N_POP):
        stats = sample_initial_stats(rng, n_settle)
        params = sample_params(rng)
        population.append((stats, params))

    # Iterative refinement
    for it in range(N_ITERS):
        grids = run_simulations(grid, positions, population)
        scores = score_likelihood(grids, gt)

        # Aggregate score
        prediction = grids_to_prediction(grids)
        agg_score = score_fun(gt, prediction)

        best_ll = scores.max()
        median_ll = np.median(scores)

        # Print top survivor param summary
        n_survive = max(2, int(N_POP * SURVIVAL_RATE))
        top_idx = np.argsort(scores)[-n_survive:]
        top_params = np.array([[population[i][1][name] for name in PARAM_NAMES] for i in top_idx])
        param_summary = "  ".join(
            f"{name}={top_params[:, i].mean():.3f}±{top_params[:, i].std():.3f}"
            for i, name in enumerate(PARAM_NAMES)
            if name in ("alpha_plains", "alpha_forest", "beta", "mu_spawn", "collapse_s")
        )

        print(f"  Iter {it+1:2d}/{N_ITERS}: score={agg_score:5.1f}  "
              f"best_ll={best_ll:.0f}  median_ll={median_ll:.0f}  {param_summary}")

        # Refit and resample
        population = refit_and_resample(population, scores, rng, N_POP, SURVIVAL_RATE)

    # Final expansion
    print(f"\nFinal expansion to {N_FINAL} particles...")
    # Use last iteration's scores for the refit
    grids = run_simulations(grid, positions, population)
    scores = score_likelihood(grids, gt)
    population = refit_and_resample(population, scores, rng, N_FINAL, SURVIVAL_RATE)

    print("Running final simulations...")
    grids = run_simulations(grid, positions, population)
    prediction = grids_to_prediction(grids)

    score = score_fun(gt, prediction)
    print(f"\nFinal score: {score:.2f}")

    # Print final param estimates
    print("\nFinal parameter estimates (population mean ± std):")
    param_values = np.array([[s[1][name] for name in PARAM_NAMES] for s in population])
    for i, name in enumerate(PARAM_NAMES):
        m = param_values[:, i].mean()
        s = param_values[:, i].std()
        print(f"  {name:>20s}: {m:.4f} ± {s:.4f}")


if __name__ == "__main__":
    main()

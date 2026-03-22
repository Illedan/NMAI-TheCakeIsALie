"""Evolutionary parameter search for Astar Island simulation.

Scores each particle by its "surprise" under the ground truth distribution:
  surprise_i = -sum over (y,x) of log(gt[y, x, sim_grid_i[y,x]])

Lower surprise = the simulated grid is more likely under the ground truth.
Each iteration keeps the lowest-surprise sub-population, fits Gaussians
to their hidden params, and resamples a new population.
"""

import json
import glob
import math
import os
import random
import subprocess
import sys

import numpy as np

from prepare import score_fun, RAW_TO_CLASS

# ── Configuration ──
ROUND_ID = "36e581f1-73f8-453f-ab98-cbe3052b701b"
SEED_IDX = 0
N_POP = 100
N_RUNS_PER_PARTICLE = 30
N_STEPS = 50
N_ITERS = 40
SURVIVAL_RATE = 0.30
N_FINAL = 100
N_FINAL_RUNS = 100
H, W = 40, 40
NUM_CLASSES = 6
EVO_BIN = "./evo_sim"

INITIAL_STATES_DIR = "initial_states"
ANALYSIS_DIR = "analysis"

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


# ── Data loading ──

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


# ── Sampling ──

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


# ── C++ interface ──

def build_input(grid, positions, population, rng_offset=0, n_runs=N_RUNS_PER_PARTICLE):
    n_settle = len(positions)
    n_particles = len(population)
    lines = [f"{H} {W} {n_settle} {n_particles} {N_STEPS} {rng_offset} {n_runs}"]
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


_rng_counter = 0

def run_simulations(grid, positions, population, n_runs=N_RUNS_PER_PARTICLE):
    """Run evo_sim. Returns (n_particles, H, W, 6) uint16 count arrays."""
    global _rng_counter
    _rng_counter += 1
    input_text = build_input(grid, positions, population,
                             rng_offset=_rng_counter * 100003, n_runs=n_runs)
    result = subprocess.run(
        [EVO_BIN], input=input_text.encode(), capture_output=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"C++ error: {result.stderr.decode()}", file=sys.stderr)
        raise RuntimeError("evo_sim failed")
    n_particles = len(population)
    data = np.frombuffer(result.stdout, dtype=np.uint16)
    expected = n_particles * H * W * NUM_CLASSES
    if len(data) != expected:
        raise RuntimeError(f"Expected {expected} uint16s, got {len(data)}")
    return data.reshape(n_particles, H, W, NUM_CLASSES)


# ── Scoring ──

def counts_to_prediction(counts, n_runs, eps_floor=0.01):
    """Convert per-particle counts (H, W, 6) to probability distribution."""
    pred = counts.astype(np.float64) / n_runs
    pred = np.maximum(pred, eps_floor)
    pred /= pred.sum(axis=-1, keepdims=True)
    return pred


def score_particles(all_counts, gt, n_runs):
    """Score each particle using the competition score formula.

    Each particle has H×W×6 counts from n_runs simulations.
    Converts to distribution, computes entropy-weighted KL vs ground truth.
    Returns array of scores (higher = better).
    """
    n_particles = all_counts.shape[0]
    scores = np.zeros(n_particles, dtype=np.float64)

    # Precompute ground truth entropy per cell
    gt_ent = -np.sum(gt * np.log(gt + 1e-12), axis=-1)  # (H, W)

    for i in range(n_particles):
        pred = counts_to_prediction(all_counts[i], n_runs)
        # Per-cell KL: sum_c gt * log(gt / pred)
        kl = np.sum(gt * np.log((gt + 1e-12) / (pred + 1e-12)), axis=-1)  # (H, W)
        # Entropy-weighted mean KL
        total_ent = gt_ent.sum()
        if total_ent > 0:
            wkl = np.sum(gt_ent * kl) / total_ent
        else:
            wkl = 0.0
        scores[i] = max(0.0, min(100.0, 100.0 * np.exp(-3.0 * wkl)))
    return scores


# ── Selection & resampling ──

def refit_and_resample(population, scores, rng, target_n):
    """Keep highest-scoring particles, fit Gaussians, resample ALL from fitted distributions."""
    n_survive = max(2, int(len(population) * SURVIVAL_RATE))
    # Highest score = best → take top n_survive
    top_idx = np.argsort(scores)[-n_survive:]
    survivors = [population[i] for i in top_idx]

    # Fit Gaussians to hidden params of survivors
    param_values = np.array([[s[1][name] for name in PARAM_NAMES] for s in survivors])
    means = param_values.mean(axis=0)
    stds = np.maximum(param_values.std(axis=0), 1e-6)

    # Fit Gaussians to initial stats of survivors
    n_settle = len(survivors[0][0])
    stat_means = np.zeros((n_settle, 4))
    stat_stds = np.zeros((n_settle, 4))
    for j in range(n_settle):
        vals = np.array([s[0][j] for s in survivors])
        stat_means[j] = vals.mean(axis=0)
        stat_stds[j] = np.maximum(vals.std(axis=0), 1e-4)

    # Resample ALL particles from fitted Gaussians (no survivors kept as-is)
    new_pop = []
    for _ in range(target_n):
        params = sample_params(rng, means, stds)
        stats = []
        for j in range(n_settle):
            pop = max(0.50, min(1.50, rng.gauss(stat_means[j, 0], stat_stds[j, 0])))
            food = max(0.30, min(0.80, rng.gauss(stat_means[j, 1], stat_stds[j, 1])))
            wealth = max(0.10, min(0.50, rng.gauss(stat_means[j, 2], stat_stds[j, 2])))
            defense = max(0.20, min(0.60, rng.gauss(stat_means[j, 3], stat_stds[j, 3])))
            stats.append((pop, food, wealth, defense))
        new_pop.append((stats, params))

    return new_pop


def grids_to_prediction(grids):
    n = grids.shape[0]
    counts = np.zeros((H, W, NUM_CLASSES), dtype=np.float64)
    for c in range(NUM_CLASSES):
        counts[:, :, c] = np.sum(grids == c, axis=0)
    alpha = 0.015
    return (counts + alpha) / (n + alpha * NUM_CLASSES)


# ── Main ──

def main():
    rng = random.Random(42)

    print("Loading initial state...")
    seed_data = load_initial_state()
    grid = seed_data["grid"]
    positions = seed_data["settlements"]
    n_settle = len(positions)

    gt = load_ground_truth()
    print(f"  Grid: {H}×{W}, {n_settle} settlements")

    # Initialize population from priors
    print(f"\nInitializing {N_POP} particles from priors...")
    population = []
    for _ in range(N_POP):
        stats = sample_initial_stats(rng, n_settle)
        params = sample_params(rng)
        population.append((stats, params))

    # Iterative refinement
    for it in range(N_ITERS):
        all_counts = run_simulations(grid, positions, population)
        scores = score_particles(all_counts, gt, N_RUNS_PER_PARTICLE)

        # Aggregate prediction for reporting
        total_counts = all_counts.sum(axis=0).astype(np.float64)
        total_n = N_POP * N_RUNS_PER_PARTICLE
        alpha = 0.015
        agg_pred = (total_counts + alpha) / (total_n + alpha * NUM_CLASSES)
        agg_score = score_fun(gt, agg_pred)

        # Print summary
        n_survive = max(2, int(N_POP * SURVIVAL_RATE))
        top_idx = np.argsort(scores)[-n_survive:]
        top_params = np.array([[population[i][1][name] for name in PARAM_NAMES] for i in top_idx])

        key_params = ["alpha_plains", "alpha_forest", "beta", "mu_spawn", "collapse_s"]
        param_summary = "  ".join(
            f"{name}={top_params[:, PARAM_NAMES.index(name)].mean():.3f}"
            for name in key_params
        )

        print(f"  Iter {it+1:2d}/{N_ITERS}: agg_score={agg_score:5.1f}  "
              f"particle_score: best={scores.max():.1f} median={np.median(scores):.1f}  "
              f"{param_summary}")

        # Select highest-scoring, refit Gaussians, resample ALL
        population = refit_and_resample(population, scores, rng, N_POP)

    # Final: more runs per particle for better distributions
    print(f"\nFinal run: {N_FINAL} particles × {N_FINAL_RUNS} runs each...")
    all_counts = run_simulations(grid, positions, population, n_runs=N_FINAL_RUNS)

    # Aggregate all counts
    total_counts = all_counts.sum(axis=0).astype(np.float64)
    total_n = N_FINAL * N_FINAL_RUNS
    alpha = 0.015
    prediction = (total_counts + alpha) / (total_n + alpha * NUM_CLASSES)

    score = score_fun(gt, prediction)
    print(f"\nFinal score: {score:.2f}")

    # Print final parameter estimates
    print("\nFinal parameter estimates (survivor mean ± std):")
    param_values = np.array([[s[1][name] for name in PARAM_NAMES] for s in population])
    for i, name in enumerate(PARAM_NAMES):
        m = param_values[:, i].mean()
        s = param_values[:, i].std()
        _, e, prior_s, _, _ = PARAM_SPEC[i]
        print(f"  {name:>20s}: {m:.4f} ± {s:.4f}  (prior: {e:.4f} ± {prior_s:.4f})")


if __name__ == "__main__":
    main()

"""Calibrate agent simulator parameters against replay data.

Uses hill-climbing to find parameters that minimize KL divergence
between simulated and ground truth probability distributions.
"""

import json
import glob
import os
import numpy as np
from pathlib import Path
from .params import AgentParams
from .simulator import monte_carlo, monte_carlo_from_data
from .world import NUM_CLASSES


def load_ground_truth(analysis_path: str) -> dict:
    """Load ground truth from analysis JSON."""
    with open(analysis_path) as f:
        data = json.load(f)
    return {
        'ground_truth': np.array(data['ground_truth']),
        'score': data.get('score', None),
        'width': data.get('width', 40),
        'height': data.get('height', 40),
    }


def compute_score(prediction: np.ndarray, ground_truth: np.ndarray) -> float:
    """Compute competition score: entropy-weighted KL divergence.

    score = max(0, min(100, 100 * exp(-3 * weighted_kl)))
    """
    eps = 1e-10
    gt = np.clip(ground_truth, eps, 1.0)
    pred = np.clip(prediction, eps, 1.0)

    # Renormalize
    gt = gt / gt.sum(axis=-1, keepdims=True)
    pred = pred / pred.sum(axis=-1, keepdims=True)

    # Per-cell entropy of ground truth
    entropy = -np.sum(gt * np.log(gt), axis=-1)  # (H, W)

    # Per-cell KL divergence
    kl = np.sum(gt * np.log(gt / pred), axis=-1)  # (H, W)

    # Weighted KL
    total_entropy = entropy.sum()
    if total_entropy < eps:
        return 100.0

    weighted_kl = (entropy * kl).sum() / total_entropy

    score = max(0.0, min(100.0, 100.0 * np.exp(-3.0 * weighted_kl)))
    return score


def find_round_files(base_dir: str) -> list[dict]:
    """Find matching initial_state + analysis file pairs."""
    analysis_dir = os.path.join(base_dir, 'astar-island', 'analysis')
    init_dir = os.path.join(base_dir, 'astar-island', 'initial_states')

    pairs = []
    for analysis_file in sorted(glob.glob(os.path.join(analysis_dir, '*.json'))):
        fname = os.path.basename(analysis_file)
        # Extract seed number
        seed_match = None
        for part in fname.split('_'):
            if part.startswith('seed'):
                continue
            try:
                seed_num = int(part)
                if 0 <= seed_num <= 4:
                    seed_match = seed_num
            except ValueError:
                continue

        # Find seed in filename
        if 'seed_0' in fname:
            seed_match = 0
        elif 'seed_1' in fname:
            seed_match = 1
        elif 'seed_2' in fname:
            seed_match = 2
        elif 'seed_3' in fname:
            seed_match = 3
        elif 'seed_4' in fname:
            seed_match = 4

        if seed_match is None:
            continue

        # Find round ID in filename (UUID fragment)
        parts = fname.replace('.json', '').split('_')
        # Look for UUID-like parts
        round_id = None
        for part in parts:
            if len(part) >= 8 and '-' in part:
                round_id = part.split('-')[0] if '-' in part else part[:8]
                round_id_full = '-'.join(p for p in parts if '-' in p or len(p) == 8)
                break

        # Find matching initial_state directory
        for init_subdir in os.listdir(init_dir):
            init_path = os.path.join(init_dir, init_subdir,
                                     f'seed_{seed_match}.json')
            if os.path.exists(init_path):
                # Check if round IDs match (last 8 chars of dir name)
                dir_round = init_subdir.split('_')[-1]
                if round_id and dir_round[:8] == round_id[:8]:
                    pairs.append({
                        'analysis': analysis_file,
                        'initial_state': init_path,
                        'seed': seed_match,
                        'round_dir': init_subdir,
                    })

    return pairs


def evaluate_params(params: AgentParams, initial_state_path: str,
                    ground_truth: np.ndarray, n_sims: int = 100) -> float:
    """Run MC with given params and score against ground truth."""
    prediction = monte_carlo(initial_state_path, params, n_sims=n_sims)
    return compute_score(prediction, ground_truth)


def hill_climb(initial_state_path: str, ground_truth: np.ndarray,
               params: AgentParams = None, n_iterations: int = 50,
               n_sims: int = 100, verbose: bool = True) -> AgentParams:
    """Hill-climb parameters to maximize score on a single round."""
    if params is None:
        params = AgentParams()

    best_params = params.copy()
    best_score = evaluate_params(best_params, initial_state_path,
                                 ground_truth, n_sims)

    if verbose:
        print(f"Initial score: {best_score:.2f}")

    float_names = AgentParams.float_field_names()
    rng = np.random.default_rng(42)

    for iteration in range(n_iterations):
        # Pick a random parameter to perturb
        param_idx = rng.integers(len(float_names))
        param_name = float_names[param_idx]
        current_val = getattr(best_params, param_name)

        # Perturbation: proportional to current value
        scale = max(0.01, abs(current_val) * 0.2)
        delta = rng.normal(0, scale)
        new_val = current_val + delta

        # Clamp to reasonable ranges
        if 'prob' in param_name or 'rate' in param_name or 'factor' in param_name:
            new_val = max(0.001, new_val)
        if param_name.startswith('init_') and 'std' in param_name:
            new_val = max(0.01, new_val)

        trial_params = best_params.copy()
        setattr(trial_params, param_name, new_val)

        trial_score = evaluate_params(trial_params, initial_state_path,
                                      ground_truth, n_sims)

        if trial_score > best_score:
            best_params = trial_params
            best_score = trial_score
            if verbose:
                print(f"  [{iteration}] {param_name}: {current_val:.4f} -> "
                      f"{new_val:.4f} => score {best_score:.2f}")

    if verbose:
        print(f"Final score: {best_score:.2f}")

    return best_params


def hill_climb_multi(pairs: list[dict], params: AgentParams = None,
                     n_iterations: int = 200, n_sims: int = 50,
                     verbose: bool = True) -> AgentParams:
    """Hill-climb parameters to maximize average score across multiple rounds.

    Uses stochastic evaluation: each iteration tests on a random subset
    of rounds for speed, with periodic full evaluations.
    """
    if params is None:
        params = AgentParams()

    # Preload all ground truths
    gt_data = []
    for pair in pairs:
        gt = load_ground_truth(pair['analysis'])['ground_truth']
        gt_data.append((pair['initial_state'], gt))

    def eval_subset(p: AgentParams, indices: list[int]) -> float:
        scores = []
        for idx in indices:
            init_path, gt = gt_data[idx]
            s = evaluate_params(p, init_path, gt, n_sims)
            scores.append(s)
        return np.mean(scores)

    def eval_all(p: AgentParams) -> float:
        return eval_subset(p, list(range(len(gt_data))))

    best_params = params.copy()
    best_score = eval_all(best_params)

    if verbose:
        print(f"Initial avg score across {len(pairs)} rounds: {best_score:.2f}")

    float_names = AgentParams.float_field_names()
    rng = np.random.default_rng(42)

    # Adaptive step sizes per parameter
    step_sizes = {}
    for name in float_names:
        val = abs(getattr(best_params, name))
        step_sizes[name] = max(0.01, val * 0.3)

    no_improve_count = 0
    n_rounds = len(gt_data)
    # Evaluate on 3 random rounds per iteration (stochastic hill-climbing)
    subset_size = min(3, n_rounds)

    for iteration in range(n_iterations):
        # Pick random subset of rounds to evaluate
        round_indices = rng.choice(n_rounds, size=subset_size, replace=False).tolist()

        # Multi-param perturbation: perturb 1-3 params at once
        n_perturb = rng.integers(1, 4)
        param_indices = rng.choice(len(float_names), size=n_perturb, replace=False)

        trial_params = best_params.copy()
        changes = []
        for idx in param_indices:
            param_name = float_names[idx]
            current_val = getattr(best_params, param_name)
            delta = rng.normal(0, step_sizes[param_name])
            new_val = current_val + delta

            # Clamp
            if 'prob' in param_name or 'rate' in param_name or 'factor' in param_name:
                new_val = max(0.001, new_val)
            if param_name.startswith('init_') and 'std' in param_name:
                new_val = max(0.01, new_val)

            setattr(trial_params, param_name, new_val)
            changes.append((param_name, current_val, new_val))

        # Quick eval on subset
        trial_subset = eval_subset(trial_params, round_indices)
        best_subset = eval_subset(best_params, round_indices)

        if trial_subset > best_subset:
            # Confirm with full evaluation every time to avoid noise
            trial_full = eval_all(trial_params)
            if trial_full > best_score:
                improvement = trial_full - best_score
                best_params = trial_params
                best_score = trial_full
                no_improve_count = 0

                for name, old_v, new_v in changes:
                    step_sizes[name] *= 1.2

                if verbose:
                    change_str = ", ".join(f"{n}: {o:.4f}->{v:.4f}" for n, o, v in changes)
                    print(f"  [{iteration}] +{improvement:.2f} => {best_score:.2f}  ({change_str})")
        else:
            no_improve_count += 1
            if no_improve_count % 15 == 0:
                for name in float_names:
                    step_sizes[name] *= 0.85

    if verbose:
        print(f"\nFinal avg score: {best_score:.2f}")

    return best_params


def cross_validate(base_dir: str, params: AgentParams = None,
                   n_sims: int = 100, verbose: bool = True) -> dict:
    """Evaluate params across all available rounds."""
    if params is None:
        params = AgentParams()

    pairs = find_round_files(base_dir)
    if verbose:
        print(f"Found {len(pairs)} round-seed pairs")

    scores = {}
    for pair in pairs:
        score = evaluate_params(params, pair['initial_state'],
                               load_ground_truth(pair['analysis'])['ground_truth'],
                               n_sims)
        key = f"{pair['round_dir']}/seed_{pair['seed']}"
        scores[key] = score
        if verbose:
            print(f"  {key}: {score:.2f}")

    if scores:
        avg = np.mean(list(scores.values()))
        if verbose:
            print(f"Average score: {avg:.2f}")

    return scores

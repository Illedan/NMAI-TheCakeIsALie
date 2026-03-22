#!/usr/bin/env python3
"""Validate agent simulator against replay data and compare with Markov chain."""

import json
import os
import sys
import time
import numpy as np
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_sim.params import AgentParams
from agent_sim.simulator import monte_carlo, save_prediction
from agent_sim.calibrate import (
    compute_score, find_round_files, load_ground_truth,
    evaluate_params, hill_climb, hill_climb_multi
)


def test_single_round(initial_state_path: str, analysis_path: str,
                      params: AgentParams = None, n_sims: int = 200):
    """Test agent sim on a single round and report score."""
    if params is None:
        params = AgentParams()

    gt_data = load_ground_truth(analysis_path)
    ground_truth = gt_data['ground_truth']
    organizer_score = gt_data.get('score')

    print(f"Running {n_sims} Monte Carlo simulations...")
    t0 = time.time()
    prediction = monte_carlo(initial_state_path, params, n_sims=n_sims)
    elapsed = time.time() - t0
    print(f"  Elapsed: {elapsed:.1f}s ({elapsed/n_sims*1000:.0f}ms/sim)")

    score = compute_score(prediction, ground_truth)
    print(f"  Agent sim score: {score:.2f}")
    if organizer_score is not None:
        print(f"  Our submitted score: {organizer_score:.2f}")

    return score, prediction


def test_all_rounds(base_dir: str, n_sims: int = 100, params: AgentParams = None):
    """Test params on all available rounds."""
    if params is None:
        params = AgentParams()
    pairs = find_round_files(base_dir)

    print(f"Found {len(pairs)} round-seed pairs\n")

    # Group by round
    round_scores = {}
    for pair in pairs:
        gt_data = load_ground_truth(pair['analysis'])
        ground_truth = gt_data['ground_truth']
        organizer_score = gt_data.get('score')

        prediction = monte_carlo(pair['initial_state'], params, n_sims=n_sims)
        score = compute_score(prediction, ground_truth)

        round_id = pair['round_dir'].split('_')[-1][:8]
        if round_id not in round_scores:
            round_scores[round_id] = []

        label = f"{pair['round_dir']}/seed_{pair['seed']}"
        submitted = f" (submitted: {organizer_score:.1f})" if organizer_score else ""
        print(f"  {label}: {score:.2f}{submitted}")
        round_scores[round_id].append(score)

    if round_scores:
        all_scores = []
        print(f"\nPer-round averages:")
        for rid, scores in sorted(round_scores.items()):
            avg = np.mean(scores)
            print(f"  {rid}: {avg:.1f} (n={len(scores)})")
            all_scores.extend(scores)
        print(f"\nOverall: avg={np.mean(all_scores):.2f}, "
              f"min={np.min(all_scores):.2f}, max={np.max(all_scores):.2f}")


def test_with_hill_climb(initial_state_path: str, analysis_path: str,
                         n_hc_iters: int = 100, n_sims_hc: int = 50,
                         n_sims_eval: int = 200):
    """Test with hill-climbed parameters on a single round."""
    gt_data = load_ground_truth(analysis_path)
    ground_truth = gt_data['ground_truth']

    print("Hill-climbing parameters...")
    params = hill_climb(initial_state_path, ground_truth,
                       n_iterations=n_hc_iters, n_sims=n_sims_hc)

    print(f"\nEvaluating with {n_sims_eval} simulations...")
    prediction = monte_carlo(initial_state_path, params, n_sims=n_sims_eval)
    score = compute_score(prediction, ground_truth)
    print(f"Hill-climbed score: {score:.2f}")

    return score, params


def test_multi_hill_climb(base_dir: str, n_hc_iters: int = 200,
                          n_sims_hc: int = 20, n_sims_eval: int = 100):
    """Hill-climb across all rounds to find generalizing params."""
    pairs = find_round_files(base_dir)
    if not pairs:
        print("No round files found!")
        return

    # Use a subset of seeds for hill-climbing (1 per round for speed)
    # Group by round
    rounds = {}
    for pair in pairs:
        round_id = pair['round_dir'].split('_')[-1][:8]
        if round_id not in rounds:
            rounds[round_id] = pair

    hc_pairs = list(rounds.values())
    print(f"Hill-climbing across {len(hc_pairs)} rounds (1 seed each)...")

    t0 = time.time()
    best_params = hill_climb_multi(
        hc_pairs, n_iterations=n_hc_iters, n_sims=n_sims_hc)
    elapsed = time.time() - t0
    print(f"Hill-climbing took {elapsed:.0f}s")

    # Print optimized params
    print("\nOptimized parameters:")
    float_names = AgentParams.float_field_names()
    default = AgentParams()
    for name in float_names:
        old_val = getattr(default, name)
        new_val = getattr(best_params, name)
        if abs(new_val - old_val) > 0.001:
            print(f"  {name}: {old_val:.4f} -> {new_val:.4f}")

    # Evaluate on ALL seeds
    print(f"\nFull evaluation with {n_sims_eval} sims on all {len(pairs)} pairs:")
    test_all_rounds(base_dir, n_sims=n_sims_eval, params=best_params)

    # Save optimized params
    params_dict = {name: getattr(best_params, name) for name in float_names}
    params_path = os.path.join(base_dir, 'astar-erik', 'agent_sim', 'optimized_params.json')
    with open(params_path, 'w') as f:
        json.dump(params_dict, f, indent=2)
    print(f"\nSaved optimized params to {params_path}")

    return best_params


if __name__ == '__main__':
    base_dir = str(Path(__file__).parent.parent.parent)

    if len(sys.argv) > 1 and sys.argv[1] == '--hill-climb':
        # Hill-climb on a specific round
        pairs = find_round_files(base_dir)
        if pairs:
            pair = pairs[0]  # Use first available
            print(f"Hill-climbing on {pair['round_dir']}/seed_{pair['seed']}")
            test_with_hill_climb(pair['initial_state'], pair['analysis'])
    elif len(sys.argv) > 1 and sys.argv[1] == '--hill-climb-all':
        # Hill-climb across ALL rounds
        n_iters = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        test_multi_hill_climb(base_dir, n_hc_iters=n_iters)
    else:
        # Test all rounds with default params
        test_all_rounds(base_dir, n_sims=50)

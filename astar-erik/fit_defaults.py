#!/usr/bin/env python3
"""
Find optimal default TuneParams by fitting the parametric model to replay data.
Uses scipy.optimize to minimize KL divergence between model predictions
and observed transition frequencies across ALL replays.
"""
import struct, sys
import numpy as np
from scipy.optimize import minimize

NUM_CLASSES = 6
FEAT_DIM = 6
CLASS_NAMES = ['Empty', 'Settlement', 'Port', 'Ruin', 'Forest', 'Mountain']


def load_binary(path):
    with open(path, 'rb') as f:
        n, fdim = struct.unpack('ii', f.read(8))
        feats = np.frombuffer(f.read(n * fdim * 4), dtype=np.float32).reshape(n, fdim).copy()
        targets = np.frombuffer(f.read(n), dtype=np.uint8).astype(np.int64).copy()
    return feats, targets


def compute_transition_stats(feats, targets):
    """Bin transitions by discretized features, compute empirical distributions."""
    # Discretize features into bins for aggregation
    # Features: [ns/8, nf/8, nr/8, sr2/16, ocean, dist/15]
    ns = (feats[:, 0] * 8).round().astype(int)  # 0-8
    nf = (feats[:, 1] * 8).round().astype(int)
    nr = (feats[:, 2] * 8).round().astype(int)
    sr2 = (feats[:, 3] * 16).round().astype(int)
    ocean = feats[:, 4].round().astype(int)

    # Group by (ns, ocean) for simplicity
    stats = {}
    for i in range(len(feats)):
        key = (int(ns[i]), int(nf[i]), int(nr[i]), int(sr2[i]), int(ocean[i]))
        if key not in stats:
            stats[key] = np.zeros(NUM_CLASSES)
        stats[key][targets[i]] += 1

    return stats


def get_transition_probs_parametric(src_class, ns, nf, nr, sr2, ocean, params):
    """Python reimplementation of get_transition_probs for fitting."""
    probs = np.zeros(NUM_CLASSES)

    if src_class == 0:  # Empty
        p_s = params['es_base'] * np.exp(params['es_ns_coeff'] * ns + params['es_ns2_coeff'] * ns**2 + params['es_sr2_coeff'] * sr2)
        p_s = min(p_s, 0.5)
        p_r = p_s * params['er_ratio']
        p_f = 0  # empty doesn't become forest directly
        probs[0] = max(0, 1 - p_s - p_r)
        probs[1] = p_s
        probs[3] = p_r
    elif src_class == 1:  # Settlement
        support = ns + params['sr_nf_weight'] * nf
        p_r = (params['sr_base'] * np.exp(-params['sr_support'] * support)
               + params['sr_raid'] * ns
               + params['sr_ruin_coeff'] * nr
               + params['sr_sr2_coeff'] * sr2)
        p_r = min(max(p_r, 0), 0.5)
        p_p = 0
        if ocean:
            p_p = params['sp_base'] * np.exp(params['sp_ns_coeff'] * ns)
            p_p = min(max(p_p, 0), 0.3)
        probs[1] = max(0, 1 - p_r - p_p)
        probs[2] = p_p
        probs[3] = p_r
    elif src_class == 2:  # Port
        p_r = params['pr_base'] * np.exp(params['pr_ns_coeff'] * ns)
        p_r = min(max(p_r, 0), 0.5)
        probs[2] = 1 - p_r
        probs[3] = p_r
    elif src_class == 3:  # Ruin
        rs = params['ruin_settle'] * (1 + params['ruin_ns_coeff'] * ns)
        re = params['ruin_empty']
        rf = params['ruin_forest']
        rp = params['ruin_port'] if ocean else 0
        total = rs + re + rf + rp
        if total > 0.99:
            scale = 0.99 / total
            rs *= scale; re *= scale; rf *= scale; rp *= scale
        probs[0] = re
        probs[1] = rs
        probs[2] = rp
        probs[3] = max(0, 1 - rs - re - rf - rp)
        probs[4] = rf
    elif src_class == 4:  # Forest
        p_s = params['fs_base'] * np.exp(params['fs_ns_coeff'] * ns + params['fs_ns2_coeff'] * ns**2)
        p_s = min(p_s, 0.5)
        p_r = p_s * params['fr_ratio']
        probs[1] = p_s
        probs[3] = p_r
        probs[4] = max(0, 1 - p_s - p_r)

    # Normalize
    total = probs.sum()
    if total > 0:
        probs /= total
    return probs


# Parameter vector <-> dict mapping
PARAM_NAMES = [
    'es_base', 'es_ns_coeff', 'es_ns2_coeff', 'es_sr2_coeff', 'er_ratio',
    'sr_base', 'sr_support', 'sr_nf_weight', 'sr_sr2_coeff', 'sr_raid', 'sr_ruin_coeff',
    'sp_base', 'sp_ns_coeff',
    'fs_base', 'fs_ns_coeff', 'fs_ns2_coeff', 'fr_ratio',
    'pr_base', 'pr_ns_coeff',
    'ruin_settle', 'ruin_empty', 'ruin_forest', 'ruin_port', 'ruin_ns_coeff',
]
PARAM_DEFAULTS = [
    0.004, 0.35, 0.0, 0.12, 0.15,
    0.10, 0.08, 0.8, 0.003, 0.015, 0.03,
    0.104, -0.08,
    0.005, 0.45, 0.0, 0.20,
    0.048, -0.04,
    0.48, 0.34, 0.16, 0.015, 0.05,
]
PARAM_BOUNDS = [
    (0.0001, 0.10), (0.01, 1.5), (-0.1, 0.2), (0.0, 0.5), (0.01, 0.5),
    (0.01, 0.30), (0.0, 0.5), (0.0, 2.0), (0.0, 0.05), (0.0, 0.06), (0.0, 0.10),
    (0.02, 0.25), (-0.3, 0.1),
    (0.0001, 0.10), (0.01, 1.5), (-0.1, 0.2), (0.01, 0.5),
    (0.01, 0.15), (-0.2, 0.1),
    (0.05, 0.80), (0.05, 0.80), (0.02, 0.50), (0.001, 0.10), (0.0, 0.2),
]


def params_from_vec(vec):
    return dict(zip(PARAM_NAMES, vec))


def objective(vec, all_data):
    """Compute negative log-likelihood of observed transitions under parametric model."""
    params = params_from_vec(vec)
    total_nll = 0
    total_n = 0

    for src_class in range(5):
        if src_class not in all_data:
            continue
        stats = all_data[src_class]
        for key, counts in stats.items():
            ns, nf, nr, sr2, ocean = key
            n = counts.sum()
            if n < 5:
                continue
            probs = get_transition_probs_parametric(src_class, ns, nf, nr, sr2, ocean, params)
            # Cross-entropy
            emp = counts / n
            for c in range(NUM_CLASSES):
                if emp[c] > 0.001:
                    p = max(probs[c], 1e-6)
                    total_nll -= n * emp[c] * np.log(p)
            total_n += n

    return total_nll / max(total_n, 1)


def main():
    # Load all transition data
    src_classes = ['empty', 'settlement', 'port', 'ruin', 'forest']
    all_data = {}

    for ci, cname in enumerate(src_classes):
        path = f'transitions_{cname}.bin'
        try:
            feats, targets = load_binary(path)
        except FileNotFoundError:
            continue

        # Subsample for speed
        if len(feats) > 3_000_000:
            idx = np.random.choice(len(feats), 3_000_000, replace=False)
            feats, targets = feats[idx], targets[idx]

        stats = compute_transition_stats(feats, targets)
        all_data[ci] = stats
        print(f"{CLASS_NAMES[ci]}: {len(stats)} unique feature combos, {sum(v.sum() for v in stats.values()):.0f} samples")

    # Initial loss
    x0 = np.array(PARAM_DEFAULTS)
    loss0 = objective(x0, all_data)
    print(f"\nInitial loss (defaults): {loss0:.6f}")

    # Optimize
    print("\nOptimizing...")
    result = minimize(
        objective, x0, args=(all_data,),
        method='L-BFGS-B',
        bounds=PARAM_BOUNDS,
        options={'maxiter': 500, 'ftol': 1e-8, 'disp': True}
    )

    print(f"\nFinal loss: {result.fun:.6f} (improvement: {loss0 - result.fun:.6f})")
    print(f"Converged: {result.success}, iterations: {result.nit}")

    # Print optimal params
    print("\n// Empirically optimal defaults from replay data:")
    opt = params_from_vec(result.x)
    for name, val, default in zip(PARAM_NAMES, result.x, PARAM_DEFAULTS):
        change = "" if abs(val - default) / max(abs(default), 0.001) < 0.05 else f"  (was {default})"
        print(f"    p.{name:20s} = {val:.6f};{change}")


if __name__ == "__main__":
    main()

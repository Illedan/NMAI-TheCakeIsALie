import numpy as np
import json
import os
import glob as _glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.join(SCRIPT_DIR, "analysis")
REPLAY_DIR = os.path.join(SCRIPT_DIR, "replays")
INITIAL_STATES_DIR = os.path.join(SCRIPT_DIR, "initial_states")
SIMULATIONS_DIR = os.path.join(SCRIPT_DIR, "simulations")

NUM_CLASSES = 6
NSTEPS = 50
RAW_TO_CLASS = {0: 0, 10: 0, 11: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _raw_to_class(grid):
    """Map raw grid values to class indices (0-5)."""
    cg = np.zeros_like(grid)
    for rv, ci in RAW_TO_CLASS.items():
        cg[grid == rv] = ci
    return cg


def discover_rounds():
    """Find all rounds with analysis (ground truth) and cross-reference data sources.

    Returns list of dicts sorted by round_number:
        {round_id, round_number, datestr, analysis_datestr,
         initial_states_dir, simulations_dir (or None),
         has_replays, has_viewports}
    """
    # Find analysis rounds (source of truth for completed rounds)
    analysis_rounds = {}
    for path in sorted(_glob.glob(os.path.join(ANALYSIS_DIR, "*_analysis_seed_0_*.json"))):
        fname = os.path.basename(path)
        parts = fname.replace("_analysis_seed_0_", "|").replace(".json", "").split("|")
        if len(parts) == 2:
            datestr, round_id = parts[0], parts[1]
            if round_id not in analysis_rounds:
                analysis_rounds[round_id] = datestr

    # Map initial_states dirs to round_ids
    is_dirs = {}
    if os.path.isdir(INITIAL_STATES_DIR):
        for d in sorted(os.listdir(INITIAL_STATES_DIR)):
            sp = os.path.join(INITIAL_STATES_DIR, d, "summary.json")
            if os.path.isfile(sp):
                with open(sp) as f:
                    s = json.load(f)
                is_dirs[s["round_id"]] = os.path.join(INITIAL_STATES_DIR, d)

    # Map simulations dirs to round_ids
    sim_dirs = {}
    if os.path.isdir(SIMULATIONS_DIR):
        for d in sorted(os.listdir(SIMULATIONS_DIR)):
            sp = os.path.join(SIMULATIONS_DIR, d, "summary.json")
            if os.path.isfile(sp):
                with open(sp) as f:
                    s = json.load(f)
                sim_dirs[s["round_id"]] = os.path.join(SIMULATIONS_DIR, d)

    # Check replays
    replay_rounds = set()
    for path in _glob.glob(os.path.join(REPLAY_DIR, "*_replay_seed_0_*.json")):
        fname = os.path.basename(path)
        parts = fname.replace("_replay_seed_0_", "|").replace(".json", "").split("|")
        if len(parts) == 2:
            replay_rounds.add(parts[1])

    # Build round list — only rounds with analysis AND initial_states
    rounds = []
    for round_id, datestr in analysis_rounds.items():
        if round_id not in is_dirs:
            continue
        # Determine round_number from summary
        sp = os.path.join(is_dirs[round_id], "summary.json")
        with open(sp) as f:
            s = json.load(f)
        rounds.append({
            "round_id": round_id,
            "round_number": s.get("round_number", 0),
            "analysis_datestr": datestr,
            "initial_states_dir": is_dirs[round_id],
            "simulations_dir": sim_dirs.get(round_id),
            "has_replays": round_id in replay_rounds,
            "has_viewports": round_id in sim_dirs,
        })

    rounds.sort(key=lambda r: r["round_number"])
    return rounds


def load_initial_state(round_info, seed_idx):
    """Load initial state for a seed. Returns (raw_grid, ocean_mask, class_grid)."""
    path = os.path.join(round_info["initial_states_dir"], f"seed_{seed_idx}.json")
    with open(path) as f:
        data = json.load(f)
    raw = np.array(data["grid"], dtype=np.int32)
    ocean_mask = (raw == 10)
    class_grid = _raw_to_class(raw)
    return raw, ocean_mask, class_grid


def load_viewports(round_info, seed_idx):
    """Load viewport observations for a seed.

    Returns list of dicts: {x, y, w, h, class_grid (h,w)}
    Each represents a 15x15 window of one stochastic final-state observation.
    Returns empty list if no viewport data available.
    """
    if not round_info["has_viewports"]:
        return []
    path = os.path.join(round_info["simulations_dir"], f"seed_{seed_idx}.json")
    with open(path) as f:
        data = json.load(f)
    viewports = []
    for item in data:
        vp = item["viewport"]
        resp = item["response"]
        raw_grid = np.array(resp["grid"], dtype=np.int32)
        class_grid = _raw_to_class(raw_grid)
        viewports.append({
            "x": vp["x"], "y": vp["y"], "w": vp["w"], "h": vp["h"],
            "class_grid": class_grid,
        })
    return viewports


def load_ground_truth(round_info, seed_idx):
    """Load ground truth H×W×6 probability tensor."""
    datestr = round_info["analysis_datestr"]
    round_id = round_info["round_id"]
    path = os.path.join(ANALYSIS_DIR, f"{datestr}_analysis_seed_{seed_idx}_{round_id}.json")
    with open(path) as f:
        data = json.load(f)
    return np.array(data["ground_truth"], dtype=np.float64)


def load_replay(round_info, seed_idx):
    """Load replay frames as (51, H, W) class-index array. Returns None if unavailable."""
    if not round_info["has_replays"]:
        return None
    datestr = round_info["analysis_datestr"]
    round_id = round_info["round_id"]
    path = os.path.join(REPLAY_DIR, f"{datestr}_replay_seed_{seed_idx}_{round_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    frames = []
    for frame in data["frames"]:
        grid = np.array(frame["grid"], dtype=np.int32)
        frames.append(_raw_to_class(grid))
    return np.array(frames, dtype=np.int32)


# ---------------------------------------------------------------------------
# Evaluation metrics
# ---------------------------------------------------------------------------

def viewport_log_likelihood(prediction, viewports, eps=1e-12):
    """Mean log-likelihood per observed cell under predicted distribution.

    Parameters
    ----------
    prediction : array (H, W, 6) — predicted probability per cell per class
    viewports : list of viewport dicts from load_viewports

    Returns
    -------
    float — mean log-likelihood per cell across all viewport observations
    """
    ll = 0.0
    n_obs = 0
    for vp in viewports:
        x, y, w, h = vp["x"], vp["y"], vp["w"], vp["h"]
        obs = vp["class_grid"]  # shape (h, w)
        for vy in range(h):
            for vx in range(w):
                c = obs[vy, vx]
                p = prediction[y + vy, x + vx, c]
                ll += np.log(max(p, eps))
                n_obs += 1
    return float(ll / max(n_obs, 1))


def replay_log_likelihood(prediction, replay, eps=1e-12):
    """Mean log-likelihood per cell over all timesteps of the replay.

    For each timestep, computes the log-likelihood of the observed grid
    under the predicted distribution, then averages over all timesteps
    and all cells.

    Parameters
    ----------
    prediction : array (H, W, 6)
    replay : array (51, H, W) or None

    Returns
    -------
    float or None
    """
    if replay is None:
        return None
    T, H, W = replay.shape
    y_idx, x_idx = np.mgrid[:H, :W]
    total_ll = 0.0
    for t in range(T):
        probs = np.maximum(prediction[y_idx, x_idx, replay[t]], eps)
        total_ll += np.sum(np.log(probs))
    return float(total_ll / (T * H * W))


def evaluate_seed(prediction, ground_truth, viewports=None, replay=None):
    """Evaluate a single seed's prediction.

    Returns dict with: score, target_maxlike, validation_maxlike
    """
    score = score_fun(ground_truth, prediction)
    target_ml = viewport_log_likelihood(prediction, viewports) if viewports else None
    val_ml = replay_log_likelihood(prediction, replay)
    return {
        "score": score,
        "target_maxlike": target_ml,
        "validation_maxlike": val_ml,
    }


# ---------------------------------------------------------------------------
# Time series cross-validation
# ---------------------------------------------------------------------------

def time_series_splits(rounds=None):
    """Generate time-series CV splits.

    Yields (train_rounds, val_round) tuples where:
    - train_rounds: list of round dicts for training (all previous rounds)
    - val_round: single round dict for validation

    The first validation round is the second round (index 1), trained on round 1.
    """
    if rounds is None:
        rounds = discover_rounds()
    for i in range(1, len(rounds)):
        yield rounds[:i], rounds[i]


def run_validation(predict_fn, rounds=None):
    """Run full time-series cross-validation and print results.

    Parameters
    ----------
    predict_fn : callable(train_rounds, val_round, seed_idx) -> prediction (H,W,6)
        The prediction function to evaluate.
    rounds : list of round dicts (default: auto-discover)

    Returns
    -------
    dict with total and per-round metrics
    """
    if rounds is None:
        rounds = discover_rounds()

    all_scores = []
    all_target_ml = []
    all_val_ml = []
    round_results = []

    for train_rounds, val_round in time_series_splits(rounds):
        rnum = val_round["round_number"]
        rid = val_round["round_id"][:8]
        seed_scores = []
        seed_target_ml = []
        seed_val_ml = []

        for seed_idx in range(5):
            gt = load_ground_truth(val_round, seed_idx)
            vps = load_viewports(val_round, seed_idx)
            replay = load_replay(val_round, seed_idx)

            prediction = predict_fn(train_rounds, val_round, seed_idx)

            metrics = evaluate_seed(prediction, gt, vps, replay)
            seed_scores.append(metrics["score"])
            if metrics["target_maxlike"] is not None:
                seed_target_ml.append(metrics["target_maxlike"])
            if metrics["validation_maxlike"] is not None:
                seed_val_ml.append(metrics["validation_maxlike"])

        avg_score = np.mean(seed_scores)
        avg_tml = np.mean(seed_target_ml) if seed_target_ml else 0.0
        avg_vml = np.mean(seed_val_ml) if seed_val_ml else 0.0

        print(f"round #{rnum} ({rid}) score:")
        print(f"  target_maxlike_{rnum}: {avg_tml:.4f}")
        print(f"  validation_score_{rnum}: {avg_score:.4f}")
        print(f"  validation_maxlike_{rnum}: {avg_vml:.4f}")

        round_results.append({
            "round_number": rnum, "round_id": val_round["round_id"],
            "score": avg_score, "target_maxlike": avg_tml,
            "validation_maxlike": avg_vml,
        })
        all_scores.append(avg_score)
        all_target_ml.append(avg_tml)
        all_val_ml.append(avg_vml)

    total_score = np.mean(all_scores) if all_scores else 0.0
    total_tml = np.mean(all_target_ml) if all_target_ml else 0.0
    total_vml = np.mean(all_val_ml) if all_val_ml else 0.0

    print("---")
    print("total_scores:")
    print(f"  target_maxlike: {total_tml:.4f}")
    print(f"  validation_score: {total_score:.4f}")
    print(f"  validation_maxlike: {total_vml:.4f}")

    return {
        "validation_score": total_score,
        "target_maxlike": total_tml,
        "validation_maxlike": total_vml,
        "rounds": round_results,
    }


# ---------------------------------------------------------------------------
# Scoring (original functions)
# ---------------------------------------------------------------------------

def weighted_kl_divergence(
    ground_truth: np.ndarray, prediction: np.ndarray, eps: float = 1e-12
) -> float:
    """Entropy-weighted KL divergence over a grid of per-cell class probabilities.

    Parameters
    ----------
    ground_truth : array, shape (H, W, C)
        True probability distributions per cell.
    prediction : array, shape (H, W, C)
        Predicted probability distributions per cell.
    eps : float
        Small constant to avoid log(0).

    Returns
    -------
    float
        The entropy-weighted mean KL divergence across all cells.
    """
    p = np.asarray(ground_truth, dtype=np.float64)
    q = np.asarray(prediction, dtype=np.float64)

    # Per-cell entropy: -Σ pᵢ log(pᵢ)
    entropy = -np.sum(p * np.log(p + eps), axis=-1)

    # Per-cell KL divergence: Σ pᵢ log(pᵢ / qᵢ)
    kl = np.sum(p * np.log((p + eps) / (q + eps)), axis=-1)

    total_entropy = np.sum(entropy)
    if total_entropy == 0:
        return 0.0

    return float(np.sum(entropy * kl) / total_entropy)


def score_fun(ground_truth: np.ndarray, prediction: np.ndarray) -> float:
    """Compute the competition score (0–100).

    score = max(0, min(100, 100 * exp(-3 * weighted_kl)))

    Parameters
    ----------
    ground_truth : array, shape (H, W, C)
    prediction : array, shape (H, W, C)

    Returns
    -------
    float
        Score between 0 and 100.
    """
    wkl = weighted_kl_divergence(ground_truth, prediction)
    return float(max(0.0, min(100.0, 100.0 * np.exp(-3.0 * wkl))))

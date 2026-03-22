"""Predictor for Astar Island — uses initial states + viewport observations.

Goal: predict H×W×6 probability distributions for each seed, optimizing score_fun.

Training and evaluation scheme:
    - TIME SERIES SPLIT: train on all previous rounds, validate on the next round.
    - Use observations in simulations/ (viewport data) to tune hidden parameters
      for each seed, maximizing likelihood of observed viewport final states.
    - Evaluate validation score and log-likelihood against ground truth / replays.
"""

from prepare import (
    run_validation, load_initial_state, load_viewports,
    viewport_log_likelihood,
    NUM_CLASSES, NSTEPS, RAW_TO_CLASS,
)
import numpy as np
import os


# ---------------------------------------------------------------------------
# Fast RNG (numpy.random is broken in this environment)
# ---------------------------------------------------------------------------

def _rand(H, W):
    buf = os.urandom(H * W * 4)
    return np.frombuffer(buf, dtype=np.uint32).astype(np.float64).reshape(H, W) / 0xFFFFFFFF


def _rand2(H, W):
    buf = os.urandom(H * W * 8)
    arr = np.frombuffer(buf, dtype=np.uint32).astype(np.float64) / 0xFFFFFFFF
    return arr[:H*W].reshape(H, W), arr[H*W:].reshape(H, W)


# ---------------------------------------------------------------------------
# Default parameters (from simulate.py experiments)
# ---------------------------------------------------------------------------

DEFAULT_PARAMS = dict(
    collapse=0.055, port_collapse=0.025,
    expand_base=0.003, expand_per_n=0.005,
    port_per_ocean=0.03,
    empty_to_ruin=0.0004, forest_to_ruin=0.0005,
    ruin_rebuild=0.48, ruin_to_empty=0.33, ruin_to_forest=0.18,
    ruin_port_per_ocean=0.05,
    forest_base=0.004, forest_per_n=0.005,
)


# ---------------------------------------------------------------------------
# Stochastic simulation (taken from simulate.py)
# ---------------------------------------------------------------------------

class State:
    def __init__(self, initial_state, ocean_mask, n_ocean, params):
        self.state = initial_state.copy()
        self.H, self.W = self.state.shape
        self.ocean_mask = ocean_mask
        self.static_mask = ocean_mask | (initial_state == 5)
        self.n_ocean = n_ocean
        self.p = params

    def _count_neighbors(self, mask):
        padded = np.pad(mask.astype(np.float64), 1, mode='constant', constant_values=0)
        H, W = self.H, self.W
        counts = np.zeros((H, W), dtype=np.float64)
        for dy in range(3):
            for dx in range(3):
                if dy == 1 and dx == 1:
                    continue
                counts += padded[dy:dy+H, dx:dx+W]
        return counts

    def evolve(self):
        new = self.state.copy()
        rand, rand2 = _rand2(self.H, self.W)
        p = self.p
        n_alive = self._count_neighbors((self.state == 1) | (self.state == 2))
        n_ocean = self.n_ocean

        # Settlement -> Ruin
        is_s = (self.state == 1)
        new[is_s & (rand < p['collapse'])] = 3
        collapsed = (new == 3) & is_s

        # Settlement -> Port (ocean-adjacent, not collapsed)
        can_port = is_s & (n_ocean > 0) & ~collapsed
        p_port = np.minimum(p['port_per_ocean'] * n_ocean, 1.0)
        new[can_port & (rand < p_port)] = 2

        # Port -> Ruin
        is_p = (self.state == 2)
        new[is_p & (rand < p['port_collapse'])] = 3

        # Plains -> Settlement
        is_land = (self.state == 0) & ~self.ocean_mask
        p_exp = np.minimum(p['expand_base'] + p['expand_per_n'] * n_alive, 1.0)
        expanded = is_land & (rand < p_exp)
        new[expanded] = 1

        # Plains -> Ruin (rare)
        new[is_land & ~expanded & (rand < p_exp + p['empty_to_ruin'])] = 3

        # Ruin transitions (categorical)
        is_r = (self.state == 3)
        rp = np.minimum(p['ruin_port_per_ocean'] * n_ocean, 0.5)
        rem = 1.0 - rp
        ps = p['ruin_rebuild'] * rem
        pe = p['ruin_to_empty'] * rem

        to_port = is_r & (rand2 < rp)
        new[to_port] = 2
        to_settl = is_r & ~to_port & (rand2 < rp + ps)
        new[to_settl] = 1
        to_empty = is_r & ~to_port & ~to_settl & (rand2 < rp + ps + pe)
        new[to_empty] = 0
        to_forest = is_r & ~to_port & ~to_settl & ~to_empty
        new[to_forest] = 4

        # Forest -> Settlement
        is_f = (self.state == 4)
        p_fc = np.minimum(p['forest_base'] + p['forest_per_n'] * n_alive, 1.0)
        cleared = is_f & (rand < p_fc)
        new[cleared] = 1

        # Forest -> Ruin (rare)
        new[is_f & ~cleared & (rand < p_fc + p['forest_to_ruin'])] = 3

        # Static cells never change
        new[self.static_mask] = self.state[self.static_mask]
        self.state = new

    def simulate(self):
        for _ in range(NSTEPS):
            self.evolve()


def run_simulations(class_grid, ocean_mask, n_ocean, params, n_sims):
    """Run n_sims Monte Carlo simulations and return (H,W,6) probability tensor."""
    H, W = class_grid.shape
    alpha = 0.015
    counts = np.zeros((H, W, NUM_CLASSES), dtype=np.float64)
    for _ in range(n_sims):
        game = State(class_grid, ocean_mask, n_ocean, params)
        game.simulate()
        for c in range(NUM_CLASSES):
            counts[:, :, c] += (game.state == c)
    return (counts + alpha) / (n_sims + alpha * NUM_CLASSES)


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

N_SIMS = 500
N_SEARCH_SIMS = 30


def estimate_params_for_round(val_round):
    """Estimate simulation parameters once per round using all seeds' viewports.

    Grid-search over collapse and expansion, pick params that maximize
    total viewport log-likelihood across all seeds.
    """
    # Gather viewports and initial states for all seeds
    seeds_data = []
    all_viewports = []
    for idx in range(5):
        raw, ocean_mask, class_grid = load_initial_state(val_round, idx)
        vps = load_viewports(val_round, idx)
        _tmp = State(class_grid, ocean_mask, None, DEFAULT_PARAMS)
        n_ocean = _tmp._count_neighbors(ocean_mask)
        seeds_data.append((class_grid, ocean_mask, n_ocean))
        all_viewports.append(vps)

    has_viewports = any(len(v) > 0 for v in all_viewports)
    if not has_viewports:
        return DEFAULT_PARAMS.copy()

    collapse_vals = [0.03, 0.05, 0.07, 0.10, 0.14, 0.20]
    expand_scales = [0.5, 1.0, 1.5, 2.0]

    def _eval_params(params):
        """Average viewport LL across all seeds."""
        total_ll = 0.0
        n = 0
        for idx in range(5):
            if not all_viewports[idx]:
                continue
            cg, om, no = seeds_data[idx]
            pred = run_simulations(cg, om, no, params, N_SEARCH_SIMS)
            total_ll += viewport_log_likelihood(pred, all_viewports[idx])
            n += 1
        return total_ll / max(n, 1)

    # Phase 1: search collapse × expansion
    best_ll = -np.inf
    best_params = DEFAULT_PARAMS.copy()

    for collapse in collapse_vals:
        for exp_scale in expand_scales:
            params = DEFAULT_PARAMS.copy()
            params['collapse'] = collapse
            params['port_collapse'] = collapse * 0.45
            params['expand_base'] = DEFAULT_PARAMS['expand_base'] * exp_scale
            params['expand_per_n'] = DEFAULT_PARAMS['expand_per_n'] * exp_scale
            params['forest_base'] = DEFAULT_PARAMS['forest_base'] * exp_scale
            params['forest_per_n'] = DEFAULT_PARAMS['forest_per_n'] * exp_scale

            ll = _eval_params(params)
            if ll > best_ll:
                best_ll = ll
                best_params = params.copy()

    # Phase 2: refine ruin rebuild rate around best params
    for ruin_rebuild in [0.35, 0.42, 0.48, 0.55]:
        params = best_params.copy()
        params['ruin_rebuild'] = ruin_rebuild
        params['ruin_to_empty'] = (1.0 - ruin_rebuild) * 0.65
        params['ruin_to_forest'] = (1.0 - ruin_rebuild) * 0.35
        ll = _eval_params(params)
        if ll > best_ll:
            best_ll = ll
            best_params = params.copy()

    return best_params


# Cache calibrated params per round
_round_params_cache = {}


def predict(train_rounds, val_round, seed_idx):
    """Predict H×W×6 probability tensor for one seed."""
    rid = val_round["round_id"]

    # Calibrate once per round, reuse for all seeds
    if rid not in _round_params_cache:
        _round_params_cache[rid] = estimate_params_for_round(val_round)
    params = _round_params_cache[rid]

    raw, ocean_mask, class_grid = load_initial_state(val_round, seed_idx)
    _tmp = State(class_grid, ocean_mask, None, DEFAULT_PARAMS)
    n_ocean = _tmp._count_neighbors(ocean_mask)

    return run_simulations(class_grid, ocean_mask, n_ocean, params, N_SIMS)


if __name__ == "__main__":
    _round_params_cache.clear()
    results = run_validation(predict)

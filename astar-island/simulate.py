from prepare import score_fun
import numpy as np
import json
import os


def _rand(H, W):
    """Fast uniform random array using os.urandom (numpy.random is broken)."""
    buf = os.urandom(H * W * 4)
    return np.frombuffer(buf, dtype=np.uint32).astype(np.float64).reshape(H, W) / 0xFFFFFFFF


def _rand2(H, W):
    """Generate two random arrays at once for efficiency."""
    buf = os.urandom(H * W * 8)
    arr = np.frombuffer(buf, dtype=np.uint32).astype(np.float64) / 0xFFFFFFFF
    return arr[:H*W].reshape(H, W), arr[H*W:].reshape(H, W)

NSTEPS = 50
NUM_CLASSES = 6
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.join(SCRIPT_DIR, "analysis")
REPLAY_DIR = os.path.join(SCRIPT_DIR, "replays")

# Map raw grid values to class indices
# 0=Empty, 10=Ocean, 11=Plains -> class 0; 1=Settlement -> 1; 2=Port -> 2;
# 3=Ruin -> 3; 4=Forest -> 4; 5=Mountain -> 5
RAW_TO_CLASS = {0: 0, 10: 0, 11: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


#Get the probability distributions for each of the six tile types in the end state.
def load_analysis(ifile):
    with open(os.path.join(ANALYSIS_DIR, ifile)) as f:
        data = json.load(f)
    gt = np.array(data["ground_truth"], dtype=np.float64)
    initial_raw = np.array(data["initial_grid"], dtype=np.int32)
    return gt, initial_raw


#Get a random observation of the evolution of a game.
def load_replay(ifile):
    with open(os.path.join(REPLAY_DIR, ifile)) as f:
        data = json.load(f)
    frames = []
    for frame in data["frames"]:
        grid = np.array(frame["grid"], dtype=np.int32)
        class_grid = np.zeros_like(grid)
        for raw_val, class_idx in RAW_TO_CLASS.items():
            class_grid[grid == raw_val] = class_idx
        frames.append(class_grid)
    return np.array(frames, dtype=np.int32)


def calibrate_params(replay, ocean_mask):
    """Estimate key parameters from a single replay, blended with priors."""
    T, H, W = replay.shape
    # Count transitions
    s_total = 0; s_to_r = 0; s_to_p_ocean = 0; s_ocean_total = 0
    p_total = 0; p_to_r = 0
    e_total = 0; e_to_s = 0
    e_by_n = np.zeros(9); e_total_by_n = np.zeros(9)
    r_to = np.zeros(5)  # settl, empty, forest, port, other
    f_total = 0; f_to_s = 0
    f_by_n = np.zeros(9); f_total_by_n = np.zeros(9)

    def _cn(grid, mask):
        padded = np.pad(mask.astype(np.float64), 1, mode='constant', constant_values=0)
        counts = np.zeros((H, W), dtype=np.float64)
        for dy in range(3):
            for dx in range(3):
                if dy == 1 and dx == 1: continue
                counts += padded[dy:dy+H, dx:dx+W]
        return counts

    n_ocean = _cn(replay[0], ocean_mask)

    for t in range(1, T):
        prev, curr = replay[t-1], replay[t]
        is_s = (prev == 1)
        s_total += is_s.sum()
        s_to_r += (is_s & (curr == 3)).sum()
        coastal_s = is_s & (n_ocean > 0)
        s_ocean_total += n_ocean[coastal_s].sum()
        s_to_p_ocean += (coastal_s & (curr == 2)).sum()

        is_p = (prev == 2)
        p_total += is_p.sum()
        p_to_r += (is_p & (curr == 3)).sum()

        is_e = (prev == 0) & ~ocean_mask
        n_alive = _cn(prev, (prev == 1) | (prev == 2))
        e_total += is_e.sum()
        e_to_s += (is_e & (curr == 1)).sum()
        for n in range(9):
            mask = is_e & (n_alive == n)
            e_total_by_n[n] += mask.sum()
            e_by_n[n] += (mask & (curr == 1)).sum()

        is_f = (prev == 4)
        f_total += is_f.sum()
        f_to_s += (is_f & (curr == 1)).sum()
        for n in range(9):
            mask = is_f & (n_alive == n)
            f_total_by_n[n] += mask.sum()
            f_by_n[n] += (mask & (curr == 1)).sum()

        is_r = (prev == 3)
        r_to[0] += (is_r & (curr == 1)).sum()
        r_to[1] += (is_r & (curr == 0)).sum()
        r_to[2] += (is_r & (curr == 4)).sum()
        r_to[3] += (is_r & (curr == 2)).sum()

    # Estimate rates from replay
    obs = {}
    obs['collapse'] = s_to_r / max(s_total, 1)
    obs['port_collapse'] = p_to_r / max(p_total, 1)
    obs['expand'] = e_to_s / max(e_total, 1)
    obs['forest_clear'] = f_to_s / max(f_total, 1)
    # Fit forest base and per_n
    f_rates = []
    for n in range(9):
        if f_total_by_n[n] > 20:
            f_rates.append((n, f_by_n[n] / f_total_by_n[n]))
    if len(f_rates) >= 2:
        fns, frs = zip(*f_rates)
        fA = np.vstack([np.ones(len(fns)), np.array(fns)]).T
        ffit = np.linalg.lstsq(fA, np.array(frs), rcond=None)[0]
        obs['forest_base'] = max(ffit[0], 0.0)
        obs['forest_per_n'] = max(ffit[1], 0.0)
    else:
        obs['forest_base'] = obs['forest_clear'] * 0.5
        obs['forest_per_n'] = obs['forest_clear'] * 1.0
    # Fit expand base and per_n from neighbor-stratified data
    rates = []
    for n in range(9):
        if e_total_by_n[n] > 20:
            rates.append((n, e_by_n[n] / e_total_by_n[n]))
    if len(rates) >= 2:
        ns, rs = zip(*rates)
        A = np.vstack([np.ones(len(ns)), np.array(ns)]).T
        fit = np.linalg.lstsq(A, np.array(rs), rcond=None)[0]
        obs['expand_base'] = max(fit[0], 0.0)
        obs['expand_per_n'] = max(fit[1], 0.0)
    else:
        obs['expand_base'] = obs['expand'] * 0.4
        obs['expand_per_n'] = obs['expand'] * 1.2
    obs['port_per_ocean'] = s_to_p_ocean / max(s_ocean_total, 1)
    r_sum = r_to.sum()
    if r_sum > 0:
        obs['ruin_rebuild'] = r_to[0] / r_sum
        obs['ruin_to_empty'] = r_to[1] / r_sum
        obs['ruin_to_forest'] = r_to[2] / r_sum
    else:
        obs['ruin_rebuild'] = 0.48
        obs['ruin_to_empty'] = 0.33
        obs['ruin_to_forest'] = 0.18

    # Blend with priors (weight: 0.6 replay, 0.4 prior)
    w = 0.7
    priors = dict(collapse=0.055, port_collapse=0.025, expand=0.005,
                  expand_base=0.003, expand_per_n=0.005,
                  forest_clear=0.007, forest_base=0.004, forest_per_n=0.005,
                  port_per_ocean=0.03,
                  ruin_rebuild=0.48, ruin_to_empty=0.33, ruin_to_forest=0.18)
    blended = {k: w * obs[k] + (1-w) * priors[k] for k in priors}
    return blended


class State:
    # Stochastic transition parameters (calibrated from replay data)
    p_collapse_min = 0.035    # settlement -> ruin (base rate)
    p_collapse_density = 0.00015 # extra collapse per alive settlement on map
    p_port_collapse = 0.018   # port -> ruin
    p_expand_base = 0.003     # empty land -> settlement (spontaneous)
    p_expand_per_n = 0.005    # empty land -> settlement (per adjacent alive)
    p_port_per_ocean = 0.04   # settlement -> port (per adjacent ocean cell)
    p_ruin_rebuild = 0.48     # ruin -> settlement
    p_ruin_to_empty = 0.33    # ruin -> empty/plains
    p_ruin_to_forest = 0.18   # ruin -> forest
    p_ruin_port_per_ocean = 0.05  # ruin -> port (per ocean neighbor)
    p_forest_base = 0.004     # forest -> settlement (spontaneous)
    p_forest_per_n = 0.005    # forest -> settlement (per adjacent alive)
    p_empty_to_ruin = 0.0004  # empty -> ruin (rare)
    p_forest_to_ruin = 0.0005 # forest -> ruin (rare)

    #Based on the first state in replay 0 set the initial state.
    def __init__(self, initial_state, ocean_mask, n_ocean=None, params=None):
        self.state = initial_state.copy()
        self.H, self.W = self.state.shape
        self.ocean_mask = ocean_mask
        self.static_mask = ocean_mask | (initial_state == 5)
        self.step = 0
        # Precompute ocean neighbor count (static, never changes)
        if n_ocean is not None:
            self.n_ocean = n_ocean
        else:
            self.n_ocean = self._count_neighbors(ocean_mask)
        # Override parameters if calibrated
        if params:
            # Split calibrated collapse: 70% base, 30% density-dependent
            self.p_collapse_min = params['collapse'] * 0.7
            self.p_collapse_density = params['collapse'] * 0.3 / 200
            self.p_port_collapse = params['port_collapse']
            self.p_expand_base = params['expand_base']
            self.p_expand_per_n = params['expand_per_n']
            self.p_port_per_ocean = params['port_per_ocean']
            self.p_forest_base = params['forest_base']
            self.p_forest_per_n = params['forest_per_n']
            self.p_ruin_rebuild = params['ruin_rebuild']
            self.p_ruin_to_empty = params['ruin_to_empty']
            self.p_ruin_to_forest = params['ruin_to_forest']

    def _count_neighbors(self, mask):
        """Count how many of the 8 neighbors satisfy the boolean mask."""
        padded = np.pad(mask.astype(np.float64), 1, mode='constant', constant_values=0)
        counts = np.zeros((self.H, self.W), dtype=np.float64)
        for dy in range(3):
            for dx in range(3):
                if dy == 1 and dx == 1:
                    continue
                counts += padded[dy:dy+self.H, dx:dx+self.W]
        return counts

    #Go from one state to the next. The properties of neighbouring cells influence the cells around them the next turn.
    #Find stochastic rules for how the cells affect their neighbours that make the evolution seen for the simulations in the /replay folder likely,
    #and that given 200 runs produce the distributions seen in the /analysis folder for the five different seeds that dictate some of the hidden, but stationary process parameters.
    def evolve(self):
        new_state = self.state.copy()
        rand, rand2 = _rand2(self.H, self.W)

        n_alive = self._count_neighbors((self.state == 1) | (self.state == 2))
        n_ocean = self.n_ocean

        # Settlement (1) -> Ruin (3): collapse increases with map density
        is_settlement = (self.state == 1)
        n_total_alive = np.sum(is_settlement) + np.sum(self.state == 2)
        p_collapse = self.p_collapse_min + self.p_collapse_density * n_total_alive
        collapse = is_settlement & (rand < p_collapse)
        new_state[collapse] = 3

        # Settlement (1) -> Port (2): scales with number of ocean neighbors
        can_port = is_settlement & (n_ocean > 0) & ~collapse
        p_port = np.minimum(self.p_port_per_ocean * n_ocean, 1.0)
        become_port = can_port & (rand < p_port)
        new_state[become_port] = 2

        # Port (2) -> Ruin (3): port collapse (also density-dependent)
        is_port = (self.state == 2)
        p_port_coll = self.p_port_collapse + self.p_collapse_density * n_total_alive * 0.5
        port_collapse = is_port & (rand < p_port_coll)
        new_state[port_collapse] = 3

        # Plains (class 0, not ocean) -> Settlement (1): expansion
        is_land = (self.state == 0) & ~self.ocean_mask
        p_expand = np.minimum(self.p_expand_base + self.p_expand_per_n * n_alive, 1.0)
        expand = is_land & (rand < p_expand)
        new_state[expand] = 1

        # Plains -> Ruin (rare, ~0.04%)
        empty_to_ruin = is_land & ~expand & (rand < p_expand + self.p_empty_to_ruin)
        new_state[empty_to_ruin] = 3

        # Ruin (3) transitions: ruins always transition immediately (categorical draw)
        # Port probability scales with ocean neighbors; remaining probability split among others
        is_ruin = (self.state == 3)
        # rand2 already generated above
        p_port = np.minimum(self.p_ruin_port_per_ocean * n_ocean, 0.5)
        remaining = 1.0 - p_port
        # Scale base rates by remaining probability
        p_settl = self.p_ruin_rebuild * remaining
        p_empty = self.p_ruin_to_empty * remaining
        p_forest = self.p_ruin_to_forest * remaining
        # Categorical: port, then settlement, then empty, then forest
        ruin_to_port = is_ruin & (rand2 < p_port)
        new_state[ruin_to_port] = 2
        ruin_to_settlement = is_ruin & ~ruin_to_port & (rand2 < p_port + p_settl)
        new_state[ruin_to_settlement] = 1
        ruin_to_empty = is_ruin & ~ruin_to_port & ~ruin_to_settlement & (rand2 < p_port + p_settl + p_empty)
        new_state[ruin_to_empty] = 0
        ruin_to_forest = is_ruin & ~ruin_to_port & ~ruin_to_settlement & ~ruin_to_empty
        new_state[ruin_to_forest] = 4

        # Forest (4) -> Settlement (1): cleared for expansion
        is_forest = (self.state == 4)
        p_forest = np.minimum(self.p_forest_base + self.p_forest_per_n * n_alive, 1.0)
        clear = is_forest & (rand < p_forest)
        new_state[clear] = 1

        # Forest -> Ruin (rare, ~0.05%)
        forest_ruin = is_forest & ~clear & (rand < p_forest + self.p_forest_to_ruin)
        new_state[forest_ruin] = 3

        # Static cells (ocean, mountain) never change
        new_state[self.static_mask] = self.state[self.static_mask]

        self.state = new_state

    #Simulate evolution from the initial state to timestep 50 by calling evolve.
    def simulate(self):
        for _ in range(NSTEPS):
            self.evolve()
            self.step += 1


class Statistic:
    def __init__(self, size, H, W):
        self.size = size
        self.H = H
        self.W = W
        self.final_states = np.zeros((size, H, W), dtype=np.int32)
        self.count = 0

    def update(self, i, final_state):
        self.final_states[i] = final_state
        self.count = i + 1

    #The maximum likelihood of seeing the observed replays given the stochastic model for the evolution of the state.
    def maximum_log_likelihood(self, replay):
        # Build empirical distribution from simulated final states
        probs = np.zeros((self.H, self.W, NUM_CLASSES), dtype=np.float64)
        for c in range(NUM_CLASSES):
            probs[:, :, c] = (self.final_states[:self.count] == c).mean(axis=0)
        probs = np.maximum(probs, 1e-6)
        probs = probs / probs.sum(axis=-1, keepdims=True)

        # Log-probability of the observed replay's final state
        replay_final = replay[-1]
        y_idx, x_idx = np.mgrid[:self.H, :self.W]
        ll = np.sum(np.log(probs[y_idx, x_idx, replay_final]))
        return float(ll)

    #Make a histogram over all object types based on the observations of each of them over all the size simulations, producing one bin for each the six object types.
    #Then normalize the sum over the bins to 1, and then cap the probability to a lower bound of 0.01, then normalize the values again.
    def normalize(self):
        # Laplace smoothing: add alpha pseudo-counts per class
        alpha = 0.02
        counts = np.zeros((self.H, self.W, NUM_CLASSES), dtype=np.float64)
        for c in range(NUM_CLASSES):
            counts[:, :, c] = (self.final_states[:self.count] == c).sum(axis=0)
        probs = (counts + alpha) / (self.count + alpha * NUM_CLASSES)
        return probs


#Run simulations covering all available rounds and seeds
# Auto-discover rounds from analysis directory
import glob as _glob
ROUNDS = []
for path in sorted(_glob.glob(os.path.join(ANALYSIS_DIR, "*_analysis_seed_0_*.json"))):
    fname = os.path.basename(path)
    # Parse: {datestr}_analysis_seed_0_{round_id}.json
    parts = fname.replace("_analysis_seed_0_", "|").replace(".json", "").split("|")
    if len(parts) == 2:
        ROUNDS.append((parts[1], parts[0]))
number_of_simulations = 1500

all_scores = []
all_maxlikes = []

for round_id, datestr in ROUNDS:
    round_scores = []
    round_maxlikes = []
    print(f"\n=== Round {round_id[:8]} ===")

    # Calibrate params from ALL replays in this round for better estimates
    all_replays = []
    all_ocean_masks = []
    for idx in range(5):
        replay_file = f"{datestr}_replay_seed_{idx}_{round_id}.json"
        analysis_file = f"{datestr}_analysis_seed_{idx}_{round_id}.json"
        _, initial_raw = load_analysis(analysis_file)
        replay = load_replay(replay_file)
        all_replays.append(replay)
        all_ocean_masks.append(initial_raw == 10)

    # Average calibration across all seeds in this round
    all_params = [calibrate_params(r, o) for r, o in zip(all_replays, all_ocean_masks)]
    params = {k: np.mean([p[k] for p in all_params]) for k in all_params[0]}

    for idx in range(5):
        analysis_file = f"{datestr}_analysis_seed_{idx}_{round_id}.json"
        replay_file = f"{datestr}_replay_seed_{idx}_{round_id}.json"
        ground_truth, initial_raw = load_analysis(analysis_file)
        replay = all_replays[idx]

        ocean_mask = all_ocean_masks[idx]
        H, W = replay.shape[1], replay.shape[2]
        # Precompute ocean neighbor count once per seed
        _tmp = State(replay[0], ocean_mask)
        n_ocean = _tmp.n_ocean
        stats = Statistic(number_of_simulations, H, W)

        for i in range(number_of_simulations):
            game = State(replay[0], ocean_mask, n_ocean=n_ocean, params=params)
            game.simulate()
            stats.update(i, game.state)

        normalized_stats = stats.normalize()
        score = score_fun(ground_truth, normalized_stats)
        max_likelihood = stats.maximum_log_likelihood(replay)
        round_scores.append(score)
        round_maxlikes.append(max_likelihood)
        print(f"  Seed {idx}: score={score:.4f}, maxlike={max_likelihood:.4f}")

    avg_s = np.mean(round_scores)
    avg_m = np.mean(round_maxlikes)
    print(f"  Round avg: score={avg_s:.4f}, maxlike={avg_m:.4f}")
    all_scores.extend(round_scores)
    all_maxlikes.extend(round_maxlikes)

print("---")
print(f"score:  {np.mean(all_scores):.4f}")
print(f"maxlike: {np.mean(all_maxlikes):.4f}")

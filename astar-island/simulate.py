from prepare import score_fun
import numpy as np
import json
import os

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


class State:
    # Stochastic transition parameters
    p_collapse = 0.08         # settlement -> ruin (winter/raids)
    p_port_collapse = 0.06    # port -> ruin
    p_expand = 0.03           # empty land -> settlement (per adjacent alive settlement)
    p_port_form = 0.05        # settlement -> port (if adjacent to ocean)
    p_ruin_rebuild = 0.04     # ruin -> settlement (per adjacent alive settlement)
    p_ruin_to_forest = 0.05   # ruin -> forest (environment reclaims)
    p_forest_clear = 0.01     # forest -> settlement (per adjacent alive settlement)

    #Based on the first state in replay 0 set the initial state.
    def __init__(self, initial_state, ocean_mask):
        self.state = initial_state.copy()
        self.H, self.W = self.state.shape
        self.ocean_mask = ocean_mask
        self.static_mask = ocean_mask | (initial_state == 5)

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
        rand = np.random.random((self.H, self.W))

        n_alive = self._count_neighbors((self.state == 1) | (self.state == 2))
        has_ocean_neighbor = self._count_neighbors(self.ocean_mask) > 0

        # Settlement (1) -> Ruin (3): collapse from winter/raids
        is_settlement = (self.state == 1)
        collapse = is_settlement & (rand < self.p_collapse)
        new_state[collapse] = 3

        # Settlement (1) -> Port (2): develop port if adjacent to ocean
        can_port = is_settlement & has_ocean_neighbor & ~collapse
        become_port = can_port & (rand < self.p_port_form)
        new_state[become_port] = 2

        # Port (2) -> Ruin (3): port collapse
        is_port = (self.state == 2)
        port_collapse = is_port & (rand < self.p_port_collapse)
        new_state[port_collapse] = 3

        # Plains (class 0, not ocean) -> Settlement (1): expansion from nearby settlements
        is_land = (self.state == 0) & ~self.ocean_mask
        expand = is_land & (rand < np.minimum(self.p_expand * n_alive, 1.0))
        new_state[expand] = 1

        # Ruin (3) -> Settlement (1): rebuild by nearby settlements
        is_ruin = (self.state == 3)
        rebuild = is_ruin & (rand < np.minimum(self.p_ruin_rebuild * n_alive, 1.0))
        new_state[rebuild] = 1

        # Ruin (3) -> Forest (4): environment reclaims abandoned land
        reforest = is_ruin & ~rebuild & (rand < self.p_ruin_to_forest)
        new_state[reforest] = 4

        # Forest (4) -> Settlement (1): cleared for expansion
        is_forest = (self.state == 4)
        clear = is_forest & (rand < np.minimum(self.p_forest_clear * n_alive, 1.0))
        new_state[clear] = 1

        # Static cells (ocean, mountain) never change
        new_state[self.static_mask] = self.state[self.static_mask]

        self.state = new_state

    #Simulate evolution from the initial state to timestep 50 by calling evolve, and record the states at every timestep.
    def simulate(self):
        nsteps = NSTEPS
        game_states = np.zeros((nsteps + 1, self.H, self.W), dtype=np.int32)
        game_states[0] = self.state
        for i in range(nsteps):
            self.evolve()
            game_states[i + 1] = self.state
        return game_states


class Statistic:
    def __init__(self, size, H, W):
        self.size = size
        self.H = H
        self.W = W
        self.final_states = np.zeros((size, H, W), dtype=np.int32)
        self.count = 0

    def update(self, i, game_states):
        self.final_states[i] = game_states[-1]
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
        probs = np.zeros((self.H, self.W, NUM_CLASSES), dtype=np.float64)
        for c in range(NUM_CLASSES):
            probs[:, :, c] = (self.final_states[:self.count] == c).mean(axis=0)
        probs = np.maximum(probs, 0.01)
        probs = probs / probs.sum(axis=-1, keepdims=True)
        return probs


#Run simulations covering all seeds
ROUND_ID = "71451d74-be9f-471f-aacd-a41f3b68a9cd"
datestr = "03_19_22"
number_of_simulations = 200

scores = []
maxlikes = []

for idx in range(5):
    analysis_file = f"{datestr}_analysis_seed_{idx}_{ROUND_ID}.json"
    replay_file = f"{datestr}_replay_seed_{idx}_{ROUND_ID}.json"
    ground_truth, initial_raw = load_analysis(analysis_file)
    replay = load_replay(replay_file)

    ocean_mask = (initial_raw == 10)
    H, W = replay.shape[1], replay.shape[2]
    stats = Statistic(number_of_simulations, H, W)

    for i in range(number_of_simulations):
        game = State(replay[0], ocean_mask)
        game_states = game.simulate()
        stats.update(i, game_states)

    normalized_stats = stats.normalize()
    score = score_fun(ground_truth, normalized_stats)
    max_likelihood = stats.maximum_log_likelihood(replay)
    scores.append(score)
    maxlikes.append(max_likelihood)
    print(f"Seed {idx}: score={score:.4f}, maxlike={max_likelihood:.4f}")

avg_score = np.mean(scores)
avg_maxlike = np.mean(maxlikes)
print("---")
print(f"score:  {avg_score:.4f}")
print(f"maxlike: {avg_maxlike:.4f}")

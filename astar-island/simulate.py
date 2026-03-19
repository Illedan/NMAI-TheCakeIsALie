from prepare import score_fun
import numpy as np


NSTEPS = 50
#Get the probability distributions for each of the six tile types in the end state.
def load_analysis(ifile):

#Get a random observaion of the evolution of a game.
def load_replay(ifile):

def class State():
    #Based on the first state in replay 0 set the initial state.
    def __init__(self, initial_state):
        self.state = initial_state
    #Go from one state to the next. The properties of neighbouring cells influence the cells around them the next turn.
    #Find stochastic rules for how the cells affect their neigbours that make the evolution seen for the simulations in the /replay folder likely,
    #and that gien 200 runs produce the distributions seen in the/analysis folder for the five different seeds that dictate some of the hidden, but stationary process parameters.
    def evolve(self):

    #Simulate evoltion from the initial state to timestep 50 by calling evolve, and record the states at every timestep.
    def simulate(self):
        nsteps = NSTEPS
        game_states = np.array(tuple([nsteps].append(list(state.shape))))
        game_states[0] = self.state
        for i in range(nsteps):
            self.evolve()
            game_states[i+1] = self.state
        return game_states

def class Statistic():
    def __init__(self, size, replay_shape):
        self.game_states = np.array(tuple([size].append(list(replay_shape))))

    def update(self, i, game_states):
        self.game_states[i] = game_states

    #The maximum likelihood of seeing the observed replays given the stochastic model for the evolution of the state.
    def maximum_log_likelihiood(self, replay):

    #Make a histogram over all object types based on the observations of each of them over all the size simulations, producing one bin for each the six object types.
    #Then normalize the sum over the bins to 1, and then cap the probability to a lower bound of 0.01, then normalize the values again.
    def normalize(self):



#Run simulations covering all states
ROUND_ID = "71451d74-be9f-471f-aacd-a41f3b68a9cd"
datestr = "03_19_22"
for idx in range(5):
    analysis_file = f"{datestr}_analysis_seed_{idx}_{ROUND_ID}.json"
    replay_file = f"{datestr}_replay_seed_{idx}_{ROUND_ID}.json"
    analysis = load_analysis(analysis_file)
    replay = load_replay(load_replay)
    stats = Statistic()
    number_of_simulations = 1000
    for i in range(1000):
        game = State(replay[0])
        game_states = game.simulate()
        stats.update(i, game_states)
    normalized_stats = stats.normalize()
    score = score_fun(analysis, normalized_stats)
    max_likelihood = stats.maximum_log_likelihiood(replay)

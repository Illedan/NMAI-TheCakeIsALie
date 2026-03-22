"""Tunable parameters for the agent-based simulator.

Defaults are calibrated from replay data (19,607 settlement observations
across 12 rounds, 3,480 frame-by-frame transitions).
"""

from dataclasses import dataclass, field, fields
import numpy as np


@dataclass
class AgentParams:
    # --- Growth phase ---
    pop_growth_rate: float = 0.08       # base population growth per step
    pop_food_factor: float = 1.0        # growth multiplied by food level
    food_mean_revert_target: float = 0.7  # food reverts toward this (observed mean ~0.69)
    food_mean_revert_rate: float = 0.3  # speed of food mean reversion
    food_pop_drain: float = 0.04        # food consumed per unit pop per step
    defense_growth_rate: float = 0.05   # defense grows toward pop-dependent cap
    defense_pop_scale: float = 0.4      # defense cap = min(1, pop * scale)
    wealth_growth_rate: float = 0.002   # passive wealth accumulation
    wealth_pop_factor: float = 0.005    # wealth growth scales with pop

    # --- Conflict phase ---
    raid_range: float = 3.0             # max distance for raiding
    raid_prob_base: float = 0.15        # base probability of raiding per step
    raid_defense_weight: float = 2.0    # higher defender defense -> lower raid prob
    raid_desperation: float = 0.5       # low food increases raid probability
    raid_pop_damage: float = 0.3        # fraction of pop lost by defender on raid
    raid_loot_frac: float = 0.2        # fraction of defender's food/wealth looted
    raid_conquest_prob: float = 0.3     # probability of ownership change on successful raid

    # --- Trade phase ---
    trade_range: float = 4.0           # max distance for trade between ports
    trade_food_gain: float = 0.05      # food gained per trade connection
    trade_wealth_gain: float = 0.01    # wealth gained per trade connection

    # --- Winter phase ---
    winter_food_loss: float = 0.05     # flat food loss per step
    collapse_food_threshold: float = 0.05  # food below this -> collapse risk
    collapse_prob_starve: float = 0.1  # probability of pop collapse from starvation
    collapse_pop_loss: float = 0.5     # fraction of pop lost on collapse
    collapse_defense_loss: float = 0.3 # defense lost on collapse

    # --- Expansion phase ---
    expand_pop_threshold: float = 1.5  # pop above this can spawn new settlement
    expand_prob_base: float = 0.03     # base probability of expansion per step
    expand_pop_factor: float = 0.02    # additional prob per pop above threshold
    expand_radius: float = 3.0        # max distance for new settlement placement
    new_settlement_pop: float = 0.45   # initial pop of new settlement (observed)
    new_settlement_food: float = 0.5   # initial food of new settlement
    new_settlement_defense: float = 0.1  # initial defense of new settlement

    # --- Environment phase ---
    ruin_rebuild_prob: float = 0.02    # probability ruin -> settlement per step
    ruin_to_empty_prob: float = 0.03   # probability ruin -> empty
    ruin_to_forest_prob: float = 0.01  # probability ruin -> forest
    port_conversion_prob: float = 0.01 # probability coastal settlement -> port
    spontaneous_settle_prob: float = 0.005  # empty/plains -> settlement (near existing)
    spontaneous_settle_range: float = 3.0   # range for spontaneous settlement
    forest_settle_prob: float = 0.003  # forest -> settlement probability

    # --- Initial stat distributions (for unknown stats) ---
    init_pop_mean: float = 1.1         # observed mean
    init_pop_std: float = 0.76         # observed std
    init_food_mean: float = 0.69       # observed mean
    init_food_std: float = 0.27        # observed std
    init_defense_mean: float = 0.46    # observed mean
    init_defense_std: float = 0.31     # observed std
    init_wealth_mean: float = 0.01     # observed mean
    init_wealth_std: float = 0.03      # observed std

    # --- Simulation ---
    num_steps: int = 50
    num_monte_carlo: int = 500

    def to_array(self) -> np.ndarray:
        """Convert float params to array for optimization."""
        return np.array([getattr(self, f.name) for f in fields(self)
                        if f.type is float])

    def from_array(self, arr: np.ndarray) -> 'AgentParams':
        """Set float params from array."""
        float_fields = [f for f in fields(self) if f.type is float]
        for i, f in enumerate(float_fields):
            setattr(self, f.name, float(arr[i]))
        return self

    @staticmethod
    def float_field_names() -> list:
        return [f.name for f in fields(AgentParams) if f.type is float]

    def copy(self) -> 'AgentParams':
        return AgentParams(**{f.name: getattr(self, f.name) for f in fields(self)})

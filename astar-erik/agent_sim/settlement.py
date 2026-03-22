"""Settlement entity for the agent-based simulator."""

from dataclasses import dataclass
import numpy as np


@dataclass
class Settlement:
    x: int
    y: int
    population: float
    food: float
    defense: float
    wealth: float
    owner_id: int
    has_port: bool
    alive: bool = True

    def distance_to(self, other: 'Settlement') -> float:
        return max(abs(self.x - other.x), abs(self.y - other.y))  # Chebyshev

    @staticmethod
    def sample_initial(x: int, y: int, owner_id: int, has_port: bool,
                       rng: np.random.Generator, params) -> 'Settlement':
        """Create a settlement with stats sampled from replay-derived distributions."""
        pop = max(0.1, rng.normal(params.init_pop_mean, params.init_pop_std))
        food = np.clip(rng.normal(params.init_food_mean, params.init_food_std), 0.0, 1.0)
        defense = np.clip(rng.normal(params.init_defense_mean, params.init_defense_std), 0.01, 1.0)
        wealth = max(0.0, rng.normal(params.init_wealth_mean, params.init_wealth_std))
        return Settlement(x=x, y=y, population=pop, food=food, defense=defense,
                         wealth=wealth, owner_id=owner_id, has_port=has_port)

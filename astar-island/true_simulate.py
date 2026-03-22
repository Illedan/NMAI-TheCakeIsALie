"""True settlement-level simulation of Astar Island.

Models individual settlement stats (population, food, wealth, defense),
spawning, raiding, collapse, and terrain transitions based on empirical
mechanics documented in game_cycle_gen.md.
"""

from __future__ import annotations

import math
import random as pyrandom

import numpy as np

NSTEPS = 50

# Raw grid values
OCEAN = 10
PLAINS = 11
FOREST = 4
MOUNTAIN = 5
SETTLEMENT = 1
PORT = 2
RUIN = 3

# Prediction classes
RAW_TO_CLASS = {0: 0, 10: 0, 11: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
NUM_CLASSES = 6


class RNG:
    """Thin RNG wrapper using Python's stdlib random (avoids broken numpy.random)."""

    def __init__(self, seed: int | None = None):
        self._rng = pyrandom.Random(seed)

    def random(self) -> float:
        return self._rng.random()

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self._rng.gauss(mu, sigma)

    def uniform(self, lo: float, hi: float) -> float:
        return self._rng.uniform(lo, hi)

    def choice(self, n: int, p: list[float] | None = None) -> int:
        if p is None:
            return self._rng.randrange(n)
        r = self._rng.random()
        cumsum = 0.0
        for i, pi in enumerate(p):
            cumsum += pi
            if r < cumsum:
                return i
        return n - 1


class Settlement:
    """A single Norse settlement on the map."""

    __slots__ = ("x", "y", "population", "food", "wealth", "defense",
                 "has_port", "alive", "owner_id")

    def __init__(self, x: int, y: int, population: float, food: float,
                 wealth: float, defense: float, has_port: bool,
                 alive: bool, owner_id: int):
        self.x = x
        self.y = y
        self.population = population
        self.food = food
        self.wealth = wealth
        self.defense = defense
        self.has_port = has_port
        self.alive = alive
        self.owner_id = owner_id

    def copy(self) -> "Settlement":
        return Settlement(
            self.x, self.y, self.population, self.food,
            self.wealth, self.defense, self.has_port,
            self.alive, self.owner_id,
        )

    def to_dict(self) -> dict:
        return {
            "x": self.x, "y": self.y,
            "population": self.population, "food": self.food,
            "wealth": self.wealth, "defense": self.defense,
            "has_port": self.has_port, "alive": self.alive,
            "owner_id": self.owner_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "Settlement":
        return Settlement(
            x=d["x"], y=d["y"],
            population=d["population"], food=d["food"],
            wealth=d["wealth"], defense=d["defense"],
            has_port=d["has_port"], alive=d["alive"],
            owner_id=d["owner_id"],
        )

    def __repr__(self):
        status = "alive" if self.alive else "dead"
        port = " port" if self.has_port else ""
        return (f"Settlement(({self.x},{self.y}) owner={self.owner_id} "
                f"pop={self.population:.3f} food={self.food:.3f} "
                f"wealth={self.wealth:.3f} def={self.defense:.3f} "
                f"{status}{port})")


class GameState:
    """Full game state: terrain grid + settlements.

    The grid stores raw terrain values (OCEAN, PLAINS, FOREST, MOUNTAIN,
    SETTLEMENT, PORT, RUIN). Settlement/Port cells are backed by Settlement
    objects in the settlements list.
    """

    def __init__(self, grid: np.ndarray, settlements: list[Settlement]):
        self.grid = grid.copy()
        self.H, self.W = grid.shape
        self.settlements = [s.copy() for s in settlements]

        # Precomputed static masks
        self.ocean_mask = (grid == OCEAN)
        self.mountain_mask = (grid == MOUNTAIN)

        # Precompute per-cell ocean neighbor count (8-connected)
        ocean_f = self.ocean_mask.astype(np.float64)
        padded = np.pad(ocean_f, 1, mode="constant")
        self.n_ocean = np.zeros((self.H, self.W), dtype=np.float64)
        for dy in range(3):
            for dx in range(3):
                if dy == 1 and dx == 1:
                    continue
                self.n_ocean += padded[dy:dy + self.H, dx:dx + self.W]

        self._rebuild_lookup()

    def _rebuild_lookup(self):
        """Rebuild the spatial lookup from the settlements list."""
        self.settlement_at = {}
        for s in self.settlements:
            if s.alive:
                self.settlement_at[(s.x, s.y)] = s

    def alive_settlements(self) -> list[Settlement]:
        return [s for s in self.settlements if s.alive]

    def settlements_by_owner(self) -> dict[int, list[Settlement]]:
        groups: dict[int, list[Settlement]] = {}
        for s in self.settlements:
            if s.alive:
                groups.setdefault(s.owner_id, []).append(s)
        return groups

    def neighbors_manhattan(self, x: int, y: int, dist: int = 1) -> list[tuple[int, int]]:
        result = []
        for dy in range(-dist, dist + 1):
            for dx in range(-dist, dist + 1):
                if abs(dx) + abs(dy) > dist or (dx == 0 and dy == 0):
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.W and 0 <= ny < self.H:
                    result.append((nx, ny))
        return result

    def neighbors_chebyshev(self, x: int, y: int, dist: int = 1) -> list[tuple[int, int]]:
        result = []
        for dy in range(-dist, dist + 1):
            for dx in range(-dist, dist + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.W and 0 <= ny < self.H:
                    result.append((nx, ny))
        return result

    def count_adj_settlements(self, x: int, y: int) -> int:
        """Count 8-connected alive settlements adjacent to (x, y)."""
        count = 0
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if (nx, ny) in self.settlement_at:
                    count += 1
        return count

    def sync_grid(self):
        """Update the grid to reflect current settlement states."""
        for s in self.settlements:
            if s.alive:
                self.grid[s.y, s.x] = PORT if s.has_port else SETTLEMENT
            else:
                if self.grid[s.y, s.x] in (SETTLEMENT, PORT):
                    self.grid[s.y, s.x] = RUIN
        self._rebuild_lookup()

    def copy(self) -> "GameState":
        gs = GameState.__new__(GameState)
        gs.grid = self.grid.copy()
        gs.H, gs.W = self.H, self.W
        gs.settlements = [s.copy() for s in self.settlements]
        gs.ocean_mask = self.ocean_mask
        gs.mountain_mask = self.mountain_mask
        gs.n_ocean = self.n_ocean
        gs._rebuild_lookup()
        return gs

    def to_class_grid(self) -> np.ndarray:
        result = np.zeros((self.H, self.W), dtype=np.int32)
        for val, cls in RAW_TO_CLASS.items():
            result[self.grid == val] = cls
        return result

    @staticmethod
    def from_replay_frame(frame: dict) -> "GameState":
        """Create GameState from a replay frame dict (has full settlement stats)."""
        grid = np.array(frame["grid"], dtype=np.int32)
        settlements = [Settlement.from_dict(s) for s in frame["settlements"]]
        return GameState(grid, settlements)

    @staticmethod
    def from_initial_state(seed_data: dict, rng: RNG | None = None) -> "GameState":
        """Create GameState from an API initial state.

        The API initial state only has (x, y, has_port, alive) — no stats.
        Stats are drawn from uniform distributions per game_cycle_gen.md:
            population: U(0.50, 1.50)
            food:       U(0.30, 0.80)
            wealth:     U(0.10, 0.50)
            defense:    U(0.20, 0.60)
        """
        if rng is None:
            rng = RNG()
        grid = np.array(seed_data["grid"], dtype=np.int32)
        settlements = []
        for i, s in enumerate(seed_data["settlements"]):
            settlements.append(Settlement(
                x=s["x"], y=s["y"],
                population=rng.uniform(0.50, 1.50),
                food=rng.uniform(0.30, 0.80),
                wealth=rng.uniform(0.10, 0.50),
                defense=rng.uniform(0.20, 0.60),
                has_port=s.get("has_port", True if (seed_data["grid"] == 2) else False),
                alive=s.get("alive", True),
                owner_id=i,
            ))
        return GameState(grid, settlements)

    def __repr__(self):
        alive = sum(1 for s in self.settlements if s.alive)
        return (f"GameState({self.H}x{self.W}, "
                f"{alive}/{len(self.settlements)} settlements alive)")


# ---------------------------------------------------------------------------
# Per-round hidden parameters
# ---------------------------------------------------------------------------

class RoundParams:
    """Hidden parameters that vary per round, sampled from fitted priors.

    All E/std values from fit_priors.py and parameters_bak.md.
    """

    def __init__(self, rng: RNG | None = None):
        if rng is None:
            rng = RNG()

        # Growth
        self.alpha_pop = max(0.01, rng.normal(0.10, 0.05))       # dpop = alpha_pop * pop
        self.alpha_def = max(0.01, rng.normal(0.083, 0.032))      # ddef = alpha_def * def

        # Food production: food_gain = alpha_plains * eff_plains + alpha_forest * eff_forest
        # Fitted from isolated non-spawning settlements across 15 rounds:
        #   alpha_plains: E=0.0183  std=0.0036
        #   alpha_forest: E=0.0220  std=0.0046
        #   beta:         E=0.0431  std=0.0163
        self.alpha_plains = max(0.0, rng.normal(0.0183, 0.0036))  # food per eff. plains tile
        self.alpha_forest = max(0.0, rng.normal(0.0220, 0.0046))  # food per eff. forest tile
        self.beta = max(0.0, rng.normal(0.0431, 0.0163))          # food consumed per pop

        # Spawning
        self.mu_spawn = max(0.5, rng.normal(2.184, 0.288))        # pop for 50% spawn chance
        self.s_spawn = max(0.01, rng.normal(0.432, 0.166))        # logistic steepness
        self.sigma_dist = max(0.3, rng.normal(1.52, 0.89))           # half-normal sigma for Manhattan spawn dist
        self.p_multi = max(0.0, min(0.5, rng.normal(0.076, 0.030)))  # multi-spawn prob
        self.hi_food_transfer = rng.normal(0.092, 0.077)           # extra food for hi-tier child
        self.mu_f_tier = max(0.0, rng.normal(0.645, 0.131))       # food threshold for hi-tier

        # Port formation
        self.port_thresh = max(0.0, rng.normal(0.454, 0.182))     # food threshold

        # Raiding
        self.p_raid_nonport = max(0.001, rng.normal(0.126, 0.063))
        self.sigma_raid_nonport = max(0.5, rng.normal(1.67, 0.10))
        self.p_raid_port = max(0.001, rng.normal(0.139, 0.092))
        self.sigma_raid_port = max(0.5, rng.normal(2.52, 0.51))
        self.p_raid_success = max(0.1, min(0.95, rng.normal(0.605, 0.048)))
        self.p_conquest = max(0.0, min(0.8, rng.normal(0.230, 0.161)))

        # Collapse
        self.collapse_s = max(0.01, rng.normal(0.158, 0.038))     # sigmoid steepness

    def __repr__(self):
        return (f"RoundParams(alpha_pop={self.alpha_pop:.3f}, "
                f"alpha_def={self.alpha_def:.3f}, "
                f"mu_spawn={self.mu_spawn:.3f}, "
                f"collapse_s={self.collapse_s:.3f})")


# ---------------------------------------------------------------------------
# Per-step evolution functions
# ---------------------------------------------------------------------------

def evolve(state: GameState, params: RoundParams, rng: RNG):
    """Execute one full step of the game cycle.

    Phase order (approximate — exact order unknown, but this matches replay data):
      1. Food production (harvest from adjacent plains/forest)
      2. Population & defense growth
      3. Food consumption
      4. Settlement spawning (children)
      5. Raiding / conflict
      6. Port formation
      7. Collapse (starvation + defense-based)
      8. Ruin transitions (rebuild or decay to forest/plains)
      9. Rare terrain transitions
    """
    step_growth(state, params, rng)
    step_spawning(state, params, rng)
    step_food_production(state, params, rng)
    step_port_formation(state, params, rng)
    step_raiding(state, params, rng)
    step_food_consumption(state, params, rng)
    step_collapse(state, params, rng)
    step_ruin_transitions(state, params, rng)
    step_rare_terrain(state, params, rng)
    state.sync_grid()


# ---------------------------------------------------------------------------
# Phase 1: Food production
# ---------------------------------------------------------------------------

def step_food_production(state: GameState, params: RoundParams, rng: RNG):
    """Each plains/forest tile adjacent to ≥1 settlement produces food, shared equally."""
    H, W = state.H, state.W
    for y in range(H):
        for x in range(W):
            val = state.grid[y, x]
            if val == PLAINS:
                alpha = params.alpha_plains
            elif val == FOREST:
                alpha = params.alpha_forest
            else:
                continue

            # Find adjacent alive settlements (8-connected)
            adj = []
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if dy == 0 and dx == 0:
                        continue
                    key = (x + dx, y + dy)
                    if key in state.settlement_at:
                        adj.append(state.settlement_at[key])
            if not adj:
                continue

            # Each tile produces food shared equally among neighbors
            share = alpha / len(adj)
            for s in adj:
                s.food += share


# ---------------------------------------------------------------------------
# Phase 2: Population & defense growth
# ---------------------------------------------------------------------------

def step_growth(state: GameState, params: RoundParams, rng: RNG):
    """Apply population and defense growth to all alive settlements.

    Population: pop_new = pop + alpha_pop * pop
    Defense:    def_new = min(def + alpha_def * def, 1.0)
    """
    for s in state.settlements:
        if not s.alive:
            continue
        s.population += params.alpha_pop * s.population
        s.defense = min(s.defense + params.alpha_def * s.defense, 1.0)


# ---------------------------------------------------------------------------
# Phase 3: Food consumption
# ---------------------------------------------------------------------------

def step_food_consumption(state: GameState, params: RoundParams, rng: RNG):
    """Settlements consume food proportional to population.

    food_new = food - beta * population
    """
    for s in state.settlements:
        if not s.alive:
            continue
        s.food -= params.beta * s.population


# ---------------------------------------------------------------------------
# Phase 4: Settlement spawning
# ---------------------------------------------------------------------------

def _logistic(x, mu, s):
    z = (x - mu) / s
    z = max(-20.0, min(20.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def step_spawning(state: GameState, params: RoundParams, rng: RNG):
    """Each isolated settlement rolls to spawn children based on population.

    - P(spawn) = logistic(pop, mu_spawn, s_spawn)
    - Distance: geometric in Chebyshev distance, lambda=sigma_dist
    - Ruin tiles 8x preferred over fresh tiles at same distance
    - Tile type determines tier: ruin→lo, plains/forest→hi
    - Multi-spawn with probability p_multi
    """
    # Snapshot parents before any spawning this step
    parents = [s for s in state.settlements if s.alive]
    by_owner = state.settlements_by_owner()
    next_owner = max(s.owner_id for s in state.settlements) + 1

    for parent in parents:
        # Only isolated settlements spawn (no same-owner neighbor within Chebyshev 6)
        has_nearby = any(
            s for s in by_owner.get(parent.owner_id, [])
            if s is not parent and max(abs(s.x - parent.x), abs(s.y - parent.y)) <= 6
        )
        if has_nearby:
            continue

        # Roll spawn probability
        p_spawn = _logistic(parent.population, params.mu_spawn, params.s_spawn)
        if rng.random() > p_spawn:
            continue

        # Spawn children (geometric: keep rolling p_multi)
        while True:
            child = _try_spawn_child(state, parent, params, rng, next_owner)
            if child is None:
                break
            state.settlements.append(child)
            state.settlement_at[(child.x, child.y)] = child

            # Roll for multi-spawn
            if rng.random() > params.p_multi:
                break
            next_owner += 1


def _try_spawn_child(state: GameState, parent: Settlement, params: RoundParams,
                     rng: RNG, next_owner: int) -> Settlement | None:
    """Try to place one child for parent. Returns Settlement or None if no valid tile."""
    # Sample Manhattan distance from half-normal, d >= 1
    for _ in range(20):  # max attempts
        d = max(1, round(abs(rng.normal(0, params.sigma_dist))))
        if d > 10:
            continue

        # Collect candidate tiles at Manhattan distance d
        candidates = []
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                if abs(dx) + abs(dy) != d:
                    continue
                nx, ny = parent.x + dx, parent.y + dy
                if not (0 <= nx < state.W and 0 <= ny < state.H):
                    continue
                val = state.grid[ny, nx]
                if val in (PLAINS, FOREST, RUIN):
                    candidates.append((nx, ny, val))

        if not candidates:
            continue

        # Weight: ruins 8x more likely than fresh tiles
        RUIN_WEIGHT = 8.0
        weights = []
        for _, _, val in candidates:
            weights.append(RUIN_WEIGHT if val == RUIN else 1.0)
        total = sum(weights)
        probs = [w / total for w in weights]

        idx = rng.choice(len(candidates), p=probs)
        cx, cy, tile = candidates[idx]

        # Determine tier based on tile
        on_ruin = (tile == RUIN)
        if on_ruin:
            # Lo-tier
            child = Settlement(
                x=cx, y=cy,
                population=0.400,
                food=0.148,
                wealth=parent.wealth * 0.098,
                defense=0.150,
                has_port=False, alive=True,
                owner_id=parent.owner_id,
            )
            # Lo-tier: no pop cost to parent
        else:
            # Hi-tier
            child = Settlement(
                x=cx, y=cy,
                population=0.500,
                food=0.148 + max(0, params.hi_food_transfer),
                wealth=parent.wealth * 0.217,
                defense=0.200,
                has_port=False, alive=True,
                owner_id=parent.owner_id,
            )
            # Hi-tier costs parent ~0.10 pop, ~0.22 food
            parent.population -= 0.10
            parent.food -= 0.22

        # Update grid
        state.grid[cy, cx] = SETTLEMENT
        return child

    return None  # no valid tile found


# ---------------------------------------------------------------------------
# Phase 5: Raiding
# ---------------------------------------------------------------------------

def step_raiding(state: GameState, params: RoundParams, rng: RNG):
    """Each enemy pair rolls for a raid based on distance and raider type.

    P(raid from dist d) = p_raid * exp(-d^2 / (2*sigma^2))
    Each enemy rolls independently. Damage is percentage-based.
    """
    alive = state.alive_settlements()
    # For each settlement, check all enemies
    for victim in alive:
        if not victim.alive:
            continue
        for raider in alive:
            if not raider.alive or raider.owner_id == victim.owner_id:
                continue

            d = abs(raider.x - victim.x) + abs(raider.y - victim.y)
            if d > 10:
                continue  # too far, skip

            # Raid probability depends on raider type
            if raider.has_port:
                p = params.p_raid_port * math.exp(-d * d / (2 * params.sigma_raid_port ** 2))
            else:
                p = params.p_raid_nonport * math.exp(-d * d / (2 * params.sigma_raid_nonport ** 2))

            if rng.random() > p:
                continue

            # Raid happens — apply damage to victim
            victim.defense -= 0.20 * victim.defense
            victim.population -= 0.15 * victim.population
            victim.food -= 0.10 * victim.food  # ~6-12%, use 10%

            # Wealth: success/fail model
            if rng.random() < params.p_raid_success:
                # Successful raid: victim loses 40%, raider gains 23% of victim's wealth
                stolen = 0.40 * victim.wealth
                victim.wealth -= stolen
                raider.wealth += 0.57 * stolen  # 57% transfer efficiency
            else:
                # Failed raid: 17% chance raider loses ~20% wealth
                if rng.random() < 0.174:
                    raider.wealth -= 0.20 * raider.wealth

            # Conquest: small chance of owner change
            if rng.random() < params.p_conquest:
                victim.owner_id = raider.owner_id


# ---------------------------------------------------------------------------
# Phase 6: Port formation
# ---------------------------------------------------------------------------

def step_port_formation(state: GameState, params: RoundParams, rng: RNG):
    """Settlements with 2+ ocean neighbors can become ports if food >= threshold."""
    for s in state.settlements:
        if not s.alive or s.has_port:
            continue
        n_oc = int(state.n_ocean[s.y, s.x])
        if n_oc < 2:
            continue
        if s.food < params.port_thresh:
            continue
        if rng.random() < 0.104:  # port_rate_above ≈ constant
            s.has_port = True
            s.wealth += 0.005  # small one-time bonus


# ---------------------------------------------------------------------------
# Phase 7: Collapse
# ---------------------------------------------------------------------------

def step_collapse(state: GameState, params: RoundParams, rng: RNG):
    """Settlements collapse from starvation (food < 0) or low defense.

    P(collapse | defense) = sigmoid(-defense / collapse_s)
    """
    for s in state.settlements:
        if not s.alive:
            continue

        # Starvation collapse
        if s.food < 0:
            s.alive = False
            continue

        # Defense-based collapse
        z = -s.defense / params.collapse_s
        z = max(-20.0, min(20.0, z))
        p_collapse = 1.0 / (1.0 + math.exp(-z))
        if rng.random() < p_collapse:
            s.alive = False


# ---------------------------------------------------------------------------
# Phase 8: Ruin transitions
# ---------------------------------------------------------------------------

def step_ruin_transitions(state: GameState, params: RoundParams, rng: RNG):
    """Ruins either get rebuilt by nearby settlements or decay to forest/plains.

    - If same-faction settlement within Chebyshev 5 → spawning handles rebuild
    - Otherwise: 32.4% → forest, 67.6% → plains (constant ratio)
    """
    H, W = state.H, state.W
    # Collect ruin positions
    ruin_cells = []
    for y in range(H):
        for x in range(W):
            if state.grid[y, x] == RUIN:
                ruin_cells.append((x, y))

    for x, y in ruin_cells:
        # Check if any alive settlement nearby could rebuild
        has_settle = False
        for s in state.alive_settlements():
            if max(abs(s.x - x), abs(s.y - y)) <= 5:
                has_settle = True
                break

        if has_settle:
            # Rebuilding is handled by the spawning phase — ruins near settlements
            # become lo-tier children. If not spawned this step, they still transition.
            # For simplicity: if still a ruin after spawning, apply decay.
            pass

        # Decay: 32.4% forest, 67.6% plains
        if rng.random() < 0.324:
            state.grid[y, x] = FOREST
        else:
            state.grid[y, x] = PLAINS


# ---------------------------------------------------------------------------
# Phase 9: Rare terrain transitions
# ---------------------------------------------------------------------------

def step_rare_terrain(state: GameState, params: RoundParams, rng: RNG):
    """Very rare terrain transitions: plains→ruin (~0.04%), forest→ruin (~0.05%)."""
    H, W = state.H, state.W
    for y in range(H):
        for x in range(W):
            val = state.grid[y, x]
            if val == PLAINS and rng.random() < 0.0004:
                state.grid[y, x] = RUIN
            elif val == FOREST and rng.random() < 0.0005:
                state.grid[y, x] = RUIN

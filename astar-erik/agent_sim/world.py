"""World: grid + settlement list + spatial queries."""

import json
import numpy as np
from typing import Optional
from .settlement import Settlement
from .params import AgentParams

# Terrain codes from the simulation
TERRAIN_EMPTY = 0
TERRAIN_SETTLEMENT = 1
TERRAIN_PORT = 2
TERRAIN_RUIN = 3
TERRAIN_FOREST = 4
TERRAIN_MOUNTAIN = 5
TERRAIN_OCEAN = 10
TERRAIN_PLAINS = 11

# Output class codes (6 classes)
CLASS_EMPTY = 0
CLASS_SETTLEMENT = 1
CLASS_PORT = 2
CLASS_RUIN = 3
CLASS_FOREST = 4
CLASS_MOUNTAIN = 5
NUM_CLASSES = 6

TERRAIN_TO_CLASS = {
    TERRAIN_EMPTY: CLASS_EMPTY,
    TERRAIN_OCEAN: CLASS_EMPTY,
    TERRAIN_PLAINS: CLASS_EMPTY,
    TERRAIN_SETTLEMENT: CLASS_SETTLEMENT,
    TERRAIN_PORT: CLASS_PORT,
    TERRAIN_RUIN: CLASS_RUIN,
    TERRAIN_FOREST: CLASS_FOREST,
    TERRAIN_MOUNTAIN: CLASS_MOUNTAIN,
}


class World:
    def __init__(self, grid: np.ndarray, settlements: list[Settlement],
                 height: int = 40, width: int = 40):
        self.height = height
        self.width = width
        self.grid = grid.copy()  # (H, W) terrain codes
        self.settlements = settlements
        self._settlement_map: dict[tuple[int, int], int] = {}
        self._rebuild_settlement_map()

        # Precompute static features
        self.is_ocean = np.zeros((height, width), dtype=bool)
        self.is_mountain = np.zeros((height, width), dtype=bool)
        self.is_forest = np.zeros((height, width), dtype=bool)
        self.ocean_adj = np.zeros((height, width), dtype=bool)

        for y in range(height):
            for x in range(width):
                t = grid[y, x]
                if t == TERRAIN_OCEAN:
                    self.is_ocean[y, x] = True
                elif t == TERRAIN_MOUNTAIN:
                    self.is_mountain[y, x] = True
                elif t == TERRAIN_FOREST:
                    self.is_forest[y, x] = True

        # ocean_adj: cell has at least one ocean neighbor (8-connected)
        for y in range(height):
            for x in range(width):
                if self.is_ocean[y, x]:
                    continue
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < height and 0 <= nx < width:
                            if self.is_ocean[ny, nx]:
                                self.ocean_adj[y, x] = True
                                break
                    if self.ocean_adj[y, x]:
                        break

    def _rebuild_settlement_map(self):
        self._settlement_map = {}
        for i, s in enumerate(self.settlements):
            if s.alive:
                self._settlement_map[(s.x, s.y)] = i

    def settlement_at(self, x: int, y: int) -> Optional[Settlement]:
        idx = self._settlement_map.get((x, y))
        if idx is not None:
            return self.settlements[idx]
        return None

    def remove_settlement(self, s: Settlement):
        """Mark settlement as dead and update grid to ruin."""
        s.alive = False
        key = (s.x, s.y)
        if key in self._settlement_map:
            del self._settlement_map[key]
        self.grid[s.y, s.x] = TERRAIN_RUIN

    def add_settlement(self, s: Settlement):
        self.settlements.append(s)
        self._settlement_map[(s.x, s.y)] = len(self.settlements) - 1
        if s.has_port:
            self.grid[s.y, s.x] = TERRAIN_PORT
        else:
            self.grid[s.y, s.x] = TERRAIN_SETTLEMENT

    def alive_settlements(self) -> list[Settlement]:
        return [s for s in self.settlements if s.alive]

    def neighbors_in_range(self, s: Settlement, max_range: float) -> list[Settlement]:
        """Find all alive settlements within Chebyshev distance."""
        result = []
        for other in self.settlements:
            if other is s or not other.alive:
                continue
            if s.distance_to(other) <= max_range:
                result.append(other)
        return result

    def to_class_grid(self) -> np.ndarray:
        """Convert current terrain grid to 6-class grid (vectorized)."""
        # Build lookup table: max terrain code is 11 (TERRAIN_PLAINS)
        lut = np.zeros(12, dtype=int)
        for t, c in TERRAIN_TO_CLASS.items():
            lut[t] = c
        return lut[self.grid]

    def valid_expansion_cells(self, s: Settlement, radius: float) -> list[tuple[int, int]]:
        """Find cells where settlement s could expand to."""
        cells = []
        r = int(radius)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = s.y + dy, s.x + dx
                if 0 <= ny < self.height and 0 <= nx < self.width:
                    t = self.grid[ny, nx]
                    if t in (TERRAIN_EMPTY, TERRAIN_PLAINS, TERRAIN_FOREST):
                        if self.settlement_at(nx, ny) is None:
                            cells.append((nx, ny))
        return cells

    @staticmethod
    def from_initial_state(path: str, params: AgentParams,
                           rng: np.random.Generator) -> 'World':
        """Load from initial_states JSON file, sampling unknown stats."""
        with open(path) as f:
            data = json.load(f)

        grid = np.array(data['grid'], dtype=int)
        height, width = grid.shape

        settlements = []
        occupied = set()
        n_owners = len(data['settlements'])
        for i, s_data in enumerate(data['settlements']):
            x, y = s_data['x'], s_data['y']
            has_port = s_data.get('has_port', False)
            owner_id = i
            s = Settlement.sample_initial(x, y, owner_id, has_port, rng, params)
            settlements.append(s)
            occupied.add((x, y))

        # Also create settlements for grid cells with settlement/port terrain
        # but no matching settlement entity
        owner_counter = n_owners
        for y in range(height):
            for x in range(width):
                if (x, y) in occupied:
                    continue
                t = grid[y, x]
                if t == TERRAIN_SETTLEMENT:
                    s = Settlement.sample_initial(x, y, owner_counter, False, rng, params)
                    settlements.append(s)
                    owner_counter += 1
                elif t == TERRAIN_PORT:
                    s = Settlement.sample_initial(x, y, owner_counter, True, rng, params)
                    settlements.append(s)
                    owner_counter += 1

        return World(grid, settlements, height, width)

    @staticmethod
    def from_grid_and_settlements(grid: np.ndarray,
                                  settlement_data: list[dict],
                                  params: AgentParams,
                                  rng: np.random.Generator) -> 'World':
        """Create from grid array and settlement dicts (with or without stats)."""
        height, width = grid.shape
        settlements = []
        for i, s_data in enumerate(settlement_data):
            x, y = s_data['x'], s_data['y']
            has_port = s_data.get('has_port', False)
            owner_id = s_data.get('owner_id', i)

            if 'population' in s_data:
                s = Settlement(
                    x=x, y=y,
                    population=s_data['population'],
                    food=s_data['food'],
                    defense=s_data['defense'],
                    wealth=s_data.get('wealth', 0.01),
                    owner_id=owner_id,
                    has_port=has_port,
                )
            else:
                s = Settlement.sample_initial(x, y, owner_id, has_port, rng, params)
            settlements.append(s)

        return World(grid, settlements, height, width)

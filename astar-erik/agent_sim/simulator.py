"""Monte Carlo simulator: run N agent-based simulations, aggregate to probabilities."""

import json
import numpy as np
from .params import AgentParams
from .settlement import Settlement
from .world import World, NUM_CLASSES, TERRAIN_TO_CLASS, TERRAIN_SETTLEMENT, TERRAIN_PORT
from .phases import step


def simulate_once(initial_state_path: str, params: AgentParams,
                  rng: np.random.Generator) -> np.ndarray:
    """Run one simulation, return final class grid (H, W)."""
    world = World.from_initial_state(initial_state_path, params, rng)

    for t in range(params.num_steps):
        step(world, params, rng)

    return world.to_class_grid()


def _simulate_from_cached(grid: np.ndarray, settlement_entries: list[dict],
                          extra_entries: list[dict],
                          params: AgentParams,
                          rng: np.random.Generator) -> np.ndarray:
    """Run one simulation from cached initial state data."""
    height, width = grid.shape
    settlements = []

    # Named settlements
    for i, s_data in enumerate(settlement_entries):
        x, y = s_data['x'], s_data['y']
        has_port = s_data.get('has_port', False)
        s = Settlement.sample_initial(x, y, i, has_port, rng, params)
        settlements.append(s)

    # Extra grid-based settlements (settlement/port terrain without entity)
    n_owners = len(settlement_entries)
    for j, e_data in enumerate(extra_entries):
        x, y = e_data['x'], e_data['y']
        has_port = e_data['has_port']
        s = Settlement.sample_initial(x, y, n_owners + j, has_port, rng, params)
        settlements.append(s)

    world = World(grid, settlements, height, width)

    for t in range(params.num_steps):
        step(world, params, rng)

    return world.to_class_grid()


def _cache_initial_state(initial_state_path: str) -> dict:
    """Parse initial state file and cache the data."""
    with open(initial_state_path) as f:
        data = json.load(f)
    grid = np.array(data['grid'], dtype=int)
    height, width = grid.shape
    settlement_entries = data['settlements']

    # Find extra settlement/port cells not in the entity list
    occupied = set()
    for s_data in settlement_entries:
        occupied.add((s_data['x'], s_data['y']))

    extra_entries = []
    for y in range(height):
        for x in range(width):
            if (x, y) in occupied:
                continue
            t = grid[y, x]
            if t == TERRAIN_SETTLEMENT:
                extra_entries.append({'x': x, 'y': y, 'has_port': False})
            elif t == TERRAIN_PORT:
                extra_entries.append({'x': x, 'y': y, 'has_port': True})

    return {
        'grid': grid,
        'height': height,
        'width': width,
        'settlement_entries': settlement_entries,
        'extra_entries': extra_entries,
    }


def simulate_once_from_world(grid: np.ndarray, settlement_data: list[dict],
                             params: AgentParams,
                             rng: np.random.Generator) -> np.ndarray:
    """Run one simulation from pre-built grid and settlements."""
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

    world = World(grid, settlements, height, width)

    for t in range(params.num_steps):
        step(world, params, rng)

    return world.to_class_grid()


def monte_carlo(initial_state_path: str, params: AgentParams,
                n_sims: int = None, seed: int = 42) -> np.ndarray:
    """Run Monte Carlo simulations, return probability tensor (H, W, 6).

    Each simulation samples random initial stats and runs stochastically.
    The output is the fraction of simulations resulting in each class per cell.
    """
    if n_sims is None:
        n_sims = params.num_monte_carlo

    # Load and cache initial state ONCE
    cache = _cache_initial_state(initial_state_path)
    grid = cache['grid']
    height, width = cache['height'], cache['width']

    counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    for i in range(n_sims):
        rng = np.random.default_rng(seed + i)
        final_grid = _simulate_from_cached(
            grid, cache['settlement_entries'], cache['extra_entries'],
            params, rng)

        # Vectorized counting
        rows = np.arange(height)[:, None]
        cols = np.arange(width)[None, :]
        np.add.at(counts, (rows, cols, final_grid), 1)

    # Normalize to probabilities
    probs = counts / n_sims

    # Floor: never use 0.0 (causes KL divergence to infinity)
    floor = 0.01
    probs = np.maximum(probs, floor)
    probs /= probs.sum(axis=2, keepdims=True)

    return probs


def monte_carlo_from_data(grid: np.ndarray, settlement_data: list[dict],
                          params: AgentParams, n_sims: int = None,
                          seed: int = 42) -> np.ndarray:
    """Monte Carlo from pre-built grid and settlement data."""
    if n_sims is None:
        n_sims = params.num_monte_carlo

    height, width = grid.shape
    counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    for i in range(n_sims):
        rng = np.random.default_rng(seed + i)
        final_grid = simulate_once_from_world(grid, settlement_data, params, rng)

        rows = np.arange(height)[:, None]
        cols = np.arange(width)[None, :]
        np.add.at(counts, (rows, cols, final_grid), 1)

    probs = counts / n_sims
    floor = 0.01
    probs = np.maximum(probs, floor)
    probs /= probs.sum(axis=2, keepdims=True)

    return probs


def save_prediction(probs: np.ndarray, output_path: str):
    """Save probability tensor as JSON in competition format [H][W][6]."""
    height, width, _ = probs.shape
    result = []
    for y in range(height):
        row = []
        for x in range(width):
            row.append([round(float(probs[y, x, c]), 6) for c in range(NUM_CLASSES)])
        result.append(row)

    with open(output_path, 'w') as f:
        json.dump(result, f)

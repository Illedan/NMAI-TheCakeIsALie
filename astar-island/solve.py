"""
Astar Island solver — observe, aggregate, predict.

Usage:
    python solve.py --token YOUR_JWT_TOKEN
    python solve.py --token YOUR_JWT_TOKEN --round-id UUID
"""

import argparse
import json
import time
import numpy as np
import requests

BASE = "https://api.ainm.no/astar-island"

# Terrain code → prediction class
TERRAIN_TO_CLASS = {
    0: 0,   # Empty → Empty
    10: 0,  # Ocean → Empty
    11: 0,  # Plains → Empty
    1: 1,   # Settlement
    2: 2,   # Port
    3: 3,   # Ruin
    4: 4,   # Forest
    5: 5,   # Mountain
}

NUM_CLASSES = 6


def make_session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    return s


def get_active_round(session: requests.Session) -> dict | None:
    rounds = session.get(f"{BASE}/rounds").json()
    active = next((r for r in rounds if r["status"] == "active"), None)
    if active:
        return active
    # Fall back to most recent non-completed
    for status in ["scoring", "pending", "completed"]:
        found = next((r for r in rounds if r["status"] == status), None)
        if found:
            return found
    return None


def get_round_detail(session: requests.Session, round_id: str) -> dict:
    resp = session.get(f"{BASE}/rounds/{round_id}")
    resp.raise_for_status()
    return resp.json()


def get_budget(session: requests.Session) -> dict:
    resp = session.get(f"{BASE}/budget")
    resp.raise_for_status()
    return resp.json()


def simulate(session: requests.Session, round_id: str, seed_index: int,
             vx: int, vy: int, vw: int = 15, vh: int = 15) -> dict:
    resp = session.post(f"{BASE}/simulate", json={
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": vx,
        "viewport_y": vy,
        "viewport_w": vw,
        "viewport_h": vh,
    })
    resp.raise_for_status()
    return resp.json()


def submit_prediction(session: requests.Session, round_id: str,
                      seed_index: int, prediction: np.ndarray) -> dict:
    resp = session.post(f"{BASE}/submit", json={
        "round_id": round_id,
        "seed_index": seed_index,
        "prediction": prediction.tolist(),
    })
    resp.raise_for_status()
    return resp.json()


def initial_grid_to_class(grid: list[list[int]]) -> np.ndarray:
    """Convert initial terrain grid to class indices."""
    h, w = len(grid), len(grid[0])
    result = np.zeros((h, w), dtype=int)
    for y in range(h):
        for x in range(w):
            result[y, x] = TERRAIN_TO_CLASS.get(grid[y][x], 0)
    return result


def build_static_prior(initial_class_grid: np.ndarray) -> np.ndarray:
    """Build a prior from the initial grid — static cells get high confidence."""
    h, w = initial_class_grid.shape
    prior = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)

    for y in range(h):
        for x in range(w):
            c = initial_class_grid[y, x]
            if c == 5:  # Mountain — never changes
                prior[y, x, 5] = 1.0
            elif c == 0:
                # Ocean cells on border stay ocean. Inner plains/empty can change.
                # Heuristic: if surrounded by ocean or is border, very likely stays empty
                prior[y, x, 0] = 0.85
                prior[y, x, 1] = 0.03
                prior[y, x, 2] = 0.02
                prior[y, x, 3] = 0.03
                prior[y, x, 4] = 0.05
                prior[y, x, 5] = 0.02
            elif c == 4:  # Forest — mostly static but can be reclaimed
                prior[y, x, 4] = 0.80
                prior[y, x, 0] = 0.05
                prior[y, x, 1] = 0.05
                prior[y, x, 2] = 0.02
                prior[y, x, 3] = 0.05
                prior[y, x, 5] = 0.03
            elif c == 1:  # Settlement — can grow, become ruin, etc.
                prior[y, x, 1] = 0.35
                prior[y, x, 2] = 0.15
                prior[y, x, 3] = 0.25
                prior[y, x, 0] = 0.10
                prior[y, x, 4] = 0.10
                prior[y, x, 5] = 0.05
            elif c == 2:  # Port
                prior[y, x, 2] = 0.30
                prior[y, x, 1] = 0.15
                prior[y, x, 3] = 0.25
                prior[y, x, 0] = 0.15
                prior[y, x, 4] = 0.10
                prior[y, x, 5] = 0.05
            else:
                prior[y, x] = 1.0 / NUM_CLASSES

    return prior


def plan_viewports(width: int, height: int, num_queries: int,
                   initial_class_grid: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Plan viewport positions to maximize coverage of dynamic areas.

    Returns list of (vx, vy, vw, vh) tuples.
    """
    max_vp = 15

    # Tile the map with overlapping viewports to get full coverage
    # 40×40 with 15×15 viewports: need ceil(40/15)=3 in each dimension = 9 viewports for full coverage
    # But we can overlap a bit for better statistics
    viewports = []

    # Full coverage tiling (3×3 = 9 viewports)
    xs = [0, 13, 25]
    ys = [0, 13, 25]

    for vy in ys:
        for vx in xs:
            vw = min(max_vp, width - vx)
            vh = min(max_vp, height - vy)
            viewports.append((vx, vy, vw, vh))

    # If we have more budget, add viewports centered on interesting areas
    # (areas with settlements in initial state)
    if num_queries > 9:
        # Find settlement clusters
        settlement_positions = []
        for y in range(height):
            for x in range(width):
                if initial_class_grid[y, x] in (1, 2):  # Settlement or Port
                    settlement_positions.append((x, y))

        # Add viewports centered on settlement clusters
        for sx, sy in settlement_positions[:num_queries - 9]:
            vx = max(0, min(sx - 7, width - max_vp))
            vy = max(0, min(sy - 7, height - max_vp))
            viewports.append((vx, vy, max_vp, max_vp))

    return viewports[:num_queries]


def observe_seed(session: requests.Session, round_id: str, seed_index: int,
                 viewports: list[tuple[int, int, int, int]],
                 width: int, height: int) -> np.ndarray:
    """Run simulation queries for a seed, return observation counts [H, W, NUM_CLASSES]."""
    counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)

    for i, (vx, vy, vw, vh) in enumerate(viewports):
        print(f"  Seed {seed_index}, query {i+1}/{len(viewports)}: "
              f"viewport ({vx},{vy}) {vw}x{vh}")

        result = simulate(session, round_id, seed_index, vx, vy, vw, vh)
        grid = result["grid"]
        vp = result["viewport"]
        actual_vx, actual_vy = vp["x"], vp["y"]
        actual_vw, actual_vh = vp["w"], vp["h"]

        for row_idx, row in enumerate(grid):
            for col_idx, val in enumerate(row):
                gy = actual_vy + row_idx
                gx = actual_vx + col_idx
                if 0 <= gy < height and 0 <= gx < width:
                    c = TERRAIN_TO_CLASS.get(val, 0)
                    counts[gy, gx, c] += 1.0

        # Rate limit: max 5 req/sec
        time.sleep(0.25)

    return counts


def build_prediction(counts: np.ndarray, prior: np.ndarray,
                     prior_weight: float = 0.5) -> np.ndarray:
    """Combine observation counts with prior to build prediction tensor."""
    h, w, c = counts.shape
    prediction = np.zeros_like(counts)

    for y in range(h):
        for x in range(w):
            obs_total = counts[y, x].sum()
            if obs_total > 0:
                # Blend observed frequencies with prior
                obs_dist = counts[y, x] / obs_total
                # More observations → trust observations more
                alpha = obs_total / (obs_total + prior_weight)
                prediction[y, x] = alpha * obs_dist + (1 - alpha) * prior[y, x]
            else:
                # No observations — use prior
                prediction[y, x] = prior[y, x]

    # Apply probability floor and renormalize
    prediction = np.maximum(prediction, 0.01)
    prediction = prediction / prediction.sum(axis=-1, keepdims=True)

    return prediction


def main():
    parser = argparse.ArgumentParser(description="Astar Island solver")
    parser.add_argument("--token", required=True, help="JWT token from app.ainm.no")
    parser.add_argument("--round-id", help="Specific round ID (default: active round)")
    parser.add_argument("--queries-per-seed", type=int, default=10,
                        help="Queries to allocate per seed (default: 10, total 50)")
    args = parser.parse_args()

    session = make_session(args.token)

    # 1. Find the round
    if args.round_id:
        round_info = session.get(f"{BASE}/rounds/{args.round_id}").json()
    else:
        round_info = get_active_round(session)
        if not round_info:
            print("No active round found!")
            return
        round_id = round_info["id"]
        round_info = get_round_detail(session, round_id)

    round_id = round_info["id"]
    width = round_info["map_width"]
    height = round_info["map_height"]
    seeds_count = round_info.get("seeds_count", 5)
    initial_states = round_info.get("initial_states", [])

    print(f"Round: {round_id}")
    print(f"Map: {width}x{height}, {seeds_count} seeds")
    print(f"Initial states: {len(initial_states)}")

    # 2. Check budget
    try:
        budget = get_budget(session)
        remaining = budget["queries_max"] - budget["queries_used"]
        print(f"Budget: {budget['queries_used']}/{budget['queries_max']} used, {remaining} remaining")
    except Exception as e:
        print(f"Could not check budget: {e}")
        remaining = 50

    # 3. Allocate queries across seeds
    queries_per_seed = min(args.queries_per_seed, remaining // seeds_count)
    if queries_per_seed < 1:
        print("Not enough queries remaining! Submitting prior-only predictions.")
        queries_per_seed = 0

    print(f"Allocating {queries_per_seed} queries per seed "
          f"({queries_per_seed * seeds_count} total)")

    # 4. For each seed: observe + predict + submit
    for seed_idx in range(seeds_count):
        print(f"\n{'='*60}")
        print(f"Processing seed {seed_idx}")
        print(f"{'='*60}")

        # Get initial grid for this seed
        if seed_idx < len(initial_states):
            initial_grid = initial_states[seed_idx]["grid"]
            initial_class = initial_grid_to_class(initial_grid)
            settlements = initial_states[seed_idx].get("settlements", [])
            print(f"  Initial settlements: {len(settlements)}")
        else:
            initial_class = np.zeros((height, width), dtype=int)
            settlements = []

        # Build prior from initial state
        prior = build_static_prior(initial_class)

        # Plan and execute observations
        if queries_per_seed > 0:
            viewports = plan_viewports(width, height, queries_per_seed, initial_class)
            counts = observe_seed(session, round_id, seed_idx, viewports, width, height)
            observed_cells = (counts.sum(axis=-1) > 0).sum()
            print(f"  Observed {observed_cells}/{width*height} cells")
        else:
            counts = np.zeros((height, width, NUM_CLASSES))

        # Build and submit prediction
        prediction = build_prediction(counts, prior)
        print(f"  Prediction shape: {prediction.shape}")
        print(f"  Prob range: [{prediction.min():.4f}, {prediction.max():.4f}]")
        print(f"  Sum check (should be 1.0): {prediction[0,0].sum():.4f}")

        result = submit_prediction(session, round_id, seed_idx, prediction)
        print(f"  Submitted seed {seed_idx}: {result}")

    # 5. Check scores
    print(f"\n{'='*60}")
    print("Done! Checking scores...")
    try:
        my_rounds = session.get(f"{BASE}/my-rounds").json()
        for r in my_rounds:
            if r["id"] == round_id:
                print(f"  Round score: {r.get('round_score')}")
                print(f"  Seed scores: {r.get('seed_scores')}")
                print(f"  Rank: {r.get('rank')}/{r.get('total_teams')}")
                break
    except Exception as e:
        print(f"  Could not fetch scores: {e}")


if __name__ == "__main__":
    main()

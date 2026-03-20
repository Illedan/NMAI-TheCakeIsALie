"""Fetch active round, run simulations, and submit predictions to Astar Island."""

import numpy as np
import requests
import sys
from secrets import ACCESS_TOKEN
from simulate import State, Statistic, RAW_TO_CLASS, NUM_CLASSES

BASE_URL = "https://api.ainm.no/astar-island"
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
NUM_SIMULATIONS = 1200


def get_active_round():
    resp = requests.get(f"{BASE_URL}/rounds", headers=HEADERS)
    resp.raise_for_status()
    rounds = resp.json()
    active = next((r for r in rounds if r["status"] == "active"), None)
    if not active:
        print("No active round found.")
        print("Available rounds:", [(r["round_number"], r["status"]) for r in rounds])
        sys.exit(1)
    return active


def get_round_details(round_id):
    resp = requests.get(f"{BASE_URL}/rounds/{round_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def raw_grid_to_classes(raw_grid):
    class_grid = np.zeros_like(raw_grid)
    for raw_val, class_idx in RAW_TO_CLASS.items():
        class_grid[raw_grid == raw_val] = class_idx
    return class_grid


def run_simulations(initial_class_grid, ocean_mask, n_sims):
    H, W = initial_class_grid.shape
    stats = Statistic(n_sims, H, W)
    for i in range(n_sims):
        game = State(initial_class_grid, ocean_mask)
        game.simulate()
        stats.final_states[i] = game.state
        stats.count = i + 1
    return stats.normalize()


def submit_prediction(round_id, seed_index, prediction):
    resp = requests.post(f"{BASE_URL}/submit", headers=HEADERS, json={
        "round_id": round_id,
        "seed_index": seed_index,
        "prediction": prediction.tolist(),
    })
    resp.raise_for_status()
    return resp.json()


def main():
    print("Fetching active round...")
    active = get_active_round()
    round_id = active["id"]
    print(f"Active round: #{active['round_number']} ({round_id})")

    print("Fetching round details...")
    details = get_round_details(round_id)
    seeds_count = details["seeds_count"]
    print(f"Map: {details['map_width']}x{details['map_height']}, {seeds_count} seeds")

    for seed_idx in range(seeds_count):
        print(f"\n--- Seed {seed_idx} ---")
        initial_state = details["initial_states"][seed_idx]
        raw_grid = np.array(initial_state["grid"], dtype=np.int32)
        ocean_mask = (raw_grid == 10)
        class_grid = raw_grid_to_classes(raw_grid)

        print(f"Running {NUM_SIMULATIONS} simulations...")
        prediction = run_simulations(class_grid, ocean_mask, NUM_SIMULATIONS)

        print("Submitting prediction...")
        result = submit_prediction(round_id, seed_idx, prediction)
        print(f"  {result}")

    print("\nAll seeds submitted!")


if __name__ == "__main__":
    main()

"""Astar Island API client — all endpoints from the specification."""

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from time import sleep

import requests

from secrets import ACCESS_TOKEN

BASE = "https://api.ainm.no/astar-island"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    return s


SESSION = _session()


# ── GET endpoints ────────────────────────────────────────────────────────────

def get_rounds() -> list[dict]:
    """GET /rounds — list all rounds with status and timing."""
    resp = SESSION.get(f"{BASE}/rounds")
    resp.raise_for_status()
    return resp.json()


def get_round_detail(round_id: str) -> dict:
    """GET /rounds/{round_id} — round details + initial states for all seeds."""
    resp = SESSION.get(f"{BASE}/rounds/{round_id}")
    resp.raise_for_status()
    return resp.json()


def get_budget() -> dict:
    """GET /budget — query budget for active round."""
    resp = SESSION.get(f"{BASE}/budget")
    resp.raise_for_status()
    return resp.json()


def get_my_rounds() -> list[dict]:
    """GET /my-rounds — rounds enriched with team scores, rank, and budget."""
    resp = SESSION.get(f"{BASE}/my-rounds")
    resp.raise_for_status()
    return resp.json()


def get_my_predictions(round_id: str) -> list[dict]:
    """GET /my-predictions/{round_id} — submitted predictions with argmax/confidence."""
    resp = SESSION.get(f"{BASE}/my-predictions/{round_id}")
    resp.raise_for_status()
    return resp.json()


def get_analysis(round_id: str, seed_index: int) -> dict:
    """GET /analysis/{round_id}/{seed_index} — post-round ground truth comparison."""
    resp = SESSION.get(f"{BASE}/analysis/{round_id}/{seed_index}")
    resp.raise_for_status()
    return resp.json()


def get_leaderboard() -> list[dict]:
    """GET /leaderboard — public leaderboard."""
    resp = SESSION.get(f"{BASE}/leaderboard")
    resp.raise_for_status()
    return resp.json()


# ── POST endpoints ───────────────────────────────────────────────────────────

def simulate(round_id: str, seed_index: int,
             viewport_x: int = 0, viewport_y: int = 0,
             viewport_w: int = 15, viewport_h: int = 15) -> dict:
    """POST /simulate — run one stochastic simulation, observe viewport."""
    payload = {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": viewport_x,
        "viewport_y": viewport_y,
        "viewport_w": viewport_w,
        "viewport_h": viewport_h,
    }
    resp = SESSION.post(f"{BASE}/simulate", json=payload)
    resp.raise_for_status()
    return resp.json()


def submit(round_id: str, seed_index: int, prediction: list) -> dict:
    """POST /submit — submit H×W×6 probability tensor for one seed."""
    payload = {
        "round_id": round_id,
        "seed_index": seed_index,
        "prediction": prediction,
    }
    resp = SESSION.post(f"{BASE}/submit", json=payload)
    resp.raise_for_status()
    return resp.json()


# ── EXTENSIONS ───────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INITIAL_STATES_DIR = os.path.join(SCRIPT_DIR, "initial_states")


def get_active_round() -> dict:
    """Return the active round dict, or raise if none found."""
    rounds = get_rounds()
    active = [r for r in rounds if r["status"] == "active"]
    if not active:
        raise RuntimeError("No active round found. Available statuses: "
                           + ", ".join(set(r["status"] for r in rounds)))
    return active[0]


@lru_cache(maxsize=None)
def resolve_round_id(round_id: str | None = None) -> str:
    """Return round_id as-is, or look up the active round. Cached."""
    if round_id:
        return round_id
    active = get_active_round()
    round_id = active["id"]
    print(f"Active round: {round_id} (round #{active['round_number']})")
    return round_id


def store_initial_states(round_id: str | None = None) -> str:
    """Fetch and store initial states for all seeds of a given round.

    Saves to initial_states/<timestamp>_<round_id[:8]>/ with:
      - seed_0.json .. seed_N.json  (grid + settlements per seed)
      - summary.json                (round metadata)

    Returns the path to the created folder.
    """
    round_id = resolve_round_id(round_id)
    detail = get_round_detail(round_id)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(INITIAL_STATES_DIR, f"{ts}_{round_id[:8]}")
    os.makedirs(folder, exist_ok=True)

    initial_states = detail.get("initial_states", [])
    for idx, state in enumerate(initial_states):
        seed_path = os.path.join(folder, f"seed_{idx}.json")
        with open(seed_path, "w") as f:
            json.dump(state, f, indent=2)
        print(f"  Saved seed {idx} to {seed_path}")

    summary = {
        "round_id": round_id,
        "round_number": detail.get("round_number"),
        "status": detail.get("status"),
        "map_width": detail.get("map_width"),
        "map_height": detail.get("map_height"),
        "seeds_count": detail.get("seeds_count", len(initial_states)),
        "timestamp": ts,
    }
    summary_path = os.path.join(folder, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary saved to {summary_path}")

    return folder


def _get_stored_round_ids() -> set[str]:
    """Return the set of round IDs already saved in initial_states/."""
    stored = set()
    if os.path.isdir(INITIAL_STATES_DIR):
        for d in os.listdir(INITIAL_STATES_DIR):
            summary_path = os.path.join(INITIAL_STATES_DIR, d, "summary.json")
            if os.path.isfile(summary_path):
                with open(summary_path) as f:
                    stored.add(json.load(f).get("round_id"))
    return stored


def ensure_active_initial_states() -> str | None:
    """Store initial states for the active round if not already stored.

    Returns the folder path if newly stored, or None if already exists.
    """
    active = get_active_round()
    round_id = active["id"]
    if round_id in _get_stored_round_ids():
        print(f"Initial states for round #{active['round_number']} ({round_id[:8]}) already stored.")
        return None
    print(f"New round #{active['round_number']} ({round_id[:8]}) — storing initial states...")
    return store_initial_states(round_id)


def store_all_previous_initial_states() -> list[str]:
    """Fetch and store initial states for all non-active rounds, skipping already stored ones."""
    rounds = get_rounds()
    active_ids = {r["id"] for r in rounds if r["status"] == "active"}
    previous = [r for r in rounds if r["id"] not in active_ids]
    stored = _get_stored_round_ids()

    folders = []
    for r in previous:
        if r["id"] in stored:
            print(f"Skipping round #{r['round_number']} ({r['id'][:8]}) — already stored")
            continue
        print(f"Fetching round #{r['round_number']} ({r['id'][:8]})...")
        folders.append(store_initial_states(r["id"]))
        sleep(1)

    print(f"Done. Stored {len(folders)} new rounds.")
    return folders


def query_viewports(seed_indices: list[int],
                    viewports: list[tuple[int, int, int, int]],
                    round_id: str | None = None,
                    delay: float = 0.22) -> dict[int, list[dict]]:
    """Query a list of viewports for each seed via POST /simulate.

    Args:
        seed_indices: List of seed indices (0-4) to query.
        viewports: List of (x, y, w, h) tuples for each viewport.
        round_id: UUID of the round (default: active round).
        delay: Seconds between requests (default 0.22, respects 5 req/s limit).

    Returns:
        Dict mapping seed_index to list of {viewport, response} dicts.
    """
    round_id = resolve_round_id(round_id)
    results = {}
    for seed_idx in seed_indices:
        seed_results = []
        print(f"--- Seed {seed_idx} ---")
        for vx, vy, vw, vh in viewports:
            result = simulate(round_id, seed_idx, vx, vy, vw, vh)
            seed_results.append({
                "viewport": {"x": vx, "y": vy, "w": vw, "h": vh},
                "response": result,
            })
            used = result.get("queries_used", "?")
            max_q = result.get("queries_max", "?")
            print(f"  viewport ({vx},{vy}) {vw}x{vh} -> OK  [{used}/{max_q}]")
            sleep(delay)
        results[seed_idx] = seed_results
    return results

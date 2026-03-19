"""
Query the POST /astar-island/simulate endpoint for all seeds across
a tiled grid of 15×15 viewports, saving each response to simulations/.

Usage:
    python query_simulate.py
    python query_simulate.py --round-id UUID
    python query_simulate.py --seeds 0 2 4 --delay 0.25
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone

import requests

from secrets import ACCESS_TOKEN

BASE = "https://api.ainm.no/astar-island"
SIMULATIONS_DIR = os.path.join(os.path.dirname(__file__), "simulations")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    return s


def get_active_round(session: requests.Session) -> dict:
    resp = session.get(f"{BASE}/rounds")
    resp.raise_for_status()
    rounds = resp.json()
    active = [r for r in rounds if r["status"] == "active"]
    if not active:
        raise RuntimeError("No active round found. Available statuses: "
                           + ", ".join(set(r["status"] for r in rounds)))
    return active[0]


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
    payload = {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": vx,
        "viewport_y": vy,
        "viewport_w": vw,
        "viewport_h": vh,
    }
    resp = session.post(f"{BASE}/simulate", json=payload)
    resp.raise_for_status()
    return resp.json()


def plan_viewports(budget: int, n_seeds: int,
                   map_w: int = 40, map_h: int = 40, vp_size: int = 15):
    """Place overlapping 15×15 viewports over the interior, skipping ocean edges.

    Distributes the budget evenly across seeds. Uses a 3×3 grid offset from
    the map border (ocean), plus extra center-area viewports if budget allows.
    All viewports are max size (15×15) — overlap is preferred over smaller tiles.
    """
    per_seed = budget // n_seeds

    # Interior region: skip ~3 cells of ocean border on each side
    # Valid x range: 0..25 (map_w - vp_size), same for y
    max_x = map_w - vp_size   # 25
    max_y = map_h - vp_size   # 25

    # 3×3 base grid covering the interior with ~5-cell overlap between neighbors
    # x: 3, 13, 23  →  covers cols 3-17, 13-27, 23-37
    # y: 3, 13, 23  →  covers rows 3-17, 13-27, 23-37
    base_positions = [(3, 3), (13, 3), (23, 3),
                      (3, 13), (13, 13), (23, 13),
                      (3, 23), (13, 23), (23, 23)]

    # Extra viewports offset to fill gaps / add center coverage
    extras = [(8, 8), (18, 8), (8, 18), (18, 18),
              (13, 8), (8, 13), (18, 13), (13, 18)]

    all_candidates = base_positions + extras
    viewports = [(x, y, vp_size, vp_size) for x, y in all_candidates[:per_seed]]
    return viewports


def main():
    parser = argparse.ArgumentParser(description="Query the Astar Island simulate endpoint")
    parser.add_argument("--round-id", type=str, default=None,
                        help="Round UUID (default: auto-detect active round)")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(5)),
                        help="Seed indices to query (default: 0 1 2 3 4)")
    parser.add_argument("--delay", type=float, default=0.22,
                        help="Delay between requests in seconds (default: 0.22, respects 5 req/s limit)")
    args = parser.parse_args()

    os.makedirs(SIMULATIONS_DIR, exist_ok=True)
    session = make_session()

    # Resolve round
    if args.round_id:
        round_id = args.round_id
        print(f"Using provided round: {round_id}")
    else:
        active = get_active_round(session)
        round_id = active["id"]
        print(f"Active round: {round_id} (round #{active['round_number']})")

    # Check budget
    budget = get_budget(session)
    remaining = budget["queries_max"] - budget["queries_used"]
    print(f"Budget: {budget['queries_used']}/{budget['queries_max']} used, {remaining} remaining")

    viewports = plan_viewports(remaining, len(args.seeds))
    total_queries = len(args.seeds) * len(viewports)
    print(f"Plan: {len(args.seeds)} seeds × {len(viewports)} viewports = {total_queries} queries")

    if total_queries > remaining:
        print(f"WARNING: Need {total_queries} queries but only {remaining} remaining!")
        print("Proceeding with available budget...")

    # Create a timestamped run folder
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(SIMULATIONS_DIR, f"{ts}_{round_id[:8]}")
    os.makedirs(run_dir, exist_ok=True)

    results = {}
    query_count = 0

    for seed_idx in args.seeds:
        seed_results = []
        print(f"\n--- Seed {seed_idx} ---")

        for vx, vy, vw, vh in viewports:
            try:
                result = simulate(session, round_id, seed_idx, vx, vy, vw, vh)
                query_count += 1
                seed_results.append({
                    "viewport": {"x": vx, "y": vy, "w": vw, "h": vh},
                    "response": result,
                })
                used = result.get("queries_used", "?")
                max_q = result.get("queries_max", "?")
                print(f"  viewport ({vx},{vy}) {vw}x{vh} -> OK  [{used}/{max_q}]")
                time.sleep(args.delay)

            except requests.HTTPError as e:
                status = e.response.status_code
                print(f"  viewport ({vx},{vy}) {vw}x{vh} -> HTTP {status}: {e.response.text}")
                if status == 429:
                    print("  Budget exhausted or rate limited. Stopping.")
                    break
                continue

        results[seed_idx] = seed_results

        # Save per-seed results
        seed_path = os.path.join(run_dir, f"seed_{seed_idx}.json")
        with open(seed_path, "w") as f:
            json.dump(seed_results, f, indent=2)
        print(f"  Saved {len(seed_results)} viewports to {seed_path}")

    # Save combined summary
    summary = {
        "round_id": round_id,
        "timestamp": ts,
        "seeds": args.seeds,
        "viewports_per_seed": len(viewports),
        "total_queries": query_count,
    }
    summary_path = os.path.join(run_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDone. {query_count} queries executed. Results in {run_dir}")


if __name__ == "__main__":
    main()

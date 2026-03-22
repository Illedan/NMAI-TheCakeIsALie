"""Download replays and analysis for all (or missing) rounds from the Astar Island API."""

import argparse
import json
import os
from time import sleep

import api

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPLAY_DIR = os.path.join(SCRIPT_DIR, "replays")
ANALYSIS_DIR = os.path.join(SCRIPT_DIR, "analysis")
NUM_SEEDS = 5


def _analysis_path(round_number: int, seed: int, round_id: str) -> str:
    return os.path.join(ANALYSIS_DIR, f"round_{round_number}_analysis_seed_{seed}_{round_id}.json")


def _replay_path(round_number: int, seed: int, round_id: str) -> str:
    return os.path.join(REPLAY_DIR, f"round_{round_number}_replay_seed_{seed}_{round_id}.json")


def _round_has_analysis(round_number: int, round_id: str) -> bool:
    return all(
        os.path.isfile(_analysis_path(round_number, s, round_id))
        for s in range(NUM_SEEDS)
    )


def _round_has_replays(round_number: int, round_id: str) -> bool:
    return all(
        os.path.isfile(_replay_path(round_number, s, round_id))
        for s in range(NUM_SEEDS)
    )


def fetch_analysis(round_number: int, round_id: str):
    """Download analysis for all seeds of a round."""
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    for seed in range(NUM_SEEDS):
        out = _analysis_path(round_number, seed, round_id)
        print(f"  Fetching analysis round #{round_number} seed {seed} ...")
        data = api.get_analysis(round_id, seed)
        with open(out, "w") as f:
            json.dump(data, f)
        print(f"    Saved {os.path.basename(out)}")
        sleep(1)


def fetch_replays(round_number: int, round_id: str):
    """Download replays for all seeds of a round."""
    os.makedirs(REPLAY_DIR, exist_ok=True)
    for seed in range(NUM_SEEDS):
        out = _replay_path(round_number, seed, round_id)
        print(f"  Fetching replay round #{round_number} seed {seed} ...")
        resp = api.SESSION.post(f"{api.BASE}/replay", json={"round_id": round_id, "seed_index": seed})
        resp.raise_for_status()
        with open(out, "w") as f:
            json.dump(resp.json(), f)
        print(f"    Saved {os.path.basename(out)}")
        sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Download replays and analysis for all rounds.")
    parser.add_argument("--all", action="store_true", help="Re-download all rounds, not just missing ones")
    parser.add_argument("--analysis-only", action="store_true", help="Only download analysis, skip replays")
    parser.add_argument("--replays-only", action="store_true", help="Only download replays, skip analysis")
    args = parser.parse_args()

    rounds = api.get_rounds()
    # Only completed rounds have analysis/replays available
    completed = [r for r in rounds if r["status"] == "completed"]
    completed.sort(key=lambda r: r["round_number"])

    print(f"Found {len(completed)} completed rounds (of {len(rounds)} total)")

    fetched_count = 0
    for r in completed:
        rn = r["round_number"]
        rid = r["id"]

        need_analysis = not args.replays_only and (args.all or not _round_has_analysis(rn, rid))
        need_replays = not args.analysis_only and (args.all or not _round_has_replays(rn, rid))

        if not need_analysis and not need_replays:
            print(f"Round #{rn} ({rid[:8]}) — already complete, skipping")
            continue

        print(f"Round #{rn} ({rid[:8]}):")

        if need_analysis:
            fetch_analysis(rn, rid)
        if need_replays:
            fetch_replays(rn, rid)

        fetched_count += 1

    print(f"\nDone. Fetched data for {fetched_count} rounds.")


if __name__ == "__main__":
    main()

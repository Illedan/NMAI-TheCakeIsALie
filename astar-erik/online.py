#!/usr/bin/env python3
"""
Online orchestrator for Astar Island C++ solver.

ONE COMMAND to query + solve + submit, bulletproof:
  python3 online.py submit

Safety features:
  - Lock file prevents double runs on same round
  - Budget check aborts if no queries remain
  - Verifies all 5 seeds accepted before finishing
  - All queries go to one tile (multi-viewport doesn't work via pre-fetch)

Other modes:
  python3 online.py dry-run    — show plan without querying
  python3 online.py fetch      — download data for local testing
"""

import argparse
import json
import os
import subprocess
import sys
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
SIMULATIONS_DIR = SCRIPT_DIR / "simulations"
API_BASE = "https://api.ainm.no/astar-island"
LOCK_FILE = SCRIPT_DIR / ".submit.lock"


def load_token():
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found. Create it with ACCESS_TOKEN=...")
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("ACCESS_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: ACCESS_TOKEN not found in .env")
    sys.exit(1)


# ── API Client ─────────────────────────────────────────────────────────────

import urllib.request
import urllib.error


def api_get(path, token):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def api_post(path, data, token, retries=3):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Rate limited (429), retrying in {wait}s... (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                raise


def get_active_round(token):
    rounds = api_get("/rounds", token)
    active = [r for r in rounds if r["status"] == "active"]
    if not active:
        print("No active round found. Available:")
        for r in rounds:
            print(f"  Round #{r['round_number']}: {r['status']}")
        sys.exit(1)
    return active[0]


def get_round_detail(round_id, token):
    return api_get(f"/rounds/{round_id}", token)


def get_budget(token):
    return api_get("/budget", token)


def api_simulate(round_id, seed_index, vx, vy, vw, vh, token):
    return api_post("/simulate", {
        "round_id": round_id,
        "seed_index": seed_index,
        "viewport_x": vx, "viewport_y": vy,
        "viewport_w": vw, "viewport_h": vh,
    }, token)


def submit_prediction(round_id, seed_index, prediction, token):
    return api_post("/submit", {
        "round_id": round_id,
        "seed_index": seed_index,
        "prediction": prediction,
    }, token)


# ── Tile scoring (mirrors C++ logic) ──────────────────────────────────────

TERRAIN_OCEAN = 10
TERRAIN_MOUNTAIN = 5
TERRAIN_SETTLEMENT = 1
TERRAIN_PORT = 2
TERRAIN_FOREST = 4
TERRAIN_RUIN = 3
TERRAIN_PLAINS = 11
TERRAIN_EMPTY = 0
MAX_VIEWPORT = 15


def score_tile(grid, vx, vy, vw, vh):
    H, W = len(grid), len(grid[0])
    score = 0
    ocean_count = 0
    has_coastal = False
    settle_count = 0
    forest_count = 0

    for y in range(vy, min(vy + vh, H)):
        for x in range(vx, min(vx + vw, W)):
            t = grid[y][x]
            if t == TERRAIN_OCEAN:
                ocean_count += 1
                continue
            if t == TERRAIN_MOUNTAIN:
                continue
            if t in (TERRAIN_SETTLEMENT, TERRAIN_PORT):
                settle_count += 1
                score += 3.0
            elif t == TERRAIN_FOREST:
                forest_count += 1
                score += 1.5
            elif t == TERRAIN_RUIN:
                score += 2.0
            else:
                score += 0.5

            if not has_coastal:
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] == TERRAIN_OCEAN:
                            has_coastal = True

    ocean_frac = ocean_count / (vw * vh)
    if ocean_frac > 0.5:
        return 0
    score *= (1.0 - ocean_frac)
    if has_coastal:
        score *= 1.3
    if settle_count > 0 and forest_count > 0:
        score *= 1.2
    return score


def find_best_tile(grid):
    H, W = len(grid), len(grid[0])
    vw = min(MAX_VIEWPORT, W)
    vh = min(MAX_VIEWPORT, H)
    best_score = -1
    bx, by = 0, 0
    for vy in range(H - vh + 1):
        for vx in range(W - vw + 1):
            s = score_tile(grid, vx, vy, vw, vh)
            if s > best_score:
                best_score = s
                bx, by = vx, vy
    return bx, by, vw, vh


# ── Logging helper ─────────────────────────────────────────────────────────

def log(run_dir, msg):
    """Append a timestamped line to run_dir/log.txt and print it."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    log_path = run_dir / "log.txt"
    with open(log_path, "a") as f:
        f.write(line + "\n")


# ── Submit command (THE one command) ──────────────────────────────────────

def cmd_submit(args):
    """Interactive query + solve + submit. C++ decides all query positions.

    Pipeline:
    1. Build binary
    2. Check budget (abort if 0)
    3. Lock file (prevent double run)
    4. Save initial states
    5. Launch C++ --interactive (long-lived process)
    6. C++ requests queries via stdout, Python relays to API, sends responses via stdin
    7. C++ produces predictions for all 5 seeds
    8. Submit all predictions, verify all accepted
    """
    token = load_token()

    # ── Step 0: Build binary ──
    solver_bin = SCRIPT_DIR / "astar"
    print("Building solver...")
    proc = subprocess.run(
        ["make", "-j4"], capture_output=True, text=True,
        cwd=str(SCRIPT_DIR), timeout=60
    )
    if proc.returncode != 0:
        print(f"BUILD FAILED:\n{proc.stderr}")
        sys.exit(1)
    if not solver_bin.exists():
        print(f"ERROR: {solver_bin} not found after build")
        sys.exit(1)
    print("Build OK")

    # ── Step 1: Get round info + budget ──
    if args.round_id:
        round_id = args.round_id
    else:
        active = get_active_round(token)
        round_id = active["id"]

    detail = get_round_detail(round_id, token)
    budget_info = get_budget(token)
    seeds_count = detail["seeds_count"]
    round_num = detail.get("round_number", "?")
    queries_max = budget_info["queries_max"]
    queries_used_api = budget_info["queries_used"]
    remaining = queries_max - queries_used_api

    print(f"\n{'='*60}")
    print(f"Round #{round_num} ({round_id[:8]})")
    print(f"Map: {detail['map_width']}x{detail['map_height']}, {seeds_count} seeds")
    print(f"Budget: {queries_used_api}/{queries_max} used, {remaining} remaining")
    print(f"{'='*60}\n")

    if remaining <= 0:
        print(f"ABORT: No queries remaining ({queries_used_api}/{queries_max} used).")
        sys.exit(1)

    # ── Step 2: Lock file ──
    lock_content = f"{round_id}\n"
    if LOCK_FILE.exists():
        with open(LOCK_FILE) as f:
            existing = f.read().strip()
        if existing == round_id:
            print(f"ABORT: Lock file exists for this round ({round_id[:8]}).")
            print(f"A submission is already in progress or completed.")
            print(f"To force: rm {LOCK_FILE}")
            sys.exit(1)
    with open(LOCK_FILE, "w") as f:
        f.write(lock_content)

    seeds = args.seeds if args.seeds else list(range(seeds_count))

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = SIMULATIONS_DIR / f"{ts}_{round_id[:8]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    log(run_dir, f"Submit: Round #{round_num} ({round_id[:8]})")
    log(run_dir, f"Budget: {queries_used_api}/{queries_max} used, {remaining} remaining")

    # ── Step 3: Save initial states ──
    query_seed = seeds[0]
    for seed_idx in seeds:
        initial = detail["initial_states"][seed_idx]
        with open(run_dir / f"seed_{seed_idx}_initial.json", "w") as f:
            json.dump(initial, f)

    # ── Step 4: Launch C++ --interactive ──
    log(run_dir, f"Launching C++ interactive solver...")
    solver_proc = subprocess.Popen(
        [str(solver_bin), "--interactive", str(run_dir), str(seeds_count)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )

    # ── Step 5: Handle interactive protocol ──
    query_results = []  # Save all query results for local testing
    queries_done = 0
    predictions_received = set()

    import threading, io

    # Read stderr in background thread (for logging)
    stderr_lines = []
    def read_stderr():
        for line in solver_proc.stderr:
            line = line.rstrip()
            if line:
                stderr_lines.append(line)
                log(run_dir, f"  C++ > {line}")
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    try:
        while True:
            line = solver_proc.stdout.readline()
            if not line:
                # Process ended
                break
            line = line.strip()

            if line.startswith("QUERY "):
                # Parse: QUERY vx vy vw vh
                parts = line.split()
                vx, vy, vw, vh = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])

                if queries_done >= remaining:
                    log(run_dir, f"  Budget exhausted ({queries_done}/{remaining}), sending empty response")
                    solver_proc.stdin.write('{"grid":[]}\n')
                    solver_proc.stdin.flush()
                    continue

                # Query API
                try:
                    result = api_simulate(round_id, query_seed, vx, vy, vw, vh, token)
                    queries_done += 1

                    query_results.append({
                        "viewport": {"x": vx, "y": vy, "w": vw, "h": vh},
                        "response": result,
                    })

                    api_used = result.get("queries_used", "?")
                    api_max = result.get("queries_max", "?")
                    log(run_dir, f"  Query {queries_done}/{remaining}: ({vx},{vy}) {vw}x{vh} [API: {api_used}/{api_max}]")

                    # Send response to C++ (grid only, one line)
                    response_json = json.dumps({"grid": result["grid"]})
                    solver_proc.stdin.write(response_json + "\n")
                    solver_proc.stdin.flush()

                    time.sleep(0.22)  # Rate limit
                except urllib.error.HTTPError as e:
                    log(run_dir, f"  Query FAILED: HTTP {e.code}")
                    if e.code == 429:
                        log(run_dir, "  Rate limited, waiting 5s...")
                        time.sleep(5)
                        try:
                            result = api_simulate(round_id, query_seed, vx, vy, vw, vh, token)
                            queries_done += 1
                            query_results.append({
                                "viewport": {"x": vx, "y": vy, "w": vw, "h": vh},
                                "response": result,
                            })
                            solver_proc.stdin.write(json.dumps({"grid": result["grid"]}) + "\n")
                            solver_proc.stdin.flush()
                            log(run_dir, f"  Retry OK")
                        except Exception:
                            log(run_dir, "  Retry failed, sending empty")
                            solver_proc.stdin.write('{"grid":[]}\n')
                            solver_proc.stdin.flush()
                    else:
                        solver_proc.stdin.write('{"grid":[]}\n')
                        solver_proc.stdin.flush()

            elif line.startswith("PREDICT "):
                seed_idx = int(line.split()[1])
                predictions_received.add(seed_idx)
                log(run_dir, f"  Prediction ready for seed {seed_idx}")

            elif line == "DONE":
                log(run_dir, f"  C++ solver finished")
                break

    except Exception as e:
        log(run_dir, f"ERROR during interactive solve: {e}")
        solver_proc.kill()
        LOCK_FILE.unlink(missing_ok=True)
        sys.exit(1)

    # Wait for process to finish
    solver_proc.wait(timeout=10)
    stderr_thread.join(timeout=5)

    if solver_proc.returncode != 0:
        log(run_dir, f"C++ exited with code {solver_proc.returncode}")

    log(run_dir, f"Total queries: {queries_done}")
    log(run_dir, f"Predictions: {sorted(predictions_received)}")

    # Save query results for local testing
    with open(run_dir / f"seed_{query_seed}.json", "w") as f:
        json.dump(query_results, f, indent=2)

    # ── Step 6: Submit predictions ──
    log(run_dir, f"")
    log(run_dir, f"=== Submitting {len(seeds)} predictions ===")

    submit_results = {}
    for seed_idx in seeds:
        prediction_path = run_dir / f"seed_{seed_idx}_prediction.json"
        if not prediction_path.exists():
            log(run_dir, f"  Seed {seed_idx}: NO PREDICTION FILE")
            continue

        with open(prediction_path) as f:
            prediction = json.load(f)

        if len(prediction) != detail["map_height"]:
            log(run_dir, f"  Seed {seed_idx}: BAD SIZE {len(prediction)} != {detail['map_height']}")
            continue

        # Verify probabilities sum to ~1 for a sample cell
        sample = prediction[detail["map_height"]//2][detail["map_width"]//2]
        psum = sum(sample)
        if abs(psum - 1.0) > 0.01:
            log(run_dir, f"  Seed {seed_idx}: WARNING prob sum={psum:.4f}")

        log(run_dir, f"  Submitting seed {seed_idx}...")
        for attempt in range(3):
            try:
                result = submit_prediction(round_id, seed_idx, prediction, token)
                status = result.get("status", "unknown")
                log(run_dir, f"  Seed {seed_idx}: {status}")
                submit_results[seed_idx] = result
                with open(run_dir / f"seed_{seed_idx}_submit.json", "w") as f:
                    json.dump(result, f, indent=2)
                break
            except urllib.error.HTTPError as e:
                body = e.read().decode() if hasattr(e, 'read') else str(e)
                log(run_dir, f"  Submit FAILED (attempt {attempt+1}/3): HTTP {e.code}: {body[:200]}")
                if attempt < 2:
                    time.sleep(3)
                else:
                    log(run_dir, f"  GIVING UP on seed {seed_idx}")
        time.sleep(0.5)

    # ── Step 7: Verify ──
    log(run_dir, f"")
    log(run_dir, f"=== Verification ===")
    all_ok = True
    for seed_idx in seeds:
        if seed_idx in submit_results:
            status = submit_results[seed_idx].get("status", "unknown")
            symbol = "OK" if status == "accepted" else f"WARN ({status})"
            log(run_dir, f"  Seed {seed_idx}: {symbol}")
            if status != "accepted":
                all_ok = False
        else:
            log(run_dir, f"  Seed {seed_idx}: MISSING - not submitted!")
            all_ok = False

    if all_ok:
        log(run_dir, f"ALL {len(seeds)} SEEDS ACCEPTED")
    else:
        log(run_dir, f"WARNING: Some seeds failed!")

    # ── Step 8: Save for local testing ──
    _save_for_local_testing(run_dir, detail, seeds, query_seed, query_results, round_id, round_num)

    summary = {
        "round_id": round_id,
        "round_number": round_num,
        "timestamp": ts,
        "mode": "interactive-submit",
        "seeds": seeds,
        "query_seed": query_seed,
        "queries_done": queries_done,
        "predictions_received": sorted(predictions_received),
        "all_accepted": all_ok,
        "completed_at": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    log(run_dir, f"")
    log(run_dir, f"Done. Data in {run_dir}")


def _save_for_local_testing(run_dir, detail, seeds, query_seed, seed_results, round_id, round_num):
    """Copy data to astar-island/ and predictions/ for local testing."""
    import shutil

    # predictions/ directory
    pred_dir = SCRIPT_DIR / "predictions" / f"round{round_num}_{round_id[:8]}"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for seed_idx in seeds:
        for suffix in ["_prediction.json", "_submit.json", "_initial.json"]:
            src = run_dir / f"seed_{seed_idx}{suffix}"
            if src.exists():
                shutil.copy(str(src), str(pred_dir / src.name))
    for fname in ["summary.json", "log.txt", "shared_correction.txt", f"seed_{query_seed}.json"]:
        src = run_dir / fname
        if src.exists():
            shutil.copy(str(src), str(pred_dir / fname))

    # astar-island/ directory (for local replay testing)
    island = REPO_ROOT / "astar-island"
    ts_dir = run_dir.name

    island_is = island / "initial_states" / ts_dir
    island_is.mkdir(parents=True, exist_ok=True)
    for seed_idx in seeds:
        src = run_dir / f"seed_{seed_idx}_initial.json"
        if src.exists():
            shutil.copy(str(src), str(island_is / f"seed_{seed_idx}.json"))
    island_summary = {
        "round_id": round_id,
        "round_number": round_num,
        "status": "active",
        "map_width": detail["map_width"],
        "map_height": detail["map_height"],
        "seeds_count": detail["seeds_count"],
        "timestamp": ts_dir[:15],
    }
    with open(island_is / "summary.json", "w") as f:
        json.dump(island_summary, f, indent=2)

    island_sim = island / "simulations" / ts_dir
    island_sim.mkdir(parents=True, exist_ok=True)
    qsrc = run_dir / f"seed_{query_seed}.json"
    if qsrc.exists():
        shutil.copy(str(qsrc), str(island_sim / f"seed_{query_seed}.json"))
    sim_summary = {
        "round_id": round_id[:8],
        "timestamp": ts_dir[:15],
        "seeds": [query_seed],
        "viewports_per_seed": len(seed_results),
        "total_queries": len(seed_results),
    }
    with open(island_sim / "summary.json", "w") as f:
        json.dump(sim_summary, f, indent=2)


# ── Dry-run command ──────────────────────────────────────────────────────

def cmd_dryrun(args):
    """Fetch map, show plan, don't query."""
    token = load_token()

    if args.round_id:
        round_id = args.round_id
    else:
        active = get_active_round(token)
        round_id = active["id"]

    detail = get_round_detail(round_id, token)
    budget_info = get_budget(token)
    round_num = detail.get("round_number", "?")
    remaining = budget_info["queries_max"] - budget_info["queries_used"]

    print(f"\nRound #{round_num} ({round_id[:8]})")
    print(f"Map: {detail['map_width']}x{detail['map_height']}, {detail['seeds_count']} seeds")
    print(f"Budget: {remaining} queries remaining\n")

    for seed_idx in range(detail["seeds_count"]):
        grid = detail["initial_states"][seed_idx]["grid"]
        tx, ty, tw, th = find_best_tile(grid)
        score = score_tile(grid, tx, ty, tw, th)
        print(f"  Seed {seed_idx}: best tile ({tx},{ty}) {tw}x{th} score={score:.1f}")


# ── Fetch command ──────────────────────────────────────────────────────────

def cmd_fetch(args):
    """Download data for all rounds to astar-island/."""
    token = load_token()
    island = REPO_ROOT / "astar-island"
    is_dir = island / "initial_states"
    analysis_dir = island / "analysis"
    is_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    rounds = api_get("/rounds", token)
    rounds.sort(key=lambda r: r.get("round_number", 0))

    existing_ids = set()
    if is_dir.exists():
        for d in is_dir.iterdir():
            if d.is_dir():
                summary = d / "summary.json"
                if summary.exists():
                    with open(summary) as f:
                        s = json.load(f)
                    existing_ids.add(s.get("round_id", "")[:8])

    for r in rounds:
        rid = r["id"]
        rnum = r["round_number"]
        status = r["status"]
        short = rid[:8]

        has_is = short in existing_ids
        has_analysis = any(analysis_dir.glob(f"*{rid}*"))

        if has_is and (has_analysis or status not in ("completed", "scoring")):
            print(f"  Round {rnum} ({short}): OK (status={status})")
            continue

        if not has_is:
            print(f"  Round {rnum} ({short}): fetching initial states...")
            detail = get_round_detail(rid, token)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            rd = is_dir / f"{ts}_{short}"
            rd.mkdir(parents=True, exist_ok=True)
            for i, state in enumerate(detail["initial_states"]):
                with open(rd / f"seed_{i}.json", "w") as f:
                    json.dump(state, f)
            summary = {
                "round_id": rid,
                "round_number": rnum,
                "status": status,
                "map_width": r["map_width"],
                "map_height": r["map_height"],
                "seeds_count": detail["seeds_count"],
                "timestamp": ts,
            }
            with open(rd / "summary.json", "w") as f:
                json.dump(summary, f, indent=2)
            print(f"    Saved {detail['seeds_count']} seeds")

        if not has_analysis and status in ("completed", "scoring"):
            print(f"  Round {rnum} ({short}): fetching analysis...")
            if has_is:
                detail = get_round_detail(rid, token)
            ts_short = datetime.now(timezone.utc).strftime("%m_%d_%H")
            for seed in range(detail["seeds_count"]):
                fname = f"{ts_short}_analysis_seed_{seed}_{rid}.json"
                try:
                    data = api_get(f"/analysis/{rid}/{seed}", token)
                    with open(analysis_dir / fname, "w") as f:
                        json.dump(data, f)
                    print(f"    Seed {seed}: score={data.get('score', '?')}")
                except urllib.error.HTTPError as e:
                    print(f"    Seed {seed}: failed (HTTP {e.code})")

    print("\nDone. Run ./astar to test locally.")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Astar Island online solver")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    dry = subparsers.add_parser("dry-run", help="Show query plan without querying")
    dry.add_argument("--round-id", type=str, default=None)

    sub = subparsers.add_parser("submit", help="Query + Solve + Submit (one command)")
    sub.add_argument("--round-id", type=str, default=None)
    sub.add_argument("--seeds", type=int, nargs="+", default=None)
    sub.add_argument("--force", action="store_true", help="Ignore lock file")

    fetch = subparsers.add_parser("fetch", help="Download data for local testing")

    args = parser.parse_args()

    if args.mode == "dry-run":
        cmd_dryrun(args)
    elif args.mode == "submit":
        if hasattr(args, 'force') and args.force and LOCK_FILE.exists():
            LOCK_FILE.unlink()
        cmd_submit(args)
    elif args.mode == "fetch":
        cmd_fetch(args)


if __name__ == "__main__":
    main()

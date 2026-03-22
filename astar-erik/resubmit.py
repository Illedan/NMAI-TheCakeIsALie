#!/usr/bin/env python3
"""Resubmit predictions for a round using stored query responses.
Does NOT make new API queries — replays cached data from previous submit.

Usage: python3 resubmit.py <round_dir>
Example: python3 resubmit.py predictions/round22_a8be24e1
"""
import json
import subprocess
import sys
import os
import urllib.request
import time

BASE_URL = "https://api.ainm.no/astar-island"

def api_post(endpoint, data, token):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, json.dumps(data).encode(), {
        "Content-Type": "application/json",
        "Cookie": f"access_token={token}",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 resubmit.py <round_dir> [--dry-run]")
        sys.exit(1)

    run_dir = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    # Get token from environment or cookie
    token = os.environ.get("ASTAR_TOKEN", "")
    if not token:
        # Try to read from online.py's default location
        token_file = os.path.expanduser("~/.ainm_token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                token = f.read().strip()

    # Parse round_id from directory name
    dirname = os.path.basename(run_dir)
    parts = dirname.split("_")
    round_id_short = parts[-1] if len(parts) > 1 else parts[0]

    # Load stored query responses
    query_file = os.path.join(run_dir, "seed_0.json")
    if not os.path.exists(query_file):
        print(f"ERROR: No stored queries at {query_file}")
        sys.exit(1)

    with open(query_file) as f:
        query_results = json.load(f)
    print(f"Loaded {len(query_results)} stored queries from {query_file}")

    # Count seeds by checking initial state files
    seeds = []
    for i in range(5):
        if os.path.exists(os.path.join(run_dir, f"seed_{i}_initial.json")):
            seeds.append(i)
    print(f"Found {len(seeds)} seeds: {seeds}")

    # Rebuild C++
    print("Building C++...")
    r = subprocess.run(["make"], cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Build failed:\n{r.stderr}")
        sys.exit(1)
    print("Build OK")

    # Launch C++ interactive solver
    solver_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "astar")
    abs_run_dir = os.path.abspath(run_dir)

    print(f"Launching C++ solver: {solver_bin} --interactive {abs_run_dir} {len(seeds)}")
    proc = subprocess.Popen(
        [solver_bin, "--interactive", abs_run_dir, str(max(seeds) + 1)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Read stderr in background
    import threading
    stderr_lines = []
    def read_stderr():
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                stderr_lines.append(line)
                print(f"  C++ > {line}", file=sys.stderr)
    t = threading.Thread(target=read_stderr, daemon=True)
    t.start()

    # Replay queries
    query_idx = 0
    predictions_received = set()

    try:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()

            if line.startswith("QUERY "):
                parts = line.split()
                vx, vy, vw, vh = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])

                if query_idx < len(query_results):
                    stored = query_results[query_idx]
                    stored_vp = stored["viewport"]
                    response_grid = stored["response"]["grid"]
                    # Send stored viewport position so C++ uses correct coordinates
                    response_obj = {
                        "grid": response_grid,
                        "vx": stored_vp["x"],
                        "vy": stored_vp["y"],
                        "vw": stored_vp.get("w", stored_vp.get("width", 15)),
                        "vh": stored_vp.get("h", stored_vp.get("height", 15)),
                    }
                    response_json = json.dumps(response_obj)
                    proc.stdin.write(response_json + "\n")
                    proc.stdin.flush()
                    mismatch = " MISMATCH!" if (vx != stored_vp["x"] or vy != stored_vp["y"]) else ""
                    print(f"  Replayed query {query_idx+1}/{len(query_results)}: "
                          f"asked=({vx},{vy}) stored=({stored_vp['x']},{stored_vp['y']}){mismatch}")
                    query_idx += 1
                else:
                    print(f"  No more stored queries, sending empty")
                    proc.stdin.write('{"grid":[]}\n')
                    proc.stdin.flush()

            elif line.startswith("PREDICT "):
                seed_idx = int(line.split()[1])
                predictions_received.add(seed_idx)
                print(f"  Prediction ready for seed {seed_idx}")

            elif line == "DONE":
                print("  C++ solver finished")
                break

    except Exception as e:
        print(f"ERROR: {e}")
        proc.kill()
        sys.exit(1)

    proc.wait(timeout=10)
    t.join(timeout=5)

    print(f"\nPredictions generated for seeds: {sorted(predictions_received)}")

    if dry_run:
        print("\n[DRY RUN] Would submit but skipping.")
        # Show diff with old predictions
        for seed_idx in sorted(predictions_received):
            old_path = os.path.join(run_dir, f"seed_{seed_idx}_prediction.json")
            new_path = os.path.join(abs_run_dir, f"seed_{seed_idx}_prediction.json")
            if os.path.exists(old_path) and os.path.exists(new_path):
                with open(old_path) as f:
                    old = json.load(f)
                with open(new_path) as f:
                    new = json.load(f)
                # Compare
                max_diff = 0
                for y in range(len(old)):
                    for x in range(len(old[0])):
                        for c in range(6):
                            d = abs(old[y][x][c] - new[y][x][c])
                            max_diff = max(max_diff, d)
                print(f"  Seed {seed_idx}: max prob diff = {max_diff:.6f}")
        return

    if not token:
        print("ERROR: No API token. Set ASTAR_TOKEN env var or create ~/.ainm_token")
        sys.exit(1)

    # Find full round_id from stored submit result
    for seed_idx in seeds:
        submit_file = os.path.join(run_dir, f"seed_{seed_idx}_submit.json")
        if os.path.exists(submit_file):
            with open(submit_file) as f:
                submit_data = json.load(f)
            if "round_id" in submit_data:
                full_round_id = submit_data["round_id"]
                break
    else:
        print("ERROR: Cannot find full round_id from stored submit results")
        sys.exit(1)

    print(f"\nSubmitting to round {full_round_id[:8]}...")
    for seed_idx in sorted(predictions_received):
        pred_path = os.path.join(abs_run_dir, f"seed_{seed_idx}_prediction.json")
        with open(pred_path) as f:
            prediction = json.load(f)

        print(f"  Submitting seed {seed_idx}...", end=" ")
        try:
            result = api_post("/submit", {
                "round_id": full_round_id,
                "seed_index": seed_idx,
                "prediction": prediction,
            }, token)
            status = result.get("status", "unknown")
            print(status)
            # Save updated submit result
            with open(os.path.join(run_dir, f"seed_{seed_idx}_submit.json"), "w") as f:
                json.dump(result, f, indent=2)
        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, 'read') else str(e)
            print(f"FAILED: HTTP {e.code}: {body[:200]}")
        time.sleep(0.5)

    print("\nDone!")


if __name__ == "__main__":
    main()

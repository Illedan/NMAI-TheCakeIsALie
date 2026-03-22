#!/usr/bin/env python3
"""Download 30 replays for each of 12 rounds that have 0 replays."""

import json
import os
import sys
import time
import urllib.request

BASE_URL = "https://api.ainm.no/astar-island"

# Read token from secrets.py
secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.py")
with open(secrets_path) as f:
    for line in f:
        if "ACCESS_TOKEN" in line:
            TOKEN = line.split('"')[1]
            break

SIM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulations")

# (directory_name, full_round_uuid)
ROUNDS = [
    ("20260319_233710_76909e29", "76909e29-f664-4b2f-b16b-61b7507277e9"),
    ("20260320_010821_f1dac9a9", "f1dac9a9-5cf1-49a9-8f17-d6cb5d5ba5cb"),
    ("20260320_075609_fd3c92ff", "fd3c92ff-3178-4dc9-8d9b-acf389b3982b"),
    ("20260320_103614_ae78003a", "ae78003a-4efe-425a-881a-d16a39bca0ad"),
    ("20260320_174421_c5cdf100", "c5cdf100-a876-4fb7-b5d8-757162c97989"),
    ("20260320_204043_2a341ace", "2a341ace-0f57-4309-9b89-e59fe0f09179"),
    ("20260320_232944_75e625c3", "75e625c3-60cb-4392-af3e-c86a98bde8c2"),
    ("20260321_023201_324fde07", "324fde07-1670-4202-b199-7aa92ecb40ee"),
    ("20260321_085513_7b4bda99", "7b4bda99-6165-4221-97cc-27880f5e6d95"),
    ("20260321_115322_d0a2c894", "d0a2c894-2162-4d49-86cf-435b9013f3b8"),
    ("20260321_143924_cc5442dd", "cc5442dd-bc5d-418b-911b-7eb960cb0390"),
    ("20260321_173223_8f664aed", "8f664aed-8839-4c85-bed0-77a2cac7c6f5"),
]

REPLAYS_PER_ROUND = 30
TOTAL = len(ROUNDS) * REPLAYS_PER_ROUND
downloaded = 0
skipped = 0
failed = 0


def post_replay(round_id, seed_index=0):
    """POST to /replay endpoint and return parsed JSON or None."""
    url = f"{BASE_URL}/replay"
    data = json.dumps({"round_id": round_id, "seed_index": seed_index}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
            return json.loads(body), len(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"_error": e.code, "_body": body}, 0
    except Exception as e:
        return {"_error": str(e)}, 0


print(f"=== Replay Download Script ===")
print(f"Rounds: {len(ROUNDS)} | Replays/round: {REPLAYS_PER_ROUND} | Total: {TOTAL}")
print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(flush=True)

for dir_name, round_id in ROUNDS:
    replay_dir = os.path.join(SIM_DIR, dir_name, "replays")
    os.makedirs(replay_dir, exist_ok=True)

    print(f"\n{'─' * 50}")
    print(f"Round: {round_id[:8]} (dir: {dir_name})")

    # Collect existing sim_seeds
    seen_seeds = set()
    existing_files = sorted([
        f for f in os.listdir(replay_dir)
        if f.startswith("seed_0_replay_") and f.endswith(".json")
    ]) if os.path.exists(replay_dir) else []

    for ef in existing_files:
        try:
            with open(os.path.join(replay_dir, ef)) as fh:
                d = json.load(fh)
                if "sim_seed" in d:
                    seen_seeds.add(d["sim_seed"])
        except Exception:
            pass

    existing_count = len(existing_files)
    if existing_count >= REPLAYS_PER_ROUND:
        print(f"  Already have {existing_count} replays, skipping")
        skipped += REPLAYS_PER_ROUND
        continue

    if seen_seeds:
        print(f"  Found {len(seen_seeds)} existing unique seeds")

    n = existing_count
    attempts = 0
    max_attempts = REPLAYS_PER_ROUND * 4  # Allow retries for duplicates + errors

    while n < REPLAYS_PER_ROUND and attempts < max_attempts:
        attempts += 1
        out_file = os.path.join(replay_dir, f"seed_0_replay_{n}.json")

        data, body_size = post_replay(round_id, seed_index=0)

        # Check for errors
        if "_error" in data:
            error_code = data["_error"]
            error_body = data.get("_body", "")
            if "rate" in str(error_body).lower() or "Rate limit" in str(error_body) or error_code == 429:
                print(f"  Rate limited, waiting 10s...", flush=True)
                time.sleep(10)
                continue
            if "detail" in str(error_body).lower():
                print(f"  Error (detail): {error_body[:100]}", flush=True)
                time.sleep(10)
                continue
            print(f"  Error: {error_code} - {error_body[:100]}", flush=True)
            failed += 1
            time.sleep(5)
            continue

        # Validate required keys
        if "frames" not in data or "sim_seed" not in data:
            print(f"  Invalid response (missing keys: {list(data.keys())[:5]})", flush=True)
            failed += 1
            time.sleep(5)
            continue

        # Check size
        if body_size < 500:
            print(f"  Response too small ({body_size}B)", flush=True)
            failed += 1
            time.sleep(5)
            continue

        sim_seed = data["sim_seed"]

        # Check for duplicate
        if sim_seed in seen_seeds:
            print(f"  ~ Duplicate sim_seed={sim_seed}, retrying...", flush=True)
            time.sleep(5)
            continue

        # Save
        with open(out_file, "w") as fh:
            json.dump(data, fh)
        seen_seeds.add(sim_seed)
        downloaded += 1
        progress = downloaded + skipped
        print(f"  + Replay {n} (seed={sim_seed}) [{progress}/{TOTAL}]", flush=True)
        n += 1

        if n < REPLAYS_PER_ROUND:
            time.sleep(5)

    print(f"  Round done: {n} replays, {len(seen_seeds)} unique seeds", flush=True)
    time.sleep(2)

print()
print("=== DONE ===")
print(f"Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}")
print(f"Finished at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

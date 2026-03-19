"""Download replays for each seed index from the Astar Island API."""

import json
import os
import numpy as np
import requests
from secrets import ACCESS_TOKEN
from datetime import datetime
from time import sleep

BASE_URL = "https://api.ainm.no/astar-island"
ROUND_ID = "71451d74-be9f-471f-aacd-a41f3b68a9cd"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREFIX = datetime.now().strftime("%m_%d_%H")
REPLAY_DIR = os.path.join(SCRIPT_DIR, "replays")
ANALYSIS_DIR = os.path.join(SCRIPT_DIR, "analysis")
HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


def get_ground_truth():
    os.makedirs(ANALYSIS_DIR, exist_ok=True)

    for idx in range(0, 5):
        out_path = os.path.join(ANALYSIS_DIR, f"{PREFIX}_analysis_seed_{idx}_{ROUND_ID}.json")
        url = f"{BASE_URL}/analysis/{ROUND_ID}/{idx}"

        print(f"Fetching ground truth seed_index={idx} ...")
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        with open(out_path, "w") as f:
            json.dump(resp.json(), f)
        print(f"  Saved to {out_path}")
        sleep(1)

def get_replays():
    os.makedirs(REPLAY_DIR, exist_ok=True)

    for idx in range(0, 5):
        payload = {"round_id": ROUND_ID, "seed_index": idx}
        out_path = os.path.join(REPLAY_DIR, f"{PREFIX}_replay_seed_{idx}_{ROUND_ID}.json")

        print(f"Downloading replay seed_index={idx} ...")
        resp = requests.post(f"{BASE_URL}/replay", json=payload, headers=HEADERS)
        resp.raise_for_status()
        with open(out_path, "w") as f:
            json.dump(resp.json(), f)
        print(f"  Saved to {out_path}")
        sleep(1)

    print("Done.")


if __name__ == "__main__":
    get_ground_truth()
    get_replays()

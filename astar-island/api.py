"""Astar Island API client — all endpoints from the specification."""

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

"""Analyze cell transitions across all replays.

For every source cell type, compute:
  - What it can transform into (and with what probability)
  - How distance to nearest cell of each type affects transitions
  - Spread probability grids: P(new_class | manhattan_distance, source_class)

Saves results to analysis_results/transitions.json
"""

import json
import os
import glob
import numpy as np
from collections import defaultdict

REPLAYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replays")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_results")

TERRAIN_NAMES = {
    0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin",
    4: "Forest", 5: "Mountain", 10: "Ocean", 11: "Plains",
}

ALL_TYPES = [0, 1, 2, 3, 4, 5, 10, 11]
MAX_DIST = 40  # max manhattan distance on a 40x40 grid


def load_all_replays():
    files = sorted(glob.glob(os.path.join(REPLAYS_DIR, "*_replay_*.json")))
    replays = []
    for f in files:
        with open(f) as fh:
            replays.append(json.load(fh))
    print(f"Loaded {len(replays)} replays")
    return replays


def compute_distance_map(grid, target_types):
    """Compute manhattan distance from each cell to nearest cell of target_types."""
    h, w = len(grid), len(grid[0])
    dist = np.full((h, w), MAX_DIST + 1, dtype=int)

    # BFS from all target cells
    queue = []
    for y in range(h):
        for x in range(w):
            if grid[y][x] in target_types:
                dist[y, x] = 0
                queue.append((y, x))

    head = 0
    while head < len(queue):
        cy, cx = queue[head]
        head += 1
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and dist[ny, nx] > dist[cy, cx] + 1:
                dist[ny, nx] = dist[cy, cx] + 1
                queue.append((ny, nx))

    return dist


def analyze_replays(replays):
    # Track: for each (old_type, new_type), count occurrences
    transition_counts = defaultdict(int)
    # Track: total cells of each type that stayed or changed
    type_totals = defaultdict(int)

    # Track: for each source_type that appeared (new cell),
    # what was the distance to nearest cell of each type in the PREVIOUS frame?
    # spread_counts[appeared_type][neighbor_type][distance] += 1
    spread_counts = defaultdict(lambda: defaultdict(lambda: np.zeros(MAX_DIST + 1, dtype=int)))
    # Also track the baseline: for cells that did NOT change to appeared_type
    no_spread_counts = defaultdict(lambda: defaultdict(lambda: np.zeros(MAX_DIST + 1, dtype=int)))

    # Track settlement properties at transition time
    settlement_transitions = []

    total_frames = 0

    for replay_idx, replay in enumerate(replays):
        frames = replay["frames"]
        w, h = replay["width"], replay["height"]
        round_id = replay["round_id"][:8]
        seed = replay["seed_index"]

        print(f"  Replay {replay_idx}: round={round_id} seed={seed}, {len(frames)} frames")

        for fi in range(len(frames) - 1):
            total_frames += 1
            frame_before = frames[fi]
            frame_after = frames[fi + 1]
            grid_before = frame_before["grid"]
            grid_after = frame_after["grid"]

            # Build settlement lookup for before frame
            settlements_before = {}
            for s in frame_before["settlements"]:
                settlements_before[(s["x"], s["y"])] = s

            # Precompute distance maps for key types in the before frame
            dist_maps = {}
            for t in [1, 2, 3, 4, 5, 10, 11]:
                target = {t}
                if t == 1:
                    target = {1}  # settlement only
                elif t == 2:
                    target = {2}  # port only
                dist_maps[t] = compute_distance_map(grid_before, target)

            # Also compute distance to alive settlements and alive ports
            alive_settlement_cells = set()
            alive_port_cells = set()
            for s in frame_before["settlements"]:
                if s["alive"]:
                    if s["has_port"] or grid_before[s["y"]][s["x"]] == 2:
                        alive_port_cells.add((s["y"], s["x"]))
                    else:
                        alive_settlement_cells.add((s["y"], s["x"]))
            # Distance to any alive settlement/port
            dist_alive_settle = np.full((h, w), MAX_DIST + 1, dtype=int)
            dist_alive_port = np.full((h, w), MAX_DIST + 1, dtype=int)
            queue = []
            for (cy, cx) in alive_settlement_cells:
                dist_alive_settle[cy, cx] = 0
                queue.append((cy, cx))
            head = 0
            while head < len(queue):
                cy, cx = queue[head]; head += 1
                for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny, nx = cy+dy, cx+dx
                    if 0<=ny<h and 0<=nx<w and dist_alive_settle[ny,nx] > dist_alive_settle[cy,cx]+1:
                        dist_alive_settle[ny,nx] = dist_alive_settle[cy,cx]+1
                        queue.append((ny,nx))

            queue = []
            for (cy, cx) in alive_port_cells:
                dist_alive_port[cy, cx] = 0
                queue.append((cy, cx))
            head = 0
            while head < len(queue):
                cy, cx = queue[head]; head += 1
                for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny, nx = cy+dy, cx+dx
                    if 0<=ny<h and 0<=nx<w and dist_alive_port[ny,nx] > dist_alive_port[cy,cx]+1:
                        dist_alive_port[ny,nx] = dist_alive_port[cy,cx]+1
                        queue.append((ny,nx))

            # Analyze each cell
            for y in range(h):
                for x in range(w):
                    old_val = grid_before[y][x]
                    new_val = grid_after[y][x]

                    type_totals[old_val] += 1
                    transition_counts[(old_val, new_val)] += 1

                    if old_val != new_val:
                        # Record distances to each type for cells that changed
                        for t in dist_maps:
                            d = int(dist_maps[t][y, x])
                            if d <= MAX_DIST:
                                spread_counts[new_val][t][d] += 1

                        # Also record alive settlement/port distances
                        d_s = int(dist_alive_settle[y, x])
                        d_p = int(dist_alive_port[y, x])
                        if d_s <= MAX_DIST:
                            spread_counts[new_val]["alive_settlement"][d_s] += 1
                        if d_p <= MAX_DIST:
                            spread_counts[new_val]["alive_port"][d_p] += 1

                        # Record settlement properties if a settlement changed
                        s = settlements_before.get((x, y))
                        if s:
                            settlement_transitions.append({
                                "from": old_val, "to": new_val,
                                "step": frame_before["step"],
                                **{k: s[k] for k in ["population", "food", "wealth", "defense", "has_port", "alive", "owner_id"]},
                            })

    print(f"\nProcessed {total_frames} frame transitions across {len(replays)} replays")
    return transition_counts, type_totals, spread_counts, settlement_transitions


def build_results(transition_counts, type_totals, spread_counts, settlement_transitions):
    results = {}

    # 1. Transition matrix: P(new_type | old_type)
    print("\n=== Transition Probabilities ===")
    transition_matrix = {}
    for old_type in ALL_TYPES:
        total = type_totals.get(old_type, 0)
        if total == 0:
            continue
        row = {}
        for new_type in ALL_TYPES:
            count = transition_counts.get((old_type, new_type), 0)
            if count > 0:
                prob = count / total
                row[str(new_type)] = {"count": count, "probability": round(prob, 8)}
        transition_matrix[str(old_type)] = {"total": total, "transitions": row}

        # Print summary
        name = TERRAIN_NAMES.get(old_type, str(old_type))
        print(f"\n  {name} ({old_type}): {total} observations")
        for new_type in ALL_TYPES:
            count = transition_counts.get((old_type, new_type), 0)
            if count > 0 and old_type != new_type:
                prob = count / total
                new_name = TERRAIN_NAMES.get(new_type, str(new_type))
                print(f"    → {new_name} ({new_type}): {count} ({prob:.6f})")

    results["transition_matrix"] = transition_matrix

    # 2. Spread probability grids: P(appeared_as_class | distance_to_source_class)
    print("\n=== Spread Distances ===")
    spread_grids = {}
    for appeared_type in sorted(spread_counts.keys(), key=lambda x: str(x)):
        appeared_name = TERRAIN_NAMES.get(appeared_type, str(appeared_type))
        grid = {}
        print(f"\n  New {appeared_name} ({appeared_type}) appeared near:")
        for source_type in sorted(spread_counts[appeared_type].keys(), key=lambda x: str(x)):
            counts = spread_counts[appeared_type][source_type]
            total = int(counts.sum())
            if total == 0:
                continue

            source_name = TERRAIN_NAMES.get(source_type, str(source_type))
            # Find the distribution
            nonzero = np.nonzero(counts)[0]
            if len(nonzero) == 0:
                continue

            min_d, max_d = int(nonzero[0]), int(nonzero[-1])
            mean_d = float(np.average(np.arange(len(counts)), weights=counts))
            median_idx = np.searchsorted(np.cumsum(counts), total / 2)

            dist_list = {str(d): int(counts[d]) for d in range(min(max_d + 1, MAX_DIST + 1)) if counts[d] > 0}

            grid[str(source_type)] = {
                "total": total,
                "min_distance": min_d,
                "max_distance": max_d,
                "mean_distance": round(mean_d, 2),
                "median_distance": int(median_idx),
                "counts_by_distance": dist_list,
            }

            print(f"    {source_name} ({source_type}): n={total}, "
                  f"dist=[{min_d}, {max_d}], mean={mean_d:.1f}, median={median_idx}")
            # Show top distances
            top_dists = sorted(dist_list.items(), key=lambda x: -x[1])[:5]
            for d, c in top_dists:
                print(f"      d={d}: {c} ({c/total:.3f})")

        spread_grids[str(appeared_type)] = grid

    results["spread_grids"] = spread_grids

    # 3. Settlement property stats at transition time
    print(f"\n=== Settlement Transitions: {len(settlement_transitions)} events ===")
    settle_trans_summary = defaultdict(lambda: {"count": 0, "pop": [], "food": [], "wealth": [], "defense": []})
    for st in settlement_transitions:
        key = f"{st['from']}->{st['to']}"
        s = settle_trans_summary[key]
        s["count"] += 1
        s["pop"].append(st["population"])
        s["food"].append(st["food"])
        s["wealth"].append(st["wealth"])
        s["defense"].append(st["defense"])

    settle_stats = {}
    for key, s in sorted(settle_trans_summary.items()):
        stats = {
            "count": s["count"],
            "population": {"mean": round(np.mean(s["pop"]), 4), "std": round(np.std(s["pop"]), 4),
                           "min": round(min(s["pop"]), 4), "max": round(max(s["pop"]), 4)},
            "food": {"mean": round(np.mean(s["food"]), 4), "std": round(np.std(s["food"]), 4),
                     "min": round(min(s["food"]), 4), "max": round(max(s["food"]), 4)},
            "wealth": {"mean": round(np.mean(s["wealth"]), 4), "std": round(np.std(s["wealth"]), 4),
                        "min": round(min(s["wealth"]), 4), "max": round(max(s["wealth"]), 4)},
            "defense": {"mean": round(np.mean(s["defense"]), 4), "std": round(np.std(s["defense"]), 4),
                         "min": round(min(s["defense"]), 4), "max": round(max(s["defense"]), 4)},
        }
        settle_stats[key] = stats
        print(f"  {key}: n={s['count']}, "
              f"pop={np.mean(s['pop']):.3f}±{np.std(s['pop']):.3f}, "
              f"food={np.mean(s['food']):.3f}±{np.std(s['food']):.3f}")

    results["settlement_transitions"] = settle_stats

    return results


def main():
    replays = load_all_replays()
    if not replays:
        print("No replays found!")
        return

    transition_counts, type_totals, spread_counts, settlement_transitions = analyze_replays(replays)
    results = build_results(transition_counts, type_totals, spread_counts, settlement_transitions)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "transitions.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()

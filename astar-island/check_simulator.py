"""
check_simulator.py — Monte Carlo validation harness for the C++ simulator.

For each frame transition (t → t+1) in the replay data, this script:
  1. Sends frame[t] to the C++ simulator K times (Monte Carlo).
  2. Builds an empirical distribution over cell types.
  3. Scores it with log-probability of the observed outcome.

Primary metric: log-probability of the actual next state under the simulator's
distribution. This is the correct scoring rule for a stochastic model — it
rewards putting high probability on what actually happened, regardless of what
the modal prediction was. "Accuracy" (argmax == actual) is misleading because
a well-calibrated 50/50 cell looks wrong half the time.

Per-transition output:
  ll_all      average log P(actual[t+1] | state[t]) over ALL cells
  ll_changed  same, restricted to cells that changed from t to t+1
              (these are the interesting cells — static cells trivially score
               near 0 since the simulator correctly keeps them fixed)
  n_changed   how many cells changed

Aggregate summary shows mean ± std across all evaluated transitions.

Usage:
    python check_simulator.py                          # all replays, K=200
    python check_simulator.py --replay <file.json>     # single replay
    python check_simulator.py --k 500                  # more Monte Carlo samples
    python check_simulator.py --steps 1,5,10,25,50     # only check these steps
    python check_simulator.py --sim ./simulator/sim    # custom simulator binary
    python check_simulator.py --debug 5                # show top-5 mismatch cells per step
"""

import argparse
import json
import math
import os
import subprocess
import sys
from collections import Counter
from glob import glob

REPLAY_DIR = os.path.join(os.path.dirname(__file__), "replays")
DEFAULT_SIM = os.path.join(os.path.dirname(__file__), "simulator", "sim")

# ---------------------------------------------------------------------------
# Parameter calibration (pure Python, no numpy)
# Estimates round-specific hidden parameters from the observed replay.
# The simulation has ~11 independent parameters that are fixed per round but
# vary across rounds — calibrating them from the replay dramatically improves
# simulation accuracy over using fixed priors.
# ---------------------------------------------------------------------------

PRIORS = dict(
    p_collapse=0.055, p_port_collapse=0.025,
    p_expand_base=0.003, p_expand_per_n=0.005,
    p_forest_base=0.004, p_forest_per_n=0.005,
    p_port_per_ocean=0.040,
    p_empty_to_ruin=0.0004, p_forest_to_ruin=0.0005,
    p_ruin_rebuild=0.48, p_ruin_to_empty=0.33, p_ruin_to_forest=0.18,
    p_ruin_port_per_ocean=0.05,
)

# How much to trust observed data vs priors (0=all prior, 1=all observed)
TRUST = dict(
    p_collapse=0.85, p_port_collapse=0.75,
    p_expand_base=0.60, p_expand_per_n=0.60,
    p_forest_base=0.60, p_forest_per_n=0.60,
    p_port_per_ocean=0.60,
    p_empty_to_ruin=0.70, p_forest_to_ruin=0.70,
    p_ruin_rebuild=0.85, p_ruin_to_empty=0.85, p_ruin_to_forest=0.85,
    p_ruin_port_per_ocean=0.70,
)


def _alive_neighbor_count(grid, x, y, H, W):
    """Count alive (settlement=1 or port=2) cells in the 8-neighborhood."""
    count = 0
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                v = grid[ny][nx]
                if v == 1 or v == 2:
                    count += 1
    return count


def _ocean_neighbor_count(grid, x, y, H, W):
    count = 0
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                if grid[ny][nx] == 10:
                    count += 1
    return count


def calibrate_params(frames, width, height):
    """
    Estimate round parameters by counting transitions across all replay frames.
    Returns a params dict ready to send to the C++ simulator.
    """
    H, W = height, width
    T = len(frames)

    # Accumulators
    s_total = s_to_r = 0
    p_total = p_to_r = 0
    # For expand: bucket by alive-neighbor count n
    e_total_n = [0] * 9   # empty cells with n alive neighbors
    e_to_s_n  = [0] * 9
    f_total_n = [0] * 9   # forest cells with n alive neighbors
    f_to_s_n  = [0] * 9
    # For port: sum ocean-neighbor counts for settlements that became port
    s_ocean_total = 0.0   # sum of ocean-neighbor counts for coastal settlements
    s_to_p_ocean  = 0     # settlements that became port (weighted by ocean count)
    e_to_r = f_to_r = 0
    r_to_s = r_to_e = r_to_f = r_to_p = r_total = 0
    r_ocean_total = 0.0
    r_to_p_ocean  = 0

    for t in range(1, T):
        prev = frames[t - 1]["grid"]
        curr = frames[t]["grid"]

        for y in range(H):
            for x in range(W):
                pv = prev[y][x]
                cv = curr[y][x]

                if pv == 1:  # settlement
                    s_total += 1
                    if cv == 3:
                        s_to_r += 1
                    elif cv == 2:
                        n_oc = _ocean_neighbor_count(prev, x, y, H, W)
                        s_ocean_total += n_oc
                        s_to_p_ocean  += n_oc  # contributes n_oc to numerator

                elif pv == 2:  # port
                    p_total += 1
                    if cv == 3:
                        p_to_r += 1

                elif pv == 0 or pv == 11:  # empty / plains
                    n_al = _alive_neighbor_count(prev, x, y, H, W)
                    n_al = min(n_al, 8)
                    e_total_n[n_al] += 1
                    if cv == 1:
                        e_to_s_n[n_al] += 1
                    elif cv == 3:
                        e_to_r += 1

                elif pv == 4:  # forest
                    n_al = _alive_neighbor_count(prev, x, y, H, W)
                    n_al = min(n_al, 8)
                    f_total_n[n_al] += 1
                    if cv == 1:
                        f_to_s_n[n_al] += 1
                    elif cv == 3:
                        f_to_r += 1

                elif pv == 3:  # ruin
                    r_total += 1
                    n_oc = _ocean_neighbor_count(prev, x, y, H, W)
                    r_ocean_total += n_oc
                    if cv == 1:
                        r_to_s += 1
                    elif cv == 0 or cv == 11:
                        r_to_e += 1
                    elif cv == 4:
                        r_to_f += 1
                    elif cv == 2:
                        r_to_p += 1
                        r_to_p_ocean += n_oc

    # --- Compute observed rates ---
    obs = {}
    obs["p_collapse"]      = s_to_r / max(s_total, 1)
    obs["p_port_collapse"] = p_to_r / max(p_total, 1)
    obs["p_empty_to_ruin"] = e_to_r / max(sum(e_total_n), 1)
    obs["p_forest_to_ruin"]= f_to_r / max(sum(f_total_n), 1)

    # Fit expand_base + expand_per_n * n via least squares (pure Python)
    obs["p_expand_base"], obs["p_expand_per_n"] = _fit_linear(e_total_n, e_to_s_n)
    obs["p_forest_base"], obs["p_forest_per_n"] = _fit_linear(f_total_n, f_to_s_n)

    obs["p_port_per_ocean"] = s_to_p_ocean / max(s_ocean_total, 1)

    if r_total > 0:
        obs["p_ruin_rebuild"]  = r_to_s / r_total
        obs["p_ruin_to_empty"] = r_to_e / r_total
        obs["p_ruin_to_forest"]= r_to_f / r_total
        obs["p_ruin_port_per_ocean"] = r_to_p_ocean / max(r_ocean_total, 1) \
                                        if r_ocean_total > 0 else PRIORS["p_ruin_port_per_ocean"]
    else:
        obs["p_ruin_rebuild"]  = PRIORS["p_ruin_rebuild"]
        obs["p_ruin_to_empty"] = PRIORS["p_ruin_to_empty"]
        obs["p_ruin_to_forest"]= PRIORS["p_ruin_to_forest"]
        obs["p_ruin_port_per_ocean"] = PRIORS["p_ruin_port_per_ocean"]

    # Blend observed with priors
    params = {k: TRUST[k] * obs[k] + (1 - TRUST[k]) * PRIORS[k] for k in PRIORS}
    return params


def _fit_linear(total_n, event_n, min_count=10):
    """
    Fit rate(n) = base + per_n * n via least squares on buckets with enough data.
    Falls back to simple average if insufficient data.
    """
    xs, ys = [], []
    for n in range(9):
        if total_n[n] >= min_count:
            xs.append(n)
            ys.append(event_n[n] / total_n[n])
    if len(xs) < 2:
        total = sum(total_n)
        events = sum(event_n)
        rate = events / max(total, 1)
        return rate * 0.5, rate * 0.5
    # Least squares: minimize sum (y - base - per_n*x)^2
    n_pts = len(xs)
    sx  = sum(xs)
    sy  = sum(ys)
    sxx = sum(x*x for x in xs)
    sxy = sum(x*y for x, y in zip(xs, ys))
    denom = n_pts * sxx - sx * sx
    if abs(denom) < 1e-12:
        avg = sy / n_pts
        return max(avg * 0.5, 0.0), max(avg * 0.5, 0.0)
    per_n = (n_pts * sxy - sx * sy) / denom
    base  = (sy - per_n * sx) / n_pts
    return max(base, 0.0), max(per_n, 0.0)

CELL_NAMES = {
    0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin",
    4: "Forest", 5: "Mountain", 10: "Ocean", 11: "Plains",
}
CELL_CHARS = {
    0: ".", 1: "S", 2: "P", 3: "R", 4: "F", 5: "^", 10: "~", 11: "_",
}


def load_replay(path):
    with open(path) as f:
        return json.load(f)


def make_frame_line(frame, width, height, params=None):
    payload = {
        "grid":        frame["grid"],
        "settlements": frame["settlements"],
        "width":       width,
        "height":      height,
    }
    if params:
        payload["params"] = params
    return json.dumps(payload, separators=(",", ":"))


def run_mc(sim_proc, frame_line, k):
    """Send frame_line to the simulator K times; return list of output grids."""
    grids = []
    for _ in range(k):
        sim_proc.stdin.write(frame_line + "\n")
        sim_proc.stdin.flush()
        out = sim_proc.stdout.readline()
        if not out:
            raise RuntimeError("Simulator closed stdout unexpectedly")
        result = json.loads(out)
        if "error" in result:
            raise RuntimeError(f"Simulator error: {result['error']}")
        grids.append(result["grid"])
    return grids


def build_tables(grids, H, W):
    """
    Build empirical cell-type count tables from K simulated grids.
    tables[y][x] = Counter(cell_value -> count)
    """
    tables = [[Counter() for _ in range(W)] for _ in range(H)]
    for grid in grids:
        for y in range(H):
            for x in range(W):
                tables[y][x][grid[y][x]] += 1
    return tables


def cell_log_prob(tables, y, x, actual_val, k, floor=1e-6):
    """log P(actual_val) under empirical distribution at (x,y), with floor."""
    cnt = tables[y][x].get(actual_val, 0)
    return math.log(max(cnt / k, floor))


def check_transition(sim_proc, frame_t, frame_t1, width, height, k, params=None, n_debug=0):
    """
    Run K simulations from frame_t and compare to actual frame_t1.
    Returns (metrics_dict, debug_lines).
    """
    H, W = height, width
    line  = make_frame_line(frame_t, width, height, params)
    grids = run_mc(sim_proc, line, k)
    tables = build_tables(grids, H, W)

    g_actual = frame_t1["grid"]
    g_prev   = frame_t["grid"]

    total_ll   = 0.0
    changed_ll = 0.0
    n_changed  = 0
    cell_info  = []   # for debug

    for y in range(H):
        for x in range(W):
            actual = g_actual[y][x]
            prev   = g_prev[y][x]
            ll     = cell_log_prob(tables, y, x, actual, k)

            total_ll += ll

            if prev != actual:
                n_changed  += 1
                changed_ll += ll
                if n_debug:
                    cell_info.append((ll, x, y, prev, actual, dict(tables[y][x])))

    n_cells = H * W
    metrics = {
        "ll_all":     total_ll   / n_cells,
        "ll_changed": changed_ll / n_changed if n_changed else float("nan"),
        "n_changed":  n_changed,
    }

    debug_lines = []
    if n_debug and cell_info:
        cell_info.sort()   # worst (lowest ll) first
        debug_lines.append("  Worst mismatch cells (changed, lowest log-prob):")
        for ll, x, y, prev, actual, dist in cell_info[:n_debug]:
            # Build distribution string sorted by probability
            dist_str = " ".join(
                f"{CELL_NAMES.get(v,'?')}:{cnt/k:.2f}"
                for v, cnt in sorted(dist.items(), key=lambda t: -t[1])
            )
            nbhd = neighborhood_str(g_prev, x, y, H, W)
            debug_lines.append(
                f"    ({x:2d},{y:2d}) {CELL_NAMES.get(prev,'?'):10s}→{CELL_NAMES.get(actual,'?'):10s}"
                f"  ll={ll:.3f}  dist=[{dist_str}]"
            )
            debug_lines.append(f"           neighborhood (prev):\n{nbhd}")

    return metrics, debug_lines


def neighborhood_str(grid, cx, cy, H, W, radius=2):
    """Return an ASCII art snippet of the neighborhood around (cx,cy)."""
    lines = []
    for y in range(cy - radius, cy + radius + 1):
        row = []
        for x in range(cx - radius, cx + radius + 1):
            if x < 0 or x >= W or y < 0 or y >= H:
                row.append(" ")
            elif x == cx and y == cy:
                row.append("*")
            else:
                row.append(CELL_CHARS.get(grid[y][x], "?"))
        lines.append("           " + " ".join(row))
    return "\n".join(lines)


def check_replay(replay_path, sim_binary, k, steps_filter=None, verbose=True, n_debug=0, no_calibrate=False):
    """Check one replay file. Returns list of per-step metric dicts."""
    data    = load_replay(replay_path)
    frames  = data["frames"]
    width   = data["width"]
    height  = data["height"]
    n_steps = len(frames) - 1

    # Calibrate round-specific parameters from the full replay
    if no_calibrate:
        params = None
    else:
        params = calibrate_params(frames, width, height)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Replay: {os.path.basename(replay_path)}")
        print(f"  {n_steps} transitions, {width}x{height}, K={k}")
        if params:
            print(f"  Calibrated params: collapse={params['p_collapse']:.4f}  "
                  f"port_collapse={params['p_port_collapse']:.4f}  "
                  f"expand_base={params['p_expand_base']:.4f}  "
                  f"expand_per_n={params['p_expand_per_n']:.4f}  "
                  f"ruin_rebuild={params['p_ruin_rebuild']:.3f}")
        print(f"  {'step':>4}  {'ll_all':>8}  {'ll_changed':>10}  {'n_changed':>9}")

    sim_proc = subprocess.Popen(
        [sim_binary],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    results = []
    try:
        for t in range(n_steps):
            step = t + 1
            if steps_filter and step not in steps_filter:
                continue

            m, dbg = check_transition(
                sim_proc, frames[t], frames[t + 1], width, height, k, params, n_debug
            )
            m["step"] = step
            results.append(m)

            if verbose:
                if math.isnan(m["ll_changed"]):
                    chg_str = "       —"
                else:
                    chg_str = f"{m['ll_changed']:10.3f}"
                print(f"  {step:>4}  {m['ll_all']:8.4f}  {chg_str}  {m['n_changed']:9d}")
                for line in dbg:
                    print(line)
    finally:
        sim_proc.stdin.close()
        sim_proc.wait()

    return results


def print_summary(all_results):
    if not all_results:
        return

    ll_all_vals = [m["ll_all"] for m in all_results]
    ll_chg_vals = [m["ll_changed"] for m in all_results if not math.isnan(m["ll_changed"])]

    def stats(vals):
        if not vals:
            return float("nan"), float("nan")
        mu  = sum(vals) / len(vals)
        var = sum((v - mu)**2 for v in vals) / len(vals)
        return mu, math.sqrt(var)

    mu_all,  sd_all  = stats(ll_all_vals)
    mu_chg,  sd_chg  = stats(ll_chg_vals)

    # A perfect model that always outputs the correct cell would get ll=0 per cell.
    # A naive "never change" model gets ll=0 on static cells and floor on changed ones.
    # The gap between ll_all and ll_changed tells you how much the simulator is
    # hurting on interesting (dynamic) cells vs. static ones.

    print(f"\n{'='*60}")
    print("AGGREGATE SUMMARY")
    print(f"  transitions evaluated : {len(all_results)}")
    print(f"  ll_all  (per cell)    : {mu_all:.4f}  ±{sd_all:.4f}")
    print(f"  ll_changed (per cell) : {mu_chg:.4f}  ±{sd_chg:.4f}   ({len(ll_chg_vals)} transitions with changes)")
    print()
    print("  Interpretation: log-prob is in nats; 0.0 = perfect, more negative = worse.")
    print("  ll_changed is the key metric — it only scores cells that actually changed.")
    print(f"  A 'never-change' baseline scores ll_changed = log(floor) ≈ {math.log(1e-6):.1f}.")
    print(f"  A random 8-class uniform baseline scores ≈ {math.log(1/8):.2f}.")


def main():
    parser = argparse.ArgumentParser(description="Validate C++ simulator against replay data")
    parser.add_argument("--replay", default=None,
                        help="Path to a single replay JSON (default: all in replays/)")
    parser.add_argument("--sim", default=DEFAULT_SIM,
                        help="Path to simulator binary (default: simulator/sim)")
    parser.add_argument("--k", type=int, default=200,
                        help="Monte Carlo samples per transition (default: 200)")
    parser.add_argument("--steps", default=None,
                        help="Comma-separated step numbers to check (default: all)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-step output, only print summary")
    parser.add_argument("--debug", type=int, default=0, metavar="N",
                        help="Show N worst mismatch cells per step with neighborhood context")
    parser.add_argument("--no-calibrate", action="store_true",
                        help="Use hardcoded prior params instead of calibrating from replay")
    args = parser.parse_args()

    if not os.path.isfile(args.sim):
        print(f"ERROR: simulator binary not found at {args.sim}")
        print("Build it first:  cd simulator && make")
        sys.exit(1)

    steps_filter = None
    if args.steps:
        steps_filter = set(int(s) for s in args.steps.split(","))

    if args.replay:
        replay_files = [args.replay]
    else:
        replay_files = sorted(glob(os.path.join(REPLAY_DIR, "*.json")))
        if not replay_files:
            print(f"No replay files found in {REPLAY_DIR}")
            sys.exit(1)

    all_results = []
    for rfile in replay_files:
        results = check_replay(
            rfile, args.sim, args.k, steps_filter,
            verbose=not args.quiet, n_debug=args.debug,
            no_calibrate=args.no_calibrate,
        )
        all_results.extend(results)

    print_summary(all_results)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate HTML showing the initial map + all query responses as a grid.

Usage:
  python3 view_queries.py simulations/20260320_174421_c5cdf100
  python3 view_queries.py simulations/20260320_174421_c5cdf100 --seed 0
"""

import argparse
import json
import os
from pathlib import Path

TERRAIN_COLORS = {
    0: "#d4c89a",   # empty
    1: "#c0392b",   # settlement (red)
    2: "#2980b9",   # port (blue)
    3: "#e67e22",   # ruin (orange - distinct from mountain)
    4: "#27ae60",   # forest (green)
    5: "#4a4a4a",   # mountain (dark grey)
    10: "#1a5276",  # ocean (dark blue)
    11: "#d4c89a",  # plains
}

TERRAIN_NAMES = {
    0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin",
    4: "Forest", 5: "Mountain", 10: "Ocean", 11: "Plains",
}


def render_grid_js(var_name, grid, cell_size, canvas_id):
    """Return JS to draw a grid on a canvas."""
    return f"""
(function() {{
  const grid = {json.dumps(grid)};
  const cs = {cell_size};
  const c = document.getElementById('{canvas_id}');
  const ctx = c.getContext('2d');
  const colors = {json.dumps({str(k): v for k, v in TERRAIN_COLORS.items()})};
  for (let y = 0; y < grid.length; y++)
    for (let x = 0; x < grid[0].length; x++) {{
      ctx.fillStyle = colors[String(grid[y][x])] || '#333';
      ctx.fillRect(x * cs, y * cs, cs, cs);
      ctx.strokeStyle = 'rgba(0,0,0,0.15)';
      ctx.strokeRect(x * cs, y * cs, cs, cs);
    }}
}})();
"""


def generate_html(run_dir, seed_idx, output_path):
    run_dir = Path(run_dir)

    # Load initial state
    initial_path = run_dir / f"seed_{seed_idx}_initial.json"
    if not initial_path.exists():
        print(f"No initial state for seed {seed_idx}")
        return
    initial = json.load(open(initial_path))
    full_grid = initial["grid"]
    H, W = len(full_grid), len(full_grid[0])

    # Load query responses
    queries_path = run_dir / f"seed_{seed_idx}.json"
    if not queries_path.exists():
        print(f"No query responses for seed {seed_idx}")
        return
    queries = json.load(open(queries_path))
    n_queries = len(queries)

    # Get viewport info
    vp = queries[0]["viewport"]
    vx, vy, vw, vh = vp["x"], vp["y"], vp["w"], vp["h"]

    # Load summary
    summary_path = run_dir / "summary.json"
    summary = json.load(open(summary_path)) if summary_path.exists() else {}

    cell_full = 12  # cell size for full map
    cell_vp = 16    # cell size for viewport grids

    # Layout: ~10 per row
    cols = 10
    rows = (n_queries + cols - 1) // cols

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html><head><title>Query Responses - Seed {seed_idx}</title>
<style>
body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 20px; }}
h2 {{ color: #e94560; margin-bottom: 5px; }}
h3 {{ color: #aaa; margin: 15px 0 5px; }}
.info {{ color: #888; margin: 3px 0; font-size: 13px; }}
.grid-container {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }}
.grid-item {{ text-align: center; }}
.grid-item canvas {{ border: 1px solid #333; }}
.grid-item .label {{ font-size: 11px; color: #888; margin-top: 2px; }}
.legend {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 12px; }}
.legend-color {{ width: 12px; height: 12px; border: 1px solid #555; }}
.full-map {{ margin: 10px 0; }}
</style></head><body>
<h2>Query Responses: Seed {seed_idx}</h2>
<div class="info">Round: {summary.get('round_id', '?')[:8]}</div>
<div class="info">Viewport: ({vx}, {vy}) {vw}x{vh} — {n_queries} queries</div>
<div class="legend">
  <div class="legend-item"><div class="legend-color" style="background:#d4c89a"></div>Empty/Plains</div>
  <div class="legend-item"><div class="legend-color" style="background:#c0392b"></div>Settlement</div>
  <div class="legend-item"><div class="legend-color" style="background:#2980b9"></div>Port</div>
  <div class="legend-item"><div class="legend-color" style="background:#e67e22"></div>Ruin</div>
  <div class="legend-item"><div class="legend-color" style="background:#27ae60"></div>Forest</div>
  <div class="legend-item"><div class="legend-color" style="background:#4a4a4a"></div>Mountain</div>
  <div class="legend-item"><div class="legend-color" style="background:#1a5276"></div>Ocean</div>
</div>
""")

    # Full initial map with viewport rectangle
    html_parts.append(f"""
<h3>Initial Map (full {W}x{H})</h3>
<div class="full-map">
<canvas id="fullmap" width="{W * cell_full}" height="{H * cell_full}"></canvas>
</div>
<script>
{render_grid_js('fullmap', full_grid, cell_full, 'fullmap')}
// Draw viewport rectangle
(function() {{
  const ctx = document.getElementById('fullmap').getContext('2d');
  ctx.strokeStyle = '#e94560';
  ctx.lineWidth = 2;
  ctx.strokeRect({vx * cell_full}, {vy * cell_full}, {vw * cell_full}, {vh * cell_full});
}})();
</script>
""")

    # Initial viewport crop
    initial_vp = []
    for y in range(vy, min(vy + vh, H)):
        row = []
        for x in range(vx, min(vx + vw, W)):
            row.append(full_grid[y][x])
        initial_vp.append(row)

    html_parts.append(f"""
<h3>Initial Viewport vs Query Responses</h3>
<div class="grid-container">
<div class="grid-item">
  <canvas id="vp_initial" width="{vw * cell_vp}" height="{vh * cell_vp}"></canvas>
  <div class="label">Initial</div>
</div>
""")

    html_parts.append(f"""<script>
{render_grid_js('vp_initial', initial_vp, cell_vp, 'vp_initial')}
</script>""")

    # Each query response
    for qi, qr in enumerate(queries):
        resp_grid = qr["response"]["grid"]
        cid = f"vp_q{qi}"
        html_parts.append(f"""
<div class="grid-item">
  <canvas id="{cid}" width="{vw * cell_vp}" height="{vh * cell_vp}"></canvas>
  <div class="label">Q{qi+1}</div>
</div>
<script>
{render_grid_js(cid, resp_grid, cell_vp, cid)}
</script>
""")

    html_parts.append("</div>")  # close grid-container
    html_parts.append("</body></html>")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(html_parts))
    print(f"Written: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize query responses")
    parser.add_argument("run_dir", help="Path to simulation run directory")
    parser.add_argument("--seed", type=int, default=None, help="Seed index (default: all with queries)")
    parser.add_argument("--output", type=str, default=None, help="Output HTML path")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)

    # Find which seeds have query responses
    if args.seed is not None:
        seeds = [args.seed]
    else:
        seeds = []
        for f in sorted(run_dir.glob("seed_*.json")):
            name = f.stem
            if "_" not in name.replace("seed_", ""):
                # seed_N.json (not seed_N_something.json)
                idx = int(name.replace("seed_", ""))
                seeds.append(idx)

    if not seeds:
        print("No query response files found.")
        return

    for seed_idx in seeds:
        if args.output:
            out = args.output
        else:
            out = str(run_dir / f"view_queries_seed_{seed_idx}.html")
        generate_html(args.run_dir, seed_idx, out)


if __name__ == "__main__":
    main()

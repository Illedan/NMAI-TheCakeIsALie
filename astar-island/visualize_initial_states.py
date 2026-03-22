"""Generate an interactive HTML visualization of initial states for the latest round."""

import json
import os
import glob
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INITIAL_STATES_DIR = os.path.join(SCRIPT_DIR, "initial_states")

TILE_CODES = {
    0: ("Empty", "#d4c89a"),
    1: ("Settlement", "#e08030"),
    2: ("Port", "#a050c0"),
    3: ("Ruin", "#8b0000"),
    4: ("Forest", "#2d8a2d"),
    5: ("Mountain", "#888888"),
    10: ("Ocean", "#1a3a6a"),
    11: ("Plains", "#c8b870"),
}

CELL_SIZE = 14


def find_latest_round():
    dirs = sorted(glob.glob(os.path.join(INITIAL_STATES_DIR, "*")))
    if not dirs:
        print("No initial_states directories found.")
        sys.exit(1)
    return dirs[-1]


def load_round(round_dir):
    with open(os.path.join(round_dir, "summary.json")) as f:
        summary = json.load(f)
    seeds = []
    for idx in range(summary["seeds_count"]):
        with open(os.path.join(round_dir, f"seed_{idx}.json")) as f:
            seeds.append(json.load(f))
    return summary, seeds


def generate_html(summary, seeds):
    round_id = summary["round_id"]
    round_num = summary["round_number"]
    W, H = summary["map_width"], summary["map_height"]
    n_seeds = len(seeds)
    grid_w = W * CELL_SIZE
    grid_h = H * CELL_SIZE
    total_w = n_seeds * (grid_w + 20) + 20

    # Build settlement lookup per seed
    settlement_maps = []
    for seed in seeds:
        smap = {}
        for s in seed["settlements"]:
            smap[(s["x"], s["y"])] = s
        settlement_maps.append(smap)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Round {round_num} - Initial States ({round_id[:8]})</title>
<style>
body {{ font-family: monospace; background: #1e1e2e; color: #cdd6f4; margin: 20px; }}
h1 {{ font-size: 18px; }}
.container {{ display: flex; gap: 20px; flex-wrap: wrap; }}
.seed-panel {{ }}
.seed-title {{ font-size: 14px; margin-bottom: 4px; }}
.grid {{ position: relative; width: {grid_w}px; height: {grid_h}px; }}
.cell {{
    position: absolute;
    width: {CELL_SIZE-1}px;
    height: {CELL_SIZE-1}px;
    cursor: crosshair;
}}
.cell:hover {{
    outline: 2px solid #fff;
    z-index: 10;
}}
#tooltip {{
    position: fixed;
    background: #313244;
    border: 1px solid #585b70;
    padding: 8px 12px;
    font-size: 13px;
    pointer-events: none;
    display: none;
    z-index: 100;
    border-radius: 4px;
    line-height: 1.5;
    white-space: pre;
}}
</style>
</head>
<body>
<h1>Round {round_num} &mdash; {round_id} &mdash; {W}x{H} map, {n_seeds} seeds</h1>
<div class="container">
"""

    for seed_idx, seed in enumerate(seeds):
        grid = seed["grid"]
        smap = settlement_maps[seed_idx]
        n_settlements = len([s for s in seed["settlements"] if s["alive"]])
        n_ports = len([s for s in seed["settlements"] if s.get("has_port")])

        html += f'<div class="seed-panel">\n'
        html += f'<div class="seed-title">Seed {seed_idx} ({n_settlements} settlements, {n_ports} ports)</div>\n'
        html += f'<div class="grid">\n'

        for y in range(H):
            for x in range(W):
                code = grid[y][x]
                name, color = TILE_CODES.get(code, (f"Unknown({code})", "#ff00ff"))
                tip = f"({x},{y}) {name} [code={code}]"
                if (x, y) in smap:
                    s = smap[(x, y)]
                    port_str = " PORT" if s.get("has_port") else ""
                    tip += f"\\nSettlement{port_str}"
                    tip += f"\\nalive={s['alive']}"
                left = x * CELL_SIZE
                top = y * CELL_SIZE
                html += (
                    f'<div class="cell" style="left:{left}px;top:{top}px;background:{color}"'
                    f' data-tip="{tip}"></div>\n'
                )

        html += '</div>\n</div>\n'

    html += """</div>
<div id="tooltip"></div>
<script>
const tooltip = document.getElementById('tooltip');
document.querySelectorAll('.cell').forEach(cell => {
    cell.addEventListener('mousemove', e => {
        tooltip.textContent = cell.dataset.tip;
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 15) + 'px';
        tooltip.style.top = (e.clientY + 15) + 'px';
    });
    cell.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
    });
});
</script>
</body>
</html>"""

    return html


def main():
    round_dir = sys.argv[1] if len(sys.argv) > 1 else find_latest_round()
    summary, seeds = load_round(round_dir)
    html = generate_html(summary, seeds)
    out_path = os.path.join(SCRIPT_DIR, "initial_states_view.html")
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Written to {out_path}")
    print(f"Round {summary['round_number']} ({summary['round_id'][:8]}), {len(seeds)} seeds")


if __name__ == "__main__":
    main()

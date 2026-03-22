"""Generate an interactive HTML replay viewer for Astar Island.

Usage:
    python visualize_replay.py <replay.json>
    python visualize_replay.py replays/03_19_22_replay_seed_0_*.json

Opens the generated HTML in the default browser.
"""

import json
import os
import sys
import webbrowser
import tempfile

TERRAIN_NAMES = {
    0: "Empty", 1: "Settlement", 2: "Port", 3: "Ruin",
    4: "Forest", 5: "Mountain", 10: "Ocean", 11: "Plains",
}

TERRAIN_COLORS = {
    0: "#e0e0e0",   # Empty — light gray
    1: "#e07020",   # Settlement — orange
    2: "#2080d0",   # Port — blue
    3: "#a04040",   # Ruin — dark red
    4: "#30a030",   # Forest — green
    5: "#808080",   # Mountain — gray
    10: "#1040a0",  # Ocean — dark blue
    11: "#c0d890",  # Plains — light green
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Astar Island Replay — Seed {seed_index}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #1a1a2e; color: #eee; font-family: monospace; display: flex; flex-direction: column; align-items: center; padding: 16px; }}
h2 {{ margin-bottom: 8px; }}
#controls {{ margin: 8px 0; display: flex; gap: 16px; align-items: center; }}
#controls button {{ background: #333; color: #eee; border: 1px solid #555; padding: 4px 12px; cursor: pointer; font-family: monospace; }}
#controls button:hover {{ background: #555; }}
#step-label {{ min-width: 120px; text-align: center; }}
#speed-label {{ font-size: 12px; }}
canvas {{ cursor: crosshair; border: 1px solid #444; }}
#tooltip {{ position: fixed; background: #222; border: 1px solid #666; padding: 8px 12px; font-size: 13px; line-height: 1.5; pointer-events: none; display: none; z-index: 10; white-space: pre; border-radius: 4px; }}
#info {{ margin-top: 8px; font-size: 12px; color: #888; }}
</style>
</head>
<body>
<h2>Astar Island Replay — Round {round_id_short}, Seed {seed_index}</h2>
<div id="controls">
  <button id="btn-prev">◀ Prev</button>
  <button id="btn-play">▶ Play</button>
  <button id="btn-next">Next ▶</button>
  <span id="step-label">Step 0 / {max_step}</span>
  <span id="speed-label">Speed: 1x</span>
</div>
<canvas id="grid" width="{canvas_w}" height="{canvas_h}"></canvas>
<div id="tooltip"></div>
<div id="info">Space: play/pause | ←→: step | +/−: speed | Click: inspect cell</div>

<script>
const CELL = {cell_size};
const W = {width};
const H = {height};
const frames = {frames_json};
const terrainNames = {terrain_names_json};
const terrainColors = {terrain_colors_json};

let currentStep = 0;
let playing = false;
let interval = null;
let speed = 1;

const canvas = document.getElementById('grid');
const ctx = canvas.getContext('2d');
const tooltip = document.getElementById('tooltip');
const stepLabel = document.getElementById('step-label');
const speedLabel = document.getElementById('speed-label');
const btnPlay = document.getElementById('btn-play');

function getSettlementAt(frame, x, y) {{
  return frame.settlements.find(s => s.x === x && s.y === y) || null;
}}

function drawGrid() {{
  const frame = frames[currentStep];
  for (let y = 0; y < H; y++) {{
    for (let x = 0; x < W; x++) {{
      const val = frame.grid[y][x];
      ctx.fillStyle = terrainColors[val] || '#ff00ff';
      ctx.fillRect(x * CELL, y * CELL, CELL, CELL);

      // Draw settlement marker
      const s = getSettlementAt(frame, x, y);
      if (s) {{
        ctx.strokeStyle = s.alive ? '#fff' : '#666';
        ctx.lineWidth = 1;
        ctx.strokeRect(x * CELL + 1, y * CELL + 1, CELL - 2, CELL - 2);
        if (s.has_port) {{
          ctx.fillStyle = '#fff';
          ctx.beginPath();
          ctx.arc(x * CELL + CELL/2, y * CELL + CELL/2, 2, 0, Math.PI * 2);
          ctx.fill();
        }}
      }}
    }}
  }}
  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 0.5;
  for (let x = 0; x <= W; x++) {{
    ctx.beginPath(); ctx.moveTo(x * CELL, 0); ctx.lineTo(x * CELL, H * CELL); ctx.stroke();
  }}
  for (let y = 0; y <= H; y++) {{
    ctx.beginPath(); ctx.moveTo(0, y * CELL); ctx.lineTo(W * CELL, y * CELL); ctx.stroke();
  }}
  stepLabel.textContent = `Step ${{frame.step}} / {max_step}`;
}}

function showTooltip(e) {{
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const x = Math.floor(mx / CELL);
  const y = Math.floor(my / CELL);
  if (x < 0 || x >= W || y < 0 || y >= H) {{ tooltip.style.display = 'none'; return; }}

  const frame = frames[currentStep];
  const val = frame.grid[y][x];
  const name = terrainNames[val] || 'Unknown';
  let text = `(${{x}}, ${{y}}) ${{name}} [${{val}}]`;

  const s = getSettlementAt(frame, x, y);
  if (s) {{
    text += `\\n──────────────────`;
    text += `\\nPopulation: ${{s.population.toFixed(3)}}`;
    text += `\\nFood:       ${{s.food.toFixed(3)}}`;
    text += `\\nWealth:     ${{s.wealth.toFixed(3)}}`;
    text += `\\nDefense:    ${{s.defense.toFixed(3)}}`;
    text += `\\nHas port:   ${{s.has_port}}`;
    text += `\\nAlive:      ${{s.alive}}`;
    text += `\\nOwner:      ${{s.owner_id}}`;
  }}

  tooltip.textContent = text;
  tooltip.style.display = 'block';
  tooltip.style.left = (e.clientX + 16) + 'px';
  tooltip.style.top = (e.clientY + 16) + 'px';
}}

function setStep(s) {{
  currentStep = Math.max(0, Math.min(frames.length - 1, s));
  drawGrid();
}}

function togglePlay() {{
  playing = !playing;
  btnPlay.textContent = playing ? '⏸ Pause' : '▶ Play';
  if (playing) {{
    interval = setInterval(() => {{
      if (currentStep >= frames.length - 1) {{ togglePlay(); return; }}
      setStep(currentStep + 1);
    }}, 300 / speed);
  }} else {{
    clearInterval(interval);
  }}
}}

function setSpeed(s) {{
  speed = Math.max(0.25, Math.min(8, s));
  speedLabel.textContent = `Speed: ${{speed}}x`;
  if (playing) {{
    clearInterval(interval);
    interval = setInterval(() => {{
      if (currentStep >= frames.length - 1) {{ togglePlay(); return; }}
      setStep(currentStep + 1);
    }}, 300 / speed);
  }}
}}

canvas.addEventListener('mousemove', showTooltip);
canvas.addEventListener('mouseleave', () => tooltip.style.display = 'none');

document.getElementById('btn-prev').addEventListener('click', () => setStep(currentStep - 1));
document.getElementById('btn-next').addEventListener('click', () => setStep(currentStep + 1));
btnPlay.addEventListener('click', togglePlay);

document.addEventListener('keydown', (e) => {{
  if (e.code === 'Space') {{ e.preventDefault(); togglePlay(); }}
  else if (e.code === 'ArrowLeft') {{ e.preventDefault(); setStep(currentStep - 1); }}
  else if (e.code === 'ArrowRight') {{ e.preventDefault(); setStep(currentStep + 1); }}
  else if (e.code === 'Equal' || e.code === 'NumpadAdd') {{ setSpeed(speed * 2); }}
  else if (e.code === 'Minus' || e.code === 'NumpadSubtract') {{ setSpeed(speed / 2); }}
}});

drawGrid();
</script>
</body>
</html>"""


def generate_viewer(replay_path: str) -> str:
    with open(replay_path) as f:
        data = json.load(f)

    width = data["width"]
    height = data["height"]
    cell_size = max(8, min(16, 640 // max(width, height)))

    html = HTML_TEMPLATE.format(
        seed_index=data["seed_index"],
        round_id_short=data["round_id"][:8],
        max_step=data["frames"][-1]["step"],
        width=width,
        height=height,
        cell_size=cell_size,
        canvas_w=width * cell_size,
        canvas_h=height * cell_size,
        frames_json=json.dumps(data["frames"]),
        terrain_names_json=json.dumps(TERRAIN_NAMES),
        terrain_colors_json=json.dumps(TERRAIN_COLORS),
    )

    out_path = replay_path.rsplit(".", 1)[0] + ".html"
    with open(out_path, "w") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_replay.py <replay.json>")
        sys.exit(1)

    path = generate_viewer(sys.argv[1])
    print(f"Generated: {path}")
    webbrowser.open(f"file://{os.path.abspath(path)}")

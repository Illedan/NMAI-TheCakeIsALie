#!/usr/bin/env python3
"""
Show scores for all improve_runs tasks.

  python scores.py            # best score per task
  python scores.py --latest   # most recent score per task
"""
import json, pathlib, sys

RUNS_DIR    = pathlib.Path(__file__).parent / "improve_runs"
LABEL_CACHE = pathlib.Path(__file__).parent / "improve_labels.json"

try:
    from dedup import normalize, GROUPS
    cache = json.loads(LABEL_CACHE.read_text()) if LABEL_CACHE.exists() else {}
    def get_label(log_stem):
        # Try to find the log file and get its label
        logs_dir = pathlib.Path(__file__).parent / "logs"
        f = logs_dir / f"{log_stem}.json"
        if f.exists():
            prompt = json.loads(f.read_text())["request"]["prompt"]
            raw = cache.get(normalize(prompt))
            return GROUPS.get(raw, raw) if raw else None
        return None
except Exception:
    def get_label(_): return None


use_latest = "--latest" in sys.argv

by_label = {}  # label -> chosen entry
for task_dir in sorted(RUNS_DIR.iterdir()):
    scores_file = task_dir / "scores.json"
    if not scores_file.exists():
        continue
    scores = json.loads(scores_file.read_text())
    if not scores:
        continue
    label = get_label(task_dir.name)
    if label is None:
        continue
    latest    = scores[-1]
    score_val = latest["score"]["score"] if latest.get("score") else None
    reason    = latest["score"]["reason"] if latest.get("score") else "—"
    rounds    = len(scores)
    calls     = latest["calls"]
    errors    = latest["errors"]
    entry = (score_val, label, rounds, calls, errors, reason)
    prev  = by_label.get(label)
    if use_latest:
        # Pick the task_dir with the most rounds (most recent run); tie-break by score
        if prev is None or rounds > prev[2] or (rounds == prev[2] and (score_val or 0) > (prev[0] or 0)):
            by_label[label] = entry
    else:
        # Pick highest score, tie-break by most rounds
        if prev is None or (score_val or 0) > (prev[0] or 0) or ((score_val or 0) == (prev[0] or 0) and rounds > prev[2]):
            by_label[label] = entry

rows = list(by_label.values())
rows.sort(key=lambda r: (r[0] is None, r[0]))  # None last, lowest first

print(f"{'Score':>5}  {'Rnd':>3}  {'Calls':>5}  {'Err':>3}  {'Task':<40}  Reason")
print("─" * 100)
for score_val, label, rounds, calls, errors, reason in rows:
    score_str = f"{score_val}/10" if score_val is not None else "  —  "
    print(f"{score_str:>5}  {rounds:>3}  {calls:>5}  {errors:>3}  {label:<40}  {reason[:60]}")

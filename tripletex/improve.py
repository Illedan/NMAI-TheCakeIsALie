#!/usr/bin/env python3
"""
Iterative improvement using raw JSON log files (no verifier needed).
Each log is run N rounds; learnings accumulate per log file.

  python improve.py                    # all logs, 3 rounds
  python improve.py 2026-03-19T21     # filter by filename substring
  python improve.py --rounds=5
  python improve.py --concurrency=4
  python improve.py --all              # include pre-competition logs too
  python improve.py --rerun-all        # don't skip 10/10 tasks
"""
import asyncio, json, os, pathlib, re, sys, time

LOGS_DIR    = pathlib.Path(__file__).parent / "logs"
RUNS_DIR    = pathlib.Path(__file__).parent / "improve_runs"
ONLINE_FROM = "2026-03-21T09-58"

# Import dedup helpers
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dedup import normalize, GROUPS, LABEL_CACHE


async def stream_output(stream, log_file, prefix):
    """Read lines from stream, print with prefix, write to log file."""
    with open(log_file, "wb") as f:
        async for line in stream:
            f.write(line)
            f.flush()
            print(f"  [{prefix}] {line.decode(errors='replace').rstrip()}", flush=True)


async def run_log(log_file: pathlib.Path, label: str, rounds: int, semaphore: asyncio.Semaphore,
                  idx: int, total: int, running: dict):
    async with semaphore:
        name     = log_file.stem[:24]
        task_dir = RUNS_DIR / log_file.stem
        task_dir.mkdir(parents=True, exist_ok=True)
        learnings = task_dir / "learnings.md"
        log_path  = task_dir / "worker.log"

        # Pre-populate learnings from canonical file if this is a new task dir
        if not learnings.exists():
            cn = label.lower().replace("+", " ").replace("(", " ").replace(")", " ").replace("/", "_").replace("-", "_")
            canonical_name = "_".join(cn.split())
            canonical_file = pathlib.Path(__file__).parent / "learnings" / f"{canonical_name}.md"
            if canonical_file.exists():
                learnings.write_text(canonical_file.read_text())

        running[name] = (label, time.time())
        print(f"\n[{idx}/{total}] START {label}  (learnings={'yes' if learnings.exists() else 'none'})", flush=True)

        t0 = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-u", "improve_worker.py",
                f"--log={log_file}",
                f"--learnings={learnings}",
                f"--rounds={rounds}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=pathlib.Path(__file__).parent,
            )
        except Exception as e:
            print(f"  [{label}] ERROR spawning subprocess: {e}", flush=True)
            running.pop(name, None)
            return {"name": name, "error": str(e), "elapsed": 0, "rounds_done": []}

        try:
            await stream_output(proc.stdout, log_path, label)
            await proc.wait()
        except Exception as e:
            print(f"  [{label}] ERROR reading output: {e}", flush=True)

        elapsed = time.time() - running[name][1]
        rc = proc.returncode
        running.pop(name, None)

        # Parse round summaries from log
        log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
        rounds_done = re.findall(r"Round (\d+) done: (\d+) calls, (\d+) errors", log_text)
        if rounds_done:
            last_r, last_calls, last_errors = rounds_done[-1]
            summary = f"round {last_r}: {last_calls} calls, {last_errors} errors"
        else:
            summary = "NO SUMMARY — check worker.log"

        flag = "✓" if rc == 0 else f"✗ rc={rc}"
        print(f"\n[{idx}/{total}] {flag} {label}  {elapsed:.0f}s  {summary}", flush=True)

        return {"name": name, "label": label, "elapsed": elapsed, "rc": rc, "rounds_done": rounds_done}


async def main():
    args        = sys.argv[1:]
    rounds      = int(next((a.split("=")[1] for a in args if a.startswith("--rounds=")),      3))
    concurrency = int(next((a.split("=")[1] for a in args if a.startswith("--concurrency=")), 4))
    include_all = "--all" in args
    rerun_all   = "--rerun-all" in args
    filter_     = next((a for a in args if not a.startswith("--")), None)

    all_logs = sorted(LOGS_DIR.glob("*.json"), reverse=True)
    logs = all_logs if include_all else [f for f in all_logs if f.name >= ONLINE_FROM]
    if filter_:
        logs = [f for f in logs if filter_ in f.name]

    # Load all prompts
    log_prompts = {}
    for f in logs:
        try:
            log_prompts[f] = json.loads(f.read_text())["request"]["prompt"]
        except Exception as e:
            print(f"  [WARN] could not read {f.name}: {e}", flush=True)

    # Deduplicate using cached Gemini labels + GROUPS mapping
    cache = json.loads(LABEL_CACHE.read_text()) if LABEL_CACHE.exists() else {}
    seen, deduped = set(), []
    unlabelled = []
    for f, prompt in log_prompts.items():
        raw_label = cache.get(normalize(prompt))
        if raw_label is None:
            unlabelled.append(f.name)
            group = normalize(prompt)
        else:
            group = GROUPS.get(raw_label, raw_label)
        if group not in seen:
            seen.add(group)
            deduped.append((f, group))

    if unlabelled:
        print(f"  [WARN] {len(unlabelled)} logs not in label cache — run dedup.py first")

    # Skip tasks that already scored 10/10 on their last round (unless --rerun-all)
    skipped = []
    filtered = []
    for f, label in deduped:
        scores_file = RUNS_DIR / f.stem / "scores.json"
        if not rerun_all and scores_file.exists():
            scores = json.loads(scores_file.read_text())
            if scores and (scores[-1].get("score") or {}).get("score") == 10:
                skipped.append(label)
                continue
        filtered.append((f, label))
    deduped = filtered

    print(f"  ({len(log_prompts) - len(deduped) - len(skipped)} duplicates removed, {len(deduped)} unique task types, {len(skipped)} skipped with 10/10)")
    for _, label in sorted(deduped, key=lambda x: x[1]):
        print(f"    {label}")
    if skipped:
        print(f"  Skipped (10/10): {', '.join(sorted(skipped))}")
    logs = [f for f, _ in deduped]

    if not logs:
        print("No logs match"); return

    RUNS_DIR.mkdir(exist_ok=True)
    print(f"Improving {len(logs)} logs × {rounds} rounds  (concurrency={concurrency})")
    print(f"Logs: improve_runs/<timestamp>/worker.log\n")

    running = {}  # name -> (label, start_time)
    semaphore = asyncio.Semaphore(concurrency)
    t0 = time.time()

    async def heartbeat():
        while True:
            await asyncio.sleep(30)
            if running:
                now = time.time()
                parts = [f"{label} ({now - start:.0f}s)" for _, (label, start) in sorted(running.items())]
                print(f"  [running] {' | '.join(parts)}", flush=True)

    hb = asyncio.create_task(heartbeat())

    futs = {asyncio.ensure_future(
        run_log(log, label, rounds, semaphore, i+1, len(logs), running)
    ): log for (log, label), i in zip(deduped, range(len(deduped)))}

    results = []
    pending = set(futs)
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"  [ERROR in future] {e}", flush=True)

    hb.cancel()

    failed = [r for r in results if r.get("rc", 1) != 0 or not r.get("rounds_done")]
    print(f"\n{'='*60}")
    print(f"Done in {time.time()-t0:.0f}s  ({len(results)}/{len(logs)} logs)")
    if failed:
        print(f"FAILED ({len(failed)}): {' '.join(r.get('label', r['name']) for r in failed)}")

asyncio.run(main())

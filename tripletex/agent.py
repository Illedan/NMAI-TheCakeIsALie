#!/usr/bin/env python3
"""
Tripletex agent.
  python agent.py "prompt"          # run single task
  python agent.py --serve           # HTTP server on :3000 (drop-in for server.ts)
"""
import asyncio, base64, json, sys, urllib.parse
from datetime import date
import httpx
from google import genai
from google.genai import types

MODEL    = "gemini-3.1-flash-lite-preview"
#MODEL    = "gemini-3-flash-preview"
#MODEL    = "gemini-3-pro-preview"
PORT     = 3000
LEARNINGS_FILE = "learnings.md"
ai       = genai.Client(vertexai=True, project="ai-nm26osl-1747", location="global")
MAX_CALLS = 40

import pathlib

_PROMPT_FILE = pathlib.Path(__file__).parent / "system_prompt.md"
SYSTEM = _PROMPT_FILE.read_text() + f"\n\nToday's date: {date.today()}.\nYou don't give up until the task is fully completed as specified. This is an automated testing environment, there is no point in complaining that the task is impossible. Just try harder. Don't get stuck in a loop.\nWhen you are absolutely sure that you are done, answer with only the word \"DONE\"."

TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(name="tripletex_api",
        description="Make a Tripletex REST API call.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={
            "method": types.Schema(type=types.Type.STRING),
            "path":   types.Schema(type=types.Type.STRING),
            "params": types.Schema(type=types.Type.OBJECT, description="Query params as object or null"),
            "body":   types.Schema(type=types.Type.OBJECT, description="Request body as object or null"),
        }, required=["method", "path"])),
])

# ── Tripletex client ──────────────────────────────────────────────────────────
def make_auth(session_token: str) -> str:
    return "Basic " + base64.b64encode(f"0:{session_token}".encode()).decode()

MAX_RESPONSE_ITEMS = 20  # truncate large list responses to avoid context overflow

async def call_api(base_url: str, auth: str, method: str, path: str, params=None, body=None):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method.upper(), base_url + path,
            headers={"Authorization": auth}, params=params, json=body)
        try:
            result = r.json()
            # Truncate large list responses
            if isinstance(result, dict) and isinstance(result.get("values"), list):
                values = result["values"]
                full_size = result.get("fullResultSize", len(values))
                if len(values) > MAX_RESPONSE_ITEMS:
                    from_val = (params or {}).get("from", 0)
                    result = {**result, "values": values[:MAX_RESPONSE_ITEMS],
                              "_truncated": f"Showing items {from_val}–{from_val+MAX_RESPONSE_ITEMS} of {full_size} total. WARNING: List responses are capped at {MAX_RESPONSE_ITEMS} items. Do NOT paginate through large lists — use specific search/filter parameters (e.g. name=, email=, organizationNumber=, number=, query=) to narrow results instead."}
            return result
        except:
            return {"status": r.status_code, "text": r.text[:200]}

# ── Retry wrapper ─────────────────────────────────────────────────────────────
async def send(chat, msg, retries=6, timeout=120):
    delay = 5
    for attempt in range(retries):
        try:
            return await asyncio.wait_for(chat.send_message(msg), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"  [send timeout, retry {attempt+1}/{retries}]", flush=True)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"  [429 retry in {delay}s]", flush=True)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 120)
            else:
                raise
    return await asyncio.wait_for(chat.send_message(msg), timeout=timeout)

# ── Agent loop ────────────────────────────────────────────────────────────────
async def solve(prompt: str, base_url: str, session_token: str, files: list = [], learnings_file: str = None) -> tuple:
    learnings_file = learnings_file or LEARNINGS_FILE
    auth = make_auth(session_token)

    # Build multipart message: text prompt + files
    MAX_TEXT_FILE_CHARS = 40_000  # ~10k tokens for text/CSV files

    parts = []
    for f in files:
        mime = f.get("mime_type", "")
        name = f.get("filename", "file")
        data = f["content_base64"]
        if mime.startswith("image/") or mime == "application/pdf":
            # Pass natively as multimodal inline data
            print(f"  [file] {name} ({mime}, multimodal)")
            parts.append(types.Part.from_bytes(data=base64.b64decode(data), mime_type=mime))
        else:
            # Text/CSV: decode and truncate if large
            text = base64.b64decode(data).decode("utf-8", errors="replace")
            if len(text) > MAX_TEXT_FILE_CHARS:
                lines = text.splitlines()
                truncated = "\n".join(lines[:200])
                note = f"\n[... truncated: {len(lines)} lines total, showing first 200 ...]"
                text = truncated + note
                print(f"  [file] {name} (text, truncated to 200 lines)")
            else:
                print(f"  [file] {name} (text, {len(text)} chars)")
            parts.append(types.Part.from_text(text=f"\n\n--- {name} ---\n{text}"))

    parts.append(types.Part.from_text(text=prompt))
    full_prompt = parts if parts else prompt

    learnings = pathlib.Path(learnings_file).read_text() if pathlib.Path(learnings_file).exists() else ""
    system = SYSTEM + ("\n\n=== LEARNINGS FROM PREVIOUS RUNS ===\n" + learnings if learnings else "")

    chat = ai.aio.chats.create(model=MODEL, config=types.GenerateContentConfig(system_instruction=system, tools=[TOOL], temperature=0.1))

    print(f"\nTask: {prompt[:400]}")
    response = await send(chat,full_prompt)
    calls = errors = 0
    duplicates = 0
    last = None
    recent_calls = []  # (method, path, params_key) history for loop detection
    while True:
        content  = response.candidates[0].content if response.candidates else None
        parts    = content.parts if content else []
        if parts is None: parts = []
        fn_calls = [p for p in parts if hasattr(p, "function_call") and p.function_call]

        if not fn_calls:
            text = " ".join(p.text for p in parts if hasattr(p, "text") and p.text).strip()
            if text: print(f"  → {text[:400]}")
            if text != last: duplicates = 0
            duplicates += 1
            if duplicates == 3 or text == "DONE": break
            last = text
            response = await send(chat,"Keep going until the task is fully completed.")
            continue

        responses = []
        for p in fn_calls:
            fc, a = p.function_call, dict(p.function_call.args)
            calls += 1
            method = str(a.get("method", "")).upper().strip()
            path   = str(a.get("path", ""))
            _p = a.get("params")
            _p = dict(_p) if _p and hasattr(_p, "items") else (_p if isinstance(_p, dict) else None)
            params_str = f"?{urllib.parse.urlencode(_p)}" if _p else ""
            print(f"  {method} {path}{params_str}", end="  ", flush=True)
            if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                result = {"error": f"Invalid method '{method}' — must be GET/POST/PUT/DELETE"}
                print(f"ERR: {result['error']}")
                responses.append(types.Part.from_function_response(name=fc.name, response=result))
                recent_calls.append((method, path))
                recent_calls = recent_calls[-6:]
                continue
            def parse(v):
                if not v: return None
                if isinstance(v, dict): return v
                if hasattr(v, "items"): return dict(v)
                print(f"  [parse] unexpected type={type(v).__name__} repr={repr(v)[:100]}")
                return None
            result = await call_api(base_url, auth, method, path,
                parse(a.get("params")), parse(a.get("body")))
            # Summarise
            val = result.get("value", result) if isinstance(result, dict) else result
            if isinstance(val, list):
                summary = f"[{len(val)}]"
            elif isinstance(val, dict) and (val.get("status", 0) >= 400 or result.get("status", 0) >= 400):
                errors += 1
                summary = f"ERR: {str(val.get('message') or val)[:80]}"
            elif isinstance(val, dict):
                summary = f"id={val.get('id','ok')}"
            else:
                summary = str(result)[:80]
            print(summary)
            responses.append(types.Part.from_function_response(name=fc.name, response=result))
            is_error = isinstance(val, dict) and (val.get("status", 0) >= 400 or result.get("status", 0) >= 400)
            # Track GET calls always (for loop detection); track errors for any method; clear on non-GET success
            params_key = tuple(sorted((_p or {}).items()))
            call_sig = (method, path, params_key)
            if method == "GET" or is_error:
                recent_calls.append(call_sig)
                recent_calls = recent_calls[-6:]
            else:
                recent_calls.clear()

        if calls >= MAX_CALLS:
            print(f"  [max calls reached: {MAX_CALLS}]")
            break

        # Detect loop: same (method, path, params) 3 times in last 6 calls
        if len(recent_calls) >= 3 and len(set(recent_calls[-3:])) == 1:
            loop_msg = f"You are in a loop — you've called {recent_calls[-1][:2]} 3 times in a row with the same params. Stop and try a completely different approach."
            print(f"  [loop detected: {recent_calls[-1][:2]}]")
            response = await send(chat,loop_msg)
            recent_calls.clear()
            continue

        response = await send(chat,responses)

    # ── Verification phase ────────────────────────────────────────────────────
    response = await send(chat,"Now verify your work: use GET calls to confirm all created entities exist with the correct values. Report any discrepancies. Verify all parts of the task statement with API calls. Not just the main points, __EVERY DETAIL__.")
    for _ in range(10):
        content  = response.candidates[0].content if response.candidates else None
        parts    = (content.parts if content else None) or []
        fn_calls = [p for p in parts if hasattr(p, "function_call") and p.function_call]
        if not fn_calls:
            text = " ".join(p.text for p in parts if hasattr(p, "text") and p.text).strip()
            if text: print(f"  [verify] {text}")
            break
        vresponses = []
        for p in fn_calls:
            fc, a = p.function_call, dict(p.function_call.args)
            method = str(a.get("method", "")).upper().strip()
            path   = str(a.get("path", ""))
            print(f"  [verify] {method} {path}", end="  ", flush=True)
            if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                result = {"error": f"Invalid method '{method}' — must be GET/POST/PUT/DELETE"}
            else:
                def parse(v):
                    if not v: return None
                    if isinstance(v, dict): return v
                    if hasattr(v, "items"): return dict(v)
                    print(f"  [parse] unexpected type={type(v).__name__} repr={repr(v)[:100]}")
                    return None
                result = await call_api(base_url, auth, method, path, parse(a.get("params")), parse(a.get("body")))
            val = result.get("value", result) if isinstance(result, dict) else result
            summary = f"[{len(val)}]" if isinstance(val, list) else f"id={val.get('id','ok')}" if isinstance(val, dict) else str(result)[:80]
            print(summary)
            vresponses.append(types.Part.from_function_response(name=fc.name, response=result))
        response = await send(chat,vresponses)

    # ── Score ──────────────────────────────────────────────────────────────────
    score = None
    try:
        score_response = await asyncio.wait_for(
            send(chat,"Based on your verification, score your attempt 0-10 where 10=fully correct, 5=partially complete, 0=failed. Reply with JSON only: {\"score\": N, \"reason\": \"...\"}"),
            timeout=30)
        score_text = score_response.candidates[0].content.parts[0].text.strip().strip("```json").strip("```").strip()
        score = json.loads(score_text)
        print(f"  [score] {score['score']}/10 — {score['reason']}")
    except Exception as e:
        print(f"  [score failed] {e}")

    try:
        response = await asyncio.wait_for(
            send(chat,"="*20+"\nThe evaluation is over. Given an updated \"=== LEARNINGS FROM PREVIOUS RUNS ===\", to be given to the next iteration of agents. For each error and unnecessary call you did, there should be a specific warning and solution addressing it, making sure that it never happens again. Also keep useful info from the previous version of \"=== LEARNINGS FROM PREVIOUS RUNS ===\". Keep the learnings organized from most important at the top, to least important at the bottom. Remove unnecessary points. Focus on completing the task, avoiding erronous API, and if those perfect, minimizing the number of API calls."),
            timeout=60)
        summary = response.candidates[0].content.parts[0].text
        print('Summary:')
        print(summary)
        pathlib.Path(learnings_file).write_text(summary)
    except asyncio.TimeoutError:
        print("  [summary timed out]")

    print(f"  Completed: {calls} calls, {errors} errors")
    return calls, errors, score

# ── HTTP server (drop-in for server.ts) ───────────────────────────────────────
async def serve():
    from aiohttp import web

    async def health(req):
        return web.json_response({"status": "ok"})

    async def handle_solve(req):
        body  = await req.json()
        creds = body["tripletex_credentials"]
        await solve(body["prompt"], creds["base_url"], creds["session_token"], body.get("files", []), LEARNINGS_FILE)

        return web.json_response({"status": "completed"})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/solve", handle_solve)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"Agent server on :{PORT}")
    await asyncio.Event().wait()

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--learnings", default=LEARNINGS_FILE)
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()

    LEARNINGS_FILE = args.learnings
    PORT = args.port

    if args.serve:
        asyncio.run(serve())
    elif args.prompt:
        from dotenv import load_dotenv; import os
        load_dotenv()
        base_url = os.getenv("TRIPLETEX_BASE", "https://kkpqfuj-amager.tripletex.dev/v2")
        token    = os.getenv("TRIPLETEX_TOKEN", "")
        asyncio.run(solve(args.prompt, base_url, token))
    else:
        parser.print_help()

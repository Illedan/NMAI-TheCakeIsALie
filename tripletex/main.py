import base64
import os
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

load_dotenv()

app = FastAPI()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
SOLVE_API_KEY = os.environ["SOLVE_API_KEY"]


@app.post("/solve")
async def solve(request: Request, authorization: str = Header()):
    # Verify Bearer token
    if not authorization.startswith("Bearer ") or authorization[7:] != SOLVE_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    prompt = body["prompt"]
    files = body.get("files", [])
    creds = body["tripletex_credentials"]

    base_url = creds["base_url"]
    token = creds["session_token"]
    auth = ("0", token)

    # Decode any attached files
    for f in files:
        data = base64.b64decode(f["content_base64"])
        Path(f["filename"]).write_bytes(data)

    # Use Claude to interpret the accounting task prompt
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are an accounting agent. Interpret this task and return "
                    f"the Tripletex API calls needed.\n\nTask: {prompt}"
                ),
            }
        ],
    )

    # TODO: Parse Claude's response and execute the API calls against Tripletex
    _ = message.content[0].text

    return JSONResponse({"status": "completed"})

"""
Local development server — use this to test with Discord on your machine.

Usage:
    set DISCORD_PUBLIC_KEY=<your-key>
    set DISCORD_TOKEN=<your-token>
    python local/local_server.py

Then in a second terminal:
    ngrok http 3000
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI, Request, Response

from bench_boss.bot import handle_interaction, verify_signature

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

app = FastAPI()


@app.post("/interactions")
async def interactions(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        return Response(content='{"error":"Invalid request signature"}', status_code=401, media_type="application/json")

    body = json.loads(raw_body)
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    return Response(content=json.dumps(result["body"]), status_code=result["statusCode"], media_type="application/json")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
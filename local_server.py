"""
Local development server — use this to test with Discord on your machine.

Usage:
    set DISCORD_PUBLIC_KEY=<your-key>
    python local_server.py

Then in a second terminal:
    ngrok http 3000
"""

import json
import os
from flask import Flask, request, jsonify
from bench_boss.bot import verify_signature, handle_interaction

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

app = Flask(__name__)


@app.route("/interactions", methods=["POST"])
def interactions():
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    raw_body = request.get_data()

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        return jsonify({"error": "Invalid request signature"}), 401

    body = json.loads(raw_body)
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    return jsonify(result["body"]), result["statusCode"]


if __name__ == "__main__":
    app.run(port=3000)
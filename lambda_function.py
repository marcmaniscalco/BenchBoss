"""
AWS Lambda entry point — used in production.
"""

import json
import os
from bench_boss.bot import verify_signature, handle_interaction

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]


def lambda_handler(event: dict, context) -> dict:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")
    raw_body = event.get("body", "").encode()

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        return {"statusCode": 401, "body": json.dumps({"error": "Invalid request signature"})}

    body = json.loads(raw_body)
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    return {"statusCode": result["statusCode"], "body": json.dumps(result["body"])}

"""
AWS Lambda entry point — used in production.
"""

import json
import logging
import os

from bench_boss.bot import handle_interaction, verify_signature

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]


def lambda_handler(event: dict, context) -> dict:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")
    raw_body = event.get("body", "").encode()

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        logger.warning("Invalid request signature")
        return {"statusCode": 401, "body": json.dumps({"error": "Invalid request signature"})}

    body = json.loads(raw_body)
    logger.info("Handling interaction type=%s", body.get("type"))
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    logger.info("Responding with statusCode=%s", result["statusCode"])
    return {"statusCode": result["statusCode"], "body": json.dumps(result["body"])}

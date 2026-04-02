"""
AWS Lambda entry point — used in production.
"""

import base64
import json
import os

import boto3
from aws_lambda_powertools import Logger

from bench_boss.bot import handle_interaction, verify_signature

logger = Logger(service="bench-boss")

DISCORD_PUBLIC_KEY = os.environ["DISCORD_PUBLIC_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

# SnapStart lifecycle hooks — no-op outside Lambda SnapStart environments.
try:
    from snapshot_restore_py import register_after_restore, register_before_snapshot

    @register_before_snapshot
    def _before_snapshot() -> None:
        """All heavy modules are imported at module level; nothing extra needed."""

    @register_after_restore
    def _after_restore() -> None:
        """Discard the boto3 default session so restored connection pools are not reused."""
        boto3.DEFAULT_SESSION = None

except ImportError:
    pass


def lambda_handler(event: dict, context) -> dict:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")

    raw_body_str = event.get("body", "")
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body_str)
    else:
        raw_body = raw_body_str.encode()

    if not verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        logger.warning("Invalid request signature")
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid request signature"}),
        }

    body = json.loads(raw_body)
    logger.info("Handling interaction type=%s", body.get("type"))
    result = handle_interaction(body, bot_token=DISCORD_TOKEN)
    logger.info("Responding with statusCode=%s", result["statusCode"])
    return {
        "statusCode": result["statusCode"],
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result["body"]),
    }

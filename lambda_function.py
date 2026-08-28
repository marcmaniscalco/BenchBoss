"""
AWS Lambda entry point for Discord interactions.

Invoked via a Function URL (AuthType: NONE). Discord signs each request with
Ed25519, which the handler verifies before dispatching.
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

try:
    from snapshot_restore_py import register_after_restore, register_before_snapshot

    @register_before_snapshot
    def _before_snapshot() -> None:
        """All heavy modules are imported at module level; nothing extra needed."""

    @register_after_restore
    def _after_restore() -> None:
        # Discard the boto3 default session so connection pools captured in the
        # snapshot are not reused after the restore.
        boto3.DEFAULT_SESSION = None

except ImportError:
    pass


def _signature_is_valid(raw_body: bytes, signature: str, timestamp: str) -> bool:
    """Verify against Discord's real key, or (QA only) a second test key.

    Discord's private signing key never leaves Discord, so nothing can forge
    a valid signature for DISCORD_PUBLIC_KEY. TEST_PUBLIC_KEY is a QA-only
    keypair we hold both halves of, letting automated integration tests sign
    real requests and exercise this exact verification path. Read from the
    environment per call (rather than frozen at import like the keys above)
    so it's trivial to flip in tests without reloading the module; Prod never
    sets it, so this is always empty and inert there.
    """
    if verify_signature(raw_body, signature, timestamp, DISCORD_PUBLIC_KEY):
        return True
    test_public_key = os.environ.get("TEST_PUBLIC_KEY", "")
    return bool(test_public_key) and verify_signature(
        raw_body, signature, timestamp, test_public_key
    )


def lambda_handler(event: dict, context) -> dict:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    signature = headers.get("x-signature-ed25519", "")
    timestamp = headers.get("x-signature-timestamp", "")

    raw_body_str = event.get("body", "")
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body_str)
    else:
        raw_body = raw_body_str.encode()

    if not _signature_is_valid(raw_body, signature, timestamp):
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

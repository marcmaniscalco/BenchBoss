"""AWS Lambda entry point for DynamoDB Stream events."""

import os

import boto3
from aws_lambda_powertools import Logger

from bench_boss.stream_handler import handle_stream_records

logger = Logger(service="bench-boss")

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


def stream_lambda_handler(event: dict, context) -> None:
    records = event.get("Records", [])
    logger.info("Processing %d stream record(s)", len(records))
    handle_stream_records(records, bot_token=DISCORD_TOKEN)
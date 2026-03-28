"""AWS Lambda entry point for DynamoDB Stream events."""

import os

from aws_lambda_powertools import Logger

from bench_boss.stream_handler import handle_stream_records

logger = Logger(service="bench-boss")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]


def stream_lambda_handler(event: dict, context) -> None:
    records = event.get("Records", [])
    logger.info("Processing %d stream record(s)", len(records))
    handle_stream_records(records, bot_token=DISCORD_TOKEN)
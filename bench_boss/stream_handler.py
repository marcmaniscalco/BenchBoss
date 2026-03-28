"""Handles DynamoDB Stream events — used for TTL-based Discord message cleanup."""

import requests
from aws_lambda_powertools import Logger

logger = Logger(service="bench-boss")


def handle_stream_records(records: list[dict], bot_token: str) -> None:
    """Process a batch of DynamoDB stream records."""
    for record in records:
        _handle_record(record, bot_token)


def _handle_record(record: dict, bot_token: str) -> None:
    if record.get("eventName") != "REMOVE":
        return
    # Only act on TTL-triggered deletions, not manual bot deletes
    if record.get("userIdentity", {}).get("type") != "Service":
        return

    old = record.get("dynamodb", {}).get("OldImage", {})
    event_key = old.get("event_key", {}).get("S", "<unknown>")
    channel_id = old.get("channel_id", {}).get("S")
    message_id = old.get("message_id", {}).get("S")

    if not channel_id or not message_id:
        logger.info(
            "TTL expiration for event %s has no message ref — skipping Discord delete",
            event_key,
        )
        return

    resp = requests.delete(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
        headers={"Authorization": f"Bot {bot_token}"},
    )
    if resp.ok:
        logger.info(
            "Deleted Discord message %s in channel %s on TTL expiry of event %s",
            message_id,
            channel_id,
            event_key,
        )
    else:
        logger.warning(
            "Failed to delete Discord message for event %s: %s %s",
            event_key,
            resp.status_code,
            resp.text,
        )
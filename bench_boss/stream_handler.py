"""Handles DynamoDB Stream events — used for TTL-based Discord message cleanup."""

import uuid
from datetime import UTC, datetime

import requests
from aws_lambda_powertools import Logger

from bench_boss.calendar import WebCalReader
from bench_boss.discord_api import build_event_embed, build_rsvp_components
from bench_boss.dynamo import save_event, store_message_ref

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
    webcal_url = old.get("webcal_url", {}).get("S")
    guild_id = old.get("guild_id", {}).get("S")

    if not channel_id or not message_id:
        logger.info(
            "TTL expiration for event %s has no message ref — skipping Discord delete",
            event_key,
        )
        return

    if webcal_url:
        _post_next_event(channel_id, webcal_url, guild_id, bot_token)

    _delete_discord_message(channel_id, message_id, bot_token)


def _post_next_event(
    channel_id: str, webcal_url: str, guild_id: str | None, bot_token: str
) -> None:
    try:
        events = WebCalReader(webcal_url).get_remaining()
    except Exception as e:
        logger.error("Failed to fetch calendar %s: %s", webcal_url, e)
        return

    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    if not events:
        resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json={"content": f"No more events at: {webcal_url}"},
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            logger.warning(
                "Failed to post no-more-events message: %s %s",
                resp.status_code,
                resp.text,
            )
        return

    ev = events[0]
    new_event_key = str(uuid.uuid4())

    try:
        save_event(
            event_key=new_event_key,
            name=ev.summary,
            start=_to_iso(ev.start),
            end=_to_iso(ev.end) if ev.end else None,
            location=ev.location,
            description=ev.description,
            guild_id=guild_id,
            webcal_url=webcal_url,
        )
    except Exception as e:
        logger.error("Failed to save next event %r: %s", ev.summary, e)
        return

    embed = build_event_embed(
        name=ev.summary,
        start=ev.start,
        end=ev.end,
        location=ev.location,
        description=ev.description,
        accepted=[],
        declined=[],
        tentative=[],
    )
    components = build_rsvp_components(new_event_key)

    resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        json={"embeds": [embed], "components": components},
        headers=headers,
        timeout=10,
    )
    if resp.ok:
        new_message_id = resp.json().get("id")
        if new_message_id:
            store_message_ref(new_event_key, channel_id, new_message_id)
        logger.info("Posted next event %r (key=%s)", ev.summary, new_event_key)
    else:
        logger.warning(
            "Failed to post next event message: %s %s", resp.status_code, resp.text
        )


def _delete_discord_message(channel_id: str, message_id: str, bot_token: str) -> None:
    resp = requests.delete(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
        headers={"Authorization": f"Bot {bot_token}"},
        timeout=10,
    )
    if resp.ok:
        logger.info(
            "Deleted Discord message %s in channel %s", message_id, channel_id
        )
    else:
        logger.warning(
            "Failed to delete Discord message %s: %s %s",
            message_id,
            resp.status_code,
            resp.text,
        )


def _to_iso(dt) -> str:
    if isinstance(dt, datetime):
        if not dt.tzinfo:
            return dt.replace(tzinfo=UTC).isoformat()
        return dt.isoformat()
    return dt.isoformat()  # date object

"""Handles DynamoDB Stream events — used for TTL-based Discord message cleanup."""

import logging
import uuid
from datetime import UTC, datetime

import requests

from bench_boss.calendar import WebCalReader
from bench_boss.discord_api import (
    build_event_embed,
    build_no_events_embed,
    build_rsvp_components,
)
from bench_boss.dynamo import save_event

logger = logging.getLogger(__name__)


def handle_stream_records(records: list[dict], bot_token: str) -> None:
    """Process a batch of DynamoDB stream records."""
    for record in records:
        _handle_record(record, bot_token)


def _handle_record(record: dict, bot_token: str) -> None:
    event_name = record.get("eventName")
    user_identity = record.get("userIdentity", {})
    logger.info("Stream record raw: %s", record)

    if event_name != "REMOVE":
        logger.debug("Skipping non-REMOVE event: %s", event_name)
        return

    # Only act on TTL-triggered deletions, not manual bot deletes.
    # The DynamoDB Streams API returns "Type" (capital T) for TTL expirations.
    identity_type = user_identity.get("Type") or user_identity.get("type")
    if identity_type != "Service":
        logger.info(
            "Skipping REMOVE — not a TTL expiration (userIdentity.Type=%r)",
            identity_type,
        )
        return

    old = record.get("dynamodb", {}).get("OldImage", {})
    event_key = old.get("event_key", {}).get("S", "<unknown>")
    channel_id = old.get("channel_id", {}).get("S")
    message_id = old.get("message_id", {}).get("S")
    webcal_url = old.get("webcal_url", {}).get("S")
    guild_id = old.get("guild_id", {}).get("S")

    logger.info(
        "TTL expiration: event_key=%s channel_id=%s message_id=%s "
        "webcal_url=%s guild_id=%s",
        event_key,
        channel_id,
        message_id,
        webcal_url,
        guild_id,
    )

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
    """Post the next upcoming event after the current one's TTL expires.

    Message creation and the DB row are ordered message-first, same as
    bot.py's `_handle_schedule` and for the same reason — see that
    function's docstring. The DB row is only written once the channel post
    has actually succeeded and we have a real message_id for it, so a slow
    or interrupted Lambda invocation can no longer leave a row with no
    message behind it. If the post succeeds but the DB write then fails,
    the just-posted message is rolled back.
    """
    try:
        events = WebCalReader(webcal_url).get_remaining()
    except Exception as e:
        logger.error("Failed to fetch calendar %s: %s", webcal_url, e)
        return

    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    if not events:
        resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json={"embeds": [build_no_events_embed()]},
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

    try:
        resp = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json={"embeds": [embed], "components": components},
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        logger.error("Error posting next event message: %s", e)
        return
    if not resp.ok:
        logger.warning(
            "Failed to post next event message: %s %s", resp.status_code, resp.text
        )
        return

    try:
        new_message_id = resp.json().get("id")
    except ValueError as e:
        logger.error("Next event message posted but response wasn't JSON: %s", e)
        return
    if not new_message_id:
        logger.error(
            "Next event message posted to %s but response had no id", channel_id
        )
        return

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
            channel_id=channel_id,
            message_id=new_message_id,
        )
        logger.info("Posted next event %r (key=%s)", ev.summary, new_event_key)
    except Exception as e:
        logger.error("Failed to save next event %r: %s", ev.summary, e)
        # Best-effort rollback — don't leave a posted message with no DB
        # row behind it; see bot.py's _handle_schedule for why.
        if not _delete_discord_message(channel_id, new_message_id, bot_token):
            logger.warning(
                "Rollback delete failed — message %s in channel %s is now "
                "orphaned (no DB row) and needs manual cleanup",
                new_message_id,
                channel_id,
            )


def _delete_discord_message(channel_id: str, message_id: str, bot_token: str) -> bool:
    """Delete a Discord message using the bot token; return whether it worked."""
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
    logger.info("Deleting Discord message: DELETE %s", url)
    try:
        resp = requests.delete(
            url,
            headers={"Authorization": f"Bot {bot_token}"},
            timeout=10,
        )
    except Exception as e:
        logger.error("Error deleting Discord message %s: %s", message_id, e)
        return False
    logger.debug(
        "Discord DELETE response: status=%s body=%s", resp.status_code, resp.text
    )
    if resp.ok:
        logger.info("Deleted Discord message %s in channel %s", message_id, channel_id)
        return True
    logger.warning(
        "Failed to delete Discord message %s: %s %s",
        message_id,
        resp.status_code,
        resp.text,
    )
    return False


def _to_iso(dt) -> str:
    if isinstance(dt, datetime):
        if not dt.tzinfo:
            return dt.replace(tzinfo=UTC).isoformat()
        return dt.isoformat()
    return dt.isoformat()  # date object

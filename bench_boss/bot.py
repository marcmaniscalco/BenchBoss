"""
Core bot logic — shared between local dev server and Lambda.
"""

import threading
import time
import uuid
from datetime import UTC, datetime

import requests
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from bench_boss.calendar import WebCalReader
from bench_boss.discord_api import build_event_embed, build_rsvp_components
from bench_boss.dynamo import delete_event, save_event, update_rsvp

# Interaction types
PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3

# Response types
PONG = 1
CHANNEL_MESSAGE_WITH_SOURCE = 4
DEFERRED_UPDATE_MESSAGE = 6
UPDATE_MESSAGE = 7


def verify_signature(
    raw_body: bytes, signature: str, timestamp: str, public_key: str
) -> bool:
    """Verify the request came from Discord using Ed25519."""
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))
        verify_key.verify(timestamp.encode() + raw_body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, Exception):
        return False


def handle_interaction(body: dict, bot_token: str = "") -> dict:
    """Route an interaction and return an HTTP response dict."""
    interaction_type = body.get("type")

    if interaction_type == PING:
        return {"statusCode": 200, "body": {"type": PONG}}

    if interaction_type == APPLICATION_COMMAND:
        command = body.get("data", {}).get("name")

        if command == "ping":
            return {
                "statusCode": 200,
                "body": {
                    "type": CHANNEL_MESSAGE_WITH_SOURCE,
                    "data": {"content": "Pong!"},
                },
            }

        if command == "schedule":
            options = {
                o["name"]: o["value"] for o in body.get("data", {}).get("options", [])
            }
            return _handle_schedule(options.get("url", ""))

        return {
            "statusCode": 200,
            "body": {
                "type": CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"content": f"Unknown command `/{command}`"},
            },
        }

    if interaction_type == MESSAGE_COMPONENT:
        custom_id = body.get("data", {}).get("custom_id", "")
        if custom_id.startswith("delete:"):
            return _handle_delete(body, bot_token)
        return _handle_rsvp(body)

    return {"statusCode": 400, "body": {"error": "Unhandled interaction type"}}


def _ensure_utc_iso(dt: datetime) -> str:
    if not dt.tzinfo:
        return dt.replace(tzinfo=UTC).isoformat()
    return dt.isoformat()


def _handle_schedule(webcal_url: str) -> dict:
    if not webcal_url:
        return _message("No calendar URL provided.")

    try:
        events = WebCalReader(webcal_url).get_upcoming(days=365)
    except Exception as e:
        return _message(f"Failed to fetch calendar: {e}")

    if not events:
        return _message("No upcoming events found in the calendar.")

    ev = events[0]
    event_key = str(uuid.uuid4())

    try:
        save_event(
            event_key=event_key,
            name=ev.summary,
            start=_ensure_utc_iso(ev.start),
            end=_ensure_utc_iso(ev.end) if ev.end else None,
            location=ev.location,
            description=ev.description,
        )
    except Exception as e:
        return _message(f"Failed to save event: {e}")

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
    components = build_rsvp_components(event_key)

    return {
        "statusCode": 200,
        "body": {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"embeds": [embed], "components": components},
        },
    }


def _handle_rsvp(body: dict) -> dict:
    custom_id = body.get("data", {}).get("custom_id", "")
    parts = custom_id.split(":")
    if len(parts) != 3 or parts[0] != "rsvp":
        return {"statusCode": 400, "body": {"error": "Invalid component ID"}}

    _, action, event_key = parts
    member = body.get("member") or {}
    user_id = member.get("user", {}).get("id") or body.get("user", {}).get("id", "")

    try:
        event = update_rsvp(event_key, user_id, action)
    except ValueError:
        return _message("Event not found.")
    except Exception as e:
        return _message(f"Failed to update RSVP: {e}")

    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"]) if event.get("end") else None

    embed = build_event_embed(
        name=event["name"],
        start=start,
        end=end,
        location=event.get("location"),
        description=event.get("description"),
        accepted=event.get("accepted", []),
        declined=event.get("declined", []),
        tentative=event.get("tentative", []),
    )
    components = build_rsvp_components(event_key)

    return {
        "statusCode": 200,
        "body": {
            "type": UPDATE_MESSAGE,
            "data": {"embeds": [embed], "components": components},
        },
    }


def _handle_delete(body: dict, bot_token: str) -> dict:
    custom_id = body.get("data", {}).get("custom_id", "")
    event_key = custom_id.split(":", 1)[1]

    try:
        delete_event(event_key)
    except Exception as e:
        return _message(f"Failed to delete event: {e}")

    app_id = body.get("application_id", "")
    token = body.get("token", "")
    if app_id and token:
        threading.Thread(
            target=_delete_original_message,
            args=(app_id, token),
            daemon=True,
        ).start()

    # Acknowledge the interaction immediately (type 6 = DEFERRED_UPDATE_MESSAGE).
    # The background thread deletes the message after the callback is sent.
    return {"statusCode": 200, "body": {"type": DEFERRED_UPDATE_MESSAGE}}


def _delete_original_message(app_id: str, token: str) -> None:
    """Delete the original event message after the interaction callback has been sent."""
    time.sleep(0.5)
    requests.delete(
        f"https://discord.com/api/v10/webhooks/{app_id}/{token}/messages/@original",
    )


def _message(content: str) -> dict:
    return {
        "statusCode": 200,
        "body": {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": {"content": content}},
    }

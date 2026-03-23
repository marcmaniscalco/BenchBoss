"""
Core bot logic — shared between local dev server and Lambda.
"""

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from bench_boss.calendar import WebCalReader
from bench_boss.discord_api import create_scheduled_event

# Interaction types
PING = 1
APPLICATION_COMMAND = 2

# Response types
PONG = 1
CHANNEL_MESSAGE_WITH_SOURCE = 4


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
            guild_id = body.get("guild_id", "")
            return _handle_schedule(options.get("url", ""), guild_id, bot_token)

        return {
            "statusCode": 200,
            "body": {
                "type": CHANNEL_MESSAGE_WITH_SOURCE,
                "data": {"content": f"Unknown command `/{command}`"},
            },
        }

    return {"statusCode": 400, "body": {"error": "Unhandled interaction type"}}


def _handle_schedule(webcal_url: str, guild_id: str, bot_token: str) -> dict:
    if not webcal_url:
        return _message("No calendar URL provided.")

    try:
        events = WebCalReader(webcal_url).get_upcoming(days=365)
    except Exception as e:
        return _message(f"Failed to fetch calendar: {e}")

    if not events:
        return _message("No upcoming events found in the calendar.")

    next_event = events[0]

    try:
        created = create_scheduled_event(
            guild_id=guild_id,
            name=next_event.summary,
            start=next_event.start,
            end=next_event.end,
            location=next_event.location,
            bot_token=bot_token,
        )
    except Exception as e:
        return _message(f"Failed to create Discord event: {e}")

    event_url = f"https://discord.com/events/{guild_id}/{created['id']}"
    return _message(f"Created event **{created['name']}** — {event_url}")


def _message(content: str) -> dict:
    return {
        "statusCode": 200,
        "body": {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": {"content": content}},
    }

"""
Core bot logic.
"""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from nacl.signing import VerifyKey

from bench_boss.calendar import WebCalReader
from bench_boss.constants import FULLTIME_ROLE_ID, TEAM_TIMEZONE
from bench_boss.discord_api import (
    build_add_rsvp_modal,
    build_delete_confirm_buttons,
    build_event_embed,
    build_event_modal,
    build_remove_rsvp_modal,
    build_retry_button,
    build_rsvp_components,
)
from bench_boss.dynamo import (
    RSVP_ACTIONS,
    delete_event,
    find_event_in_channel,
    get_draft_event,
    get_event,
    remove_rsvp,
    save_draft_event,
    save_event,
    set_goalie,
    set_rsvp,
    store_interaction_ref,
    store_message_ref,
    update_event,
    update_rsvp,
)

logger = logging.getLogger(__name__)

# Interaction types
PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3
MODAL_SUBMIT = 5

# Response types
PONG = 1
CHANNEL_MESSAGE_WITH_SOURCE = 4
DEFERRED_UPDATE_MESSAGE = 6
UPDATE_MESSAGE = 7
MODAL = 9

_ACTION_ALIASES = {"a": "accepted", "d": "declined", "t": "tentative", "g": "goalie"}


def _has_fulltime_role(roles: list) -> bool:
    return FULLTIME_ROLE_ID in roles


_ADMINISTRATOR = 1 << 3


def _is_admin(body: dict) -> bool:
    """Return True if the interacting member has the Administrator permission."""
    permissions = body.get("member", {}).get("permissions", "0")
    try:
        return bool(int(permissions) & _ADMINISTRATOR)
    except (ValueError, TypeError):
        return False


def _get_user_id(body: dict) -> str:
    """Extract the interacting user's ID from a guild member or DM context."""
    member = body.get("member") or {}
    user_data = member.get("user") or body.get("user") or {}
    return user_data.get("id", "")


def verify_signature(
    raw_body: bytes, signature: str, timestamp: str, public_key: str
) -> bool:
    """Verify the request came from Discord using Ed25519."""
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))
        verify_key.verify(timestamp.encode() + raw_body, bytes.fromhex(signature))
        return True
    except Exception:
        logger.warning("Signature verification failed")
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
            return _handle_schedule(
                options.get("url", ""),
                guild_id=body.get("guild_id"),
                channel_id=body.get("channel_id", ""),
            )

        if command == "events":
            options = {
                o["name"]: o["value"] for o in body.get("data", {}).get("options", [])
            }
            return _handle_events(options.get("url", ""), body, bot_token)

        if command == "create-event":
            return {
                "statusCode": 200,
                "body": {"type": MODAL, "data": build_event_modal()},
            }

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
            return _handle_delete(body)
        if custom_id.startswith("delete_confirm:"):
            return _handle_delete_confirm(body, bot_token)
        if custom_id.startswith("delete_cancel:"):
            return _handle_delete_cancel()
        if custom_id.startswith("add_rsvp:"):
            return _handle_add_rsvp_button(body)
        if custom_id.startswith("remove_rsvp:"):
            return _handle_remove_rsvp_button(body)
        if custom_id.startswith("goalie_rsvp:"):
            return _handle_goalie_rsvp(body)
        if custom_id.startswith("edit_event:"):
            return _handle_edit_event_button(body)
        if custom_id.startswith("retry_event_modal:"):
            return _handle_retry_event_modal_button(body)
        return _handle_rsvp(body)

    if interaction_type == MODAL_SUBMIT:
        custom_id = body.get("data", {}).get("custom_id", "")
        if custom_id.startswith("add_rsvp_modal:") or custom_id.startswith(
            "remove_rsvp_modal:"
        ):
            return _handle_rsvp_edit_submit(body, bot_token)
        if custom_id == "create_event_modal":
            return _handle_create_event_submit(body)
        if custom_id.startswith("edit_event_modal:"):
            return _handle_edit_event_submit(body, bot_token)
        return {"statusCode": 400, "body": {"error": "Unhandled modal submission"}}

    return {"statusCode": 400, "body": {"error": "Unhandled interaction type"}}


def _ensure_utc_iso(dt: datetime) -> str:
    if not dt.tzinfo:
        return dt.replace(tzinfo=UTC).isoformat()
    return dt.isoformat()


def _handle_schedule(
    webcal_url: str,
    guild_id: str | None = None,
    channel_id: str = "",
) -> dict:
    if not webcal_url:
        return _message("No calendar URL provided.")

    try:
        events = WebCalReader(webcal_url).get_upcoming(days=365)
    except Exception as e:
        logger.error("Failed to fetch calendar %s: %s", webcal_url, e)
        return _message(f"Failed to fetch calendar: {e}")

    if not events:
        logger.info("No upcoming events found for %s", webcal_url)
        return _message("No upcoming events found in the calendar.")

    ev = events[0]
    start_iso = _ensure_utc_iso(ev.start)

    if channel_id:
        try:
            existing = find_event_in_channel(channel_id, ev.summary, start_iso)
        except Exception as e:
            logger.error("Duplicate check failed: %s", e)
            existing = None
        if existing:
            return _ephemeral(f"**{ev.summary}** is already posted in this channel.")

    event_key = str(uuid.uuid4())

    try:
        save_event(
            event_key=event_key,
            name=ev.summary,
            start=start_iso,
            end=_ensure_utc_iso(ev.end) if ev.end else None,
            location=ev.location,
            description=ev.description,
            guild_id=guild_id,
            webcal_url=webcal_url,
            channel_id=channel_id or None,
        )
        logger.info("Scheduled event %r (key=%s)", ev.summary, event_key)
    except Exception as e:
        logger.error("Failed to save event: %s", e)
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
        goalie=[],
    )
    components = build_rsvp_components(event_key)

    # Note: we don't store (channel_id, message_id) here because we don't
    # know the message_id yet — Discord assigns it when it posts the embed
    # in response to this interaction. On Lambda we can't fire-and-forget a
    # follow-up fetch (the execution environment freezes when the handler
    # returns). Instead, message_id is captured lazily on the first RSVP
    # button click via store_message_ref(...) in the button handlers.
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
    user_data = member.get("user") or body.get("user") or {}
    user_id = user_data.get("id", "")
    display_name = (
        member.get("nick")
        or user_data.get("global_name")
        or user_data.get("username")
        or None
    )
    if (
        member
        and display_name is not None
        and not _has_fulltime_role(member.get("roles", []))
    ):
        display_name = display_name + "*"

    try:
        event = update_rsvp(event_key, user_id, action, display_name)
        logger.info("RSVP %s for event %s by user %s", action, event_key, user_id)
    except ValueError:
        logger.warning("RSVP failed — event not found: %s", event_key)
        return _message("Event not found.")
    except Exception as e:
        logger.error("Failed to update RSVP for event %s: %s", event_key, e)
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
        names=event.get("member_names") or {},
        goalie=event.get("goalie", []),
    )
    components = build_rsvp_components(event_key)

    return {
        "statusCode": 200,
        "body": {
            "type": UPDATE_MESSAGE,
            "data": {"embeds": [embed], "components": components},
        },
    }


def _handle_delete(body: dict) -> dict:
    if not _is_admin(body):
        return _ephemeral("You don't have permission to delete events.")

    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    channel_id = body.get("channel_id", "")
    message_id = body.get("message", {}).get("id", "")

    components = build_delete_confirm_buttons(event_key, channel_id, message_id)
    return {
        "statusCode": 200,
        "body": {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {
                "content": "Are you sure you want to delete this event?",
                "components": components,
                "flags": 64,
            },
        },
    }


def _handle_delete_confirm(body: dict, bot_token: str) -> dict:
    if not _is_admin(body):
        return _ephemeral("You don't have permission to delete events.")

    # custom_id format: delete_confirm:{event_key}:{channel_id}:{message_id}
    parts = body.get("data", {}).get("custom_id", "").split(":", 3)
    if len(parts) != 4:
        return _ephemeral("Invalid delete confirmation.")
    _, event_key, channel_id, message_id = parts

    try:
        delete_event(event_key)
        logger.info("Deleted event %s", event_key)
    except ValueError:
        logger.debug(
            "Event %s not found in DB, continuing with message deletion", event_key
        )
    except Exception as e:
        logger.error("Failed to delete event %s: %s", event_key, e)
        return _ephemeral(f"Failed to delete event: {e}")

    if channel_id and message_id and bot_token:
        _delete_channel_message(channel_id, message_id, bot_token)

    return {
        "statusCode": 200,
        "body": {
            "type": UPDATE_MESSAGE,
            "data": {"content": "Event deleted.", "components": []},
        },
    }


def _handle_delete_cancel() -> dict:
    return {
        "statusCode": 200,
        "body": {
            "type": UPDATE_MESSAGE,
            "data": {"content": "Deletion cancelled.", "components": []},
        },
    }


def _store_button_refs(body: dict, event_key: str) -> None:
    """Persist the channel/message IDs and interaction token from a button click."""
    channel_id = body.get("channel_id", "")
    message_id = body.get("message", {}).get("id", "")
    if channel_id and message_id:
        store_message_ref(event_key, channel_id, message_id)
    else:
        logger.warning(
            "Button interaction missing channel_id or message_id for event %s",
            event_key,
        )
    interaction_token = body.get("token", "")
    app_id = body.get("application_id", "")
    if interaction_token and app_id:
        store_interaction_ref(event_key, interaction_token, app_id)


def _handle_add_rsvp_button(body: dict) -> dict:
    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    _store_button_refs(body, event_key)
    return {
        "statusCode": 200,
        "body": {"type": MODAL, "data": build_add_rsvp_modal(event_key)},
    }


def _handle_remove_rsvp_button(body: dict) -> dict:
    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    _store_button_refs(body, event_key)
    return {
        "statusCode": 200,
        "body": {"type": MODAL, "data": build_remove_rsvp_modal(event_key)},
    }


def _handle_edit_event_button(body: dict) -> dict:
    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    event = get_event(event_key)
    if event is None:
        return _ephemeral("Event not found.")

    is_creator = bool(event.get("created_by")) and event["created_by"] == _get_user_id(
        body
    )
    if not _is_admin(body) and not is_creator:
        return _ephemeral("You don't have permission to edit this event.")

    _store_button_refs(body, event_key)

    start = datetime.fromisoformat(event["start"])
    end = datetime.fromisoformat(event["end"]) if event.get("end") else None
    duration = str(int((end - start).total_seconds() // 60)) if end else ""

    prefill = {
        "name": event["name"],
        "datetime": _format_event_datetime(start),
        "duration": duration,
        "location": event.get("location", ""),
        "description": event.get("description", ""),
    }

    return {
        "statusCode": 200,
        "body": {
            "type": MODAL,
            "data": build_event_modal(event_key, prefill=prefill),
        },
    }


def _handle_retry_event_modal_button(body: dict) -> dict:
    """Reopen a create/edit-event modal from a validation-failure message's
    "Fix and Retry" button, prefilled with what was previously submitted."""
    draft_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    draft = get_draft_event(draft_key)
    if draft is None:
        return _ephemeral("This retry has expired — run the command again.")

    return {
        "statusCode": 200,
        "body": {
            "type": MODAL,
            "data": build_event_modal(
                draft.get("target_event_key"),
                prefill=draft["fields"],
                error_field=draft["error_field"],
                error_message=draft["error_message"],
            ),
        },
    }


def _handle_goalie_rsvp(body: dict) -> dict:
    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    member = body.get("member") or {}
    user_data = member.get("user") or body.get("user") or {}
    user_id = user_data.get("id", "")
    display_name = (
        member.get("nick")
        or user_data.get("global_name")
        or user_data.get("username")
        or None
    )
    if (
        member
        and display_name is not None
        and not _has_fulltime_role(member.get("roles", []))
    ):
        display_name = display_name + "*"

    event = get_event(event_key)
    if event is None:
        return _message("Event not found.")
    current_goalie = event.get("goalie", [])
    if current_goalie and user_id not in current_goalie:
        names_map = event.get("member_names") or {}
        existing = names_map.get(current_goalie[0]) or f"<@{current_goalie[0]}>"
        return _ephemeral(
            f"**{existing}** is already the goalie. "
            "Remove them first before adding a new one."
        )

    try:
        event = set_goalie(event_key, user_id, display_name)
        logger.info("Goalie RSVP for event %s by user %s", event_key, user_id)
    except ValueError:
        logger.warning("Goalie RSVP failed — event not found: %s", event_key)
        return _message("Event not found.")
    except Exception as e:
        logger.error("Failed to update goalie for event %s: %s", event_key, e)
        return _message(f"Failed to update goalie: {e}")

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
        names=event.get("member_names") or {},
        goalie=event.get("goalie", []),
    )
    components = build_rsvp_components(event_key)

    return {
        "statusCode": 200,
        "body": {
            "type": UPDATE_MESSAGE,
            "data": {"embeds": [embed], "components": components},
        },
    }


def _parse_user_id(value: str) -> str | None:
    """Extract a numeric Discord user ID from a mention (<@123>) or raw ID string."""
    value = value.strip()
    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1].lstrip("!")
    return value if value.isdigit() else None


_EVENT_DATETIME_FORMAT = "%Y-%m-%d %I:%M %p"


def _parse_event_datetime(raw: str) -> datetime | None:
    """Parse a 'YYYY-MM-DD H:MM AM/PM' string into a TEAM_TIMEZONE-aware datetime."""
    try:
        naive = datetime.strptime(raw.strip(), _EVENT_DATETIME_FORMAT)
    except ValueError:
        return None
    return naive.replace(tzinfo=ZoneInfo(TEAM_TIMEZONE))


def _format_event_datetime(dt: datetime) -> str:
    """Format a datetime back into the modal's expected input string."""
    return dt.astimezone(ZoneInfo(TEAM_TIMEZONE)).strftime(_EVENT_DATETIME_FORMAT)


def _parse_duration_minutes(raw: str) -> int | None:
    """Parse a positive integer number of minutes, or None if invalid."""
    try:
        minutes = int(raw.strip())
    except ValueError:
        return None
    return minutes if minutes > 0 else None


def _extract_modal_fields(body: dict) -> dict:
    """Flatten a modal submission's nested action-row components into a dict."""
    return {
        comp["custom_id"]: comp["value"]
        for row in body.get("data", {}).get("components", [])
        for comp in row.get("components", [])
    }


def _parse_event_modal_fields(
    fields: dict,
) -> tuple[dict | None, str | None, str | None]:
    """
    Validate and parse the create/edit event modal fields.

    Returns (parsed, None, None) on success, where parsed has keys
    name/start/end/location/description, or (None, error_message,
    error_field) on validation failure, where error_field is the
    custom_id of the input that failed validation.
    """
    name = fields.get("name", "").strip()
    if not name:
        return None, "Title is required.", "name"

    start = _parse_event_datetime(fields.get("datetime", ""))
    if start is None:
        return (
            None,
            "Could not parse date/time — use format YYYY-MM-DD H:MM AM/PM "
            "(e.g. 2026-08-30 7:00 PM).",
            "datetime",
        )

    duration = _parse_duration_minutes(fields.get("duration", ""))
    if duration is None:
        return None, "Duration must be a positive number of minutes.", "duration"

    end = start + timedelta(minutes=duration)
    location = fields.get("location", "").strip() or None
    description = fields.get("description", "").strip() or None

    return (
        {
            "name": name,
            "start": start,
            "end": end,
            "location": location,
            "description": description,
        },
        None,
        None,
    )


def _search_guild_member(guild_id: str, query: str, bot_token: str) -> str | None:
    """Search a guild for a member by username. Returns the user ID or None."""
    resp = requests.get(
        f"https://discord.com/api/v10/guilds/{guild_id}/members/search",
        params={"query": query, "limit": 1},
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    if not resp.ok:
        logger.warning("Guild member search failed for %r: %s", query, resp.status_code)
        return None
    members = resp.json()
    return members[0]["user"]["id"] if members else None


def _fetch_guild_member(guild_id: str, user_id: str, bot_token: str) -> dict | None:
    """Fetch the raw guild member object from the Discord API."""
    resp = requests.get(
        f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}",
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        },
        timeout=10,
    )
    if not resp.ok:
        logger.warning(
            "Failed to fetch member %s from guild %s: %s",
            user_id,
            guild_id,
            resp.status_code,
        )
        return None
    return resp.json()


def _fetch_member_display_name(
    guild_id: str, user_id: str, bot_token: str
) -> str | None:
    """Fetch a guild member's display name (server nick > global name > username)."""
    member = _fetch_guild_member(guild_id, user_id, bot_token)
    if member is None:
        return None
    return (
        member.get("nick")
        or member.get("user", {}).get("global_name")
        or member.get("user", {}).get("username")
        or None
    )


def _handle_rsvp_edit_submit(body: dict, bot_token: str) -> dict:
    custom_id = body.get("data", {}).get("custom_id", "")
    modal_type, event_key = custom_id.split(":", 1)

    fields = _extract_modal_fields(body)

    raw_user = fields.get("user", "").strip()
    user_id = _parse_user_id(raw_user)

    if not user_id:
        event = get_event(event_key)
        guild_id = event.get("guild_id") if event else None
        if guild_id and bot_token:
            user_id = _search_guild_member(guild_id, raw_user, bot_token)
        if not user_id:
            return _ephemeral(
                "Could not find that user — try again with their "
                "@mention or numeric ID."
            )

    guild_id = body.get("guild_id")
    guild_member = (
        _fetch_guild_member(guild_id, user_id, bot_token)
        if guild_id and bot_token
        else None
    )
    display_name = (
        (
            guild_member.get("nick")
            or guild_member.get("user", {}).get("global_name")
            or guild_member.get("user", {}).get("username")
            or None
        )
        if guild_member
        else None
    )
    if (
        guild_member is not None
        and display_name is not None
        and not _has_fulltime_role(guild_member.get("roles", []))
    ):
        display_name = display_name + "*"

    if modal_type == "add_rsvp_modal":
        action = fields.get("action", "").strip().lower()
        action = _ACTION_ALIASES.get(action, action)
        if action == "goalie":
            event = get_event(event_key)
            if event is None:
                return _ephemeral("Event not found.")
            current_goalie = event.get("goalie", [])
            if user_id in current_goalie:
                return _ephemeral("You're already the goalie — only one is needed!")
            if current_goalie:
                names_map = event.get("member_names") or {}
                existing = names_map.get(current_goalie[0]) or f"<@{current_goalie[0]}>"
                return _ephemeral(
                    f"**{existing}** is already the goalie. "
                    "Remove them first before adding a new one."
                )
            try:
                event = set_goalie(event_key, user_id, display_name)
            except ValueError:
                return _ephemeral("Event not found.")
            except Exception as e:
                logger.error("Failed to set goalie for event %s: %s", event_key, e)
                return _ephemeral(f"Failed to update goalie: {e}")
            if bot_token:
                _update_channel_message(event, bot_token)
            return _ephemeral(f"Added **{display_name or user_id}** as goalie.")
        if action not in RSVP_ACTIONS:
            return _ephemeral(
                "Invalid RSVP status — use: accepted, declined, tentative, or goalie."
            )
        try:
            event = set_rsvp(event_key, user_id, action, display_name)
        except ValueError:
            return _ephemeral("Event not found.")
        except Exception as e:
            logger.error("Failed to add RSVP for event %s: %s", event_key, e)
            return _ephemeral(f"Failed to update RSVP: {e}")
        if bot_token:
            _update_channel_message(event, bot_token)
        return _ephemeral(f"Added **{display_name or user_id}** as **{action}**.")

    # remove_rsvp_modal
    try:
        event = remove_rsvp(event_key, user_id)
    except ValueError as e:
        return _ephemeral(str(e))
    except Exception as e:
        logger.error("Failed to remove RSVP for event %s: %s", event_key, e)
        return _ephemeral(f"Failed to remove RSVP: {e}")
    if bot_token:
        _update_channel_message(event, bot_token)
    return _ephemeral(f"Removed **{display_name or user_id}** from the RSVP.")


def _reject_event_modal(
    fields: dict, error: str, error_field: str, target_event_key: str | None
) -> dict:
    """
    Stash a failed create/edit-event submission and respond with an
    ephemeral error message plus a "Fix and Retry" button. Discord does
    not allow responding to a MODAL_SUBMIT interaction with a MODAL, so
    the modal can only be reopened from a fresh button-click interaction.
    """
    draft_key = str(uuid.uuid4())
    save_draft_event(draft_key, fields, error_field, error, target_event_key)
    return {
        "statusCode": 200,
        "body": {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {
                "content": f"❌ {error}",
                "flags": 64,
                "components": build_retry_button(draft_key),
            },
        },
    }


def _handle_create_event_submit(body: dict) -> dict:
    fields = _extract_modal_fields(body)
    parsed, error, error_field = _parse_event_modal_fields(fields)
    if error:
        return _reject_event_modal(fields, error, error_field, None)

    event_key = str(uuid.uuid4())

    try:
        save_event(
            event_key=event_key,
            name=parsed["name"],
            start=_ensure_utc_iso(parsed["start"]),
            end=_ensure_utc_iso(parsed["end"]),
            location=parsed["location"],
            description=parsed["description"],
            guild_id=body.get("guild_id"),
            channel_id=body.get("channel_id") or None,
            created_by=_get_user_id(body) or None,
        )
        logger.info("Created event %r (key=%s)", parsed["name"], event_key)
    except Exception as e:
        logger.error("Failed to save event: %s", e)
        return _ephemeral(f"Failed to create event: {e}")

    embed = build_event_embed(
        name=parsed["name"],
        start=parsed["start"],
        end=parsed["end"],
        location=parsed["location"],
        description=parsed["description"],
        accepted=[],
        declined=[],
        tentative=[],
        goalie=[],
    )
    components = build_rsvp_components(event_key)

    # message_id is captured lazily on the first button click, same as
    # calendar-sourced events — see the comment in _handle_schedule.
    return {
        "statusCode": 200,
        "body": {
            "type": CHANNEL_MESSAGE_WITH_SOURCE,
            "data": {"embeds": [embed], "components": components},
        },
    }


def _handle_edit_event_submit(body: dict, bot_token: str) -> dict:
    event_key = body.get("data", {}).get("custom_id", "").split(":", 1)[1]
    fields = _extract_modal_fields(body)
    parsed, error, error_field = _parse_event_modal_fields(fields)
    if error:
        return _reject_event_modal(fields, error, error_field, event_key)

    try:
        event = update_event(
            event_key,
            name=parsed["name"],
            start=_ensure_utc_iso(parsed["start"]),
            end=_ensure_utc_iso(parsed["end"]),
            location=parsed["location"],
            description=parsed["description"],
        )
        logger.info("Updated event %s", event_key)
    except ValueError:
        return _ephemeral("Event not found.")
    except Exception as e:
        logger.error("Failed to update event %s: %s", event_key, e)
        return _ephemeral(f"Failed to update event: {e}")

    if bot_token:
        _update_channel_message(event, bot_token)
    return _ephemeral(f"Updated **{parsed['name']}**.")


def _update_channel_message(event: dict, bot_token: str) -> None:
    """PATCH the original channel event message with the current RSVP state."""
    channel_id = event.get("channel_id")
    message_id = event.get("message_id")
    if not channel_id or not message_id:
        logger.warning(
            "Skipping channel update for event %s — no message ref stored "
            "(channel=%r message=%r)",
            event.get("event_key"),
            channel_id,
            message_id,
        )
        return

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
        names=event.get("member_names") or {},
        goalie=event.get("goalie", []),
    )
    event_key = event["event_key"]
    components = build_rsvp_components(event_key)

    if bot_token:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
        }
    else:
        interaction_token = event.get("interaction_token")
        app_id = event.get("app_id")
        if not interaction_token or not app_id:
            logger.warning(
                "Skipping channel update for event %s — no bot token "
                "or interaction token",
                event_key,
            )
            return
        url = f"https://discord.com/api/v10/webhooks/{app_id}/{interaction_token}/messages/{message_id}"
        headers = {"Content-Type": "application/json"}

    resp = requests.patch(
        url,
        json={"embeds": [embed], "components": components},
        headers=headers,
        timeout=10,
    )
    if resp.ok:
        logger.info("Updated channel message for event %s", event_key)
    else:
        logger.warning(
            "Failed to update channel message for event %s: %s %s",
            event_key,
            resp.status_code,
            resp.text,
        )


def _delete_channel_message(channel_id: str, message_id: str, bot_token: str) -> None:
    """Delete an event embed from the channel using the bot token."""
    try:
        resp = requests.delete(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
            headers={
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if not resp.ok:
            logger.warning(
                "Failed to delete channel message %s in channel %s: %s",
                message_id,
                channel_id,
                resp.status_code,
            )
    except Exception as e:
        logger.error(
            "Error deleting channel message %s in channel %s: %s",
            message_id,
            channel_id,
            e,
        )


def _handle_events(webcal_url: str, body: dict, bot_token: str) -> dict:
    if not webcal_url:
        return _ephemeral("No calendar URL provided.")

    member = body.get("member") or {}
    user_id = member.get("user", {}).get("id") or body.get("user", {}).get("id", "")
    if not user_id or not bot_token:
        return _ephemeral("Could not determine your user ID.")

    # Run synchronously: in Lambda the execution environment freezes the
    # moment the handler returns, so a background thread would be paused
    # mid-flight and the DM wouldn't actually go out until the next
    # invocation thaws the environment.
    if _send_dm_events(webcal_url, user_id, bot_token):
        return _ephemeral("Sent you a DM with all events from the calendar.")
    return _ephemeral(
        "Sorry — I couldn't send you the events DM. "
        "Make sure you allow DMs from server members and try again."
    )


def _format_event_line(ev) -> str:
    s = ev.start
    if isinstance(s, datetime):
        date_str = s.strftime("%a, %b %d at %I:%M %p").replace(" 0", " ")
    elif isinstance(s, date):
        date_str = "All day, " + s.strftime("%a, %b %d").replace(" 0", " ")
    else:
        date_str = str(s)
    return f"**{ev.summary}** — {date_str}"


def _send_dm_events(webcal_url: str, user_id: str, bot_token: str) -> bool:
    try:
        events = WebCalReader(webcal_url).get_remaining()
    except Exception as e:
        logger.error("Failed to fetch calendar for events DM: %s", e)
        return False

    if not events:
        content = "No events found in the calendar."
    else:
        lines = ["**Remaining events from calendar:**"]
        for ev in events:
            lines.append(f"• {_format_event_line(ev)}")
        content = "\n".join(lines)
        if len(content) > 2000:
            content = content[:1997] + "..."

    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    dm_resp = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        json={"recipient_id": user_id},
        headers=headers,
        timeout=10,
    )
    if not dm_resp.ok:
        logger.error(
            "Failed to create DM channel for user %s: %s", user_id, dm_resp.status_code
        )
        return False

    channel_id = dm_resp.json().get("id")
    msg_resp = requests.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        json={"content": content},
        headers=headers,
        timeout=10,
    )
    if msg_resp.ok:
        logger.info("Sent events DM to user %s", user_id)
        return True
    logger.error(
        "Failed to send events DM to user %s: %s %s",
        user_id,
        msg_resp.status_code,
        msg_resp.text,
    )
    return False


def _message(content: str, ephemeral: bool = False) -> dict:
    data: dict = {"content": content}
    if ephemeral:
        data["flags"] = 64
    return {
        "statusCode": 200,
        "body": {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": data},
    }


def _ephemeral(content: str) -> dict:
    return _message(content, ephemeral=True)

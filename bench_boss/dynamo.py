"""DynamoDB persistence for event RSVP state."""

import os
from datetime import UTC, datetime, timedelta

import logging

import boto3
from boto3.dynamodb.conditions import Attr

from bench_boss.constants import EVENT_TTL_HOURS

logger = logging.getLogger(__name__)

RSVP_ACTIONS = ("accepted", "declined", "tentative")
GOALIE_ACTION = "goalie"


def _table():
    kwargs = {}
    endpoint = os.environ.get("DYNAMODB_ENDPOINT")
    if not endpoint and os.environ.get("AWS_SAM_LOCAL"):
        endpoint = "http://host.docker.internal:8000"
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = "local"
        kwargs["aws_secret_access_key"] = "local"
        kwargs["aws_session_token"] = None
    return boto3.resource("dynamodb", region_name="us-east-1", **kwargs).Table(
        os.environ["DYNAMODB_TABLE"]
    )


def _ttl_timestamp(end: str | None, start: str) -> int:
    """Return a Unix timestamp 24 hours after end (or start if no end)."""
    base = datetime.fromisoformat(end if end else start)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return int((base + timedelta(hours=EVENT_TTL_HOURS)).timestamp())


def save_event(
    event_key: str,
    name: str,
    start: str,
    end: str | None,
    location: str | None,
    description: str | None,
    guild_id: str | None = None,
    webcal_url: str | None = None,
    channel_id: str | None = None,
) -> None:
    """Persist a new event with empty RSVP lists."""
    logger.debug("Saving event %s (%r)", event_key, name)
    item: dict = {
        "event_key": event_key,
        "name": name,
        "start": start,
        "accepted": [],
        "declined": [],
        "tentative": [],
        "goalie": [],
        "ttl": _ttl_timestamp(end, start),
    }
    if end is not None:
        item["end"] = end
    if location is not None:
        item["location"] = location
    if description is not None:
        item["description"] = description
    if guild_id is not None:
        item["guild_id"] = guild_id
    if webcal_url is not None:
        item["webcal_url"] = webcal_url
    if channel_id is not None:
        item["channel_id"] = channel_id
    _table().put_item(Item=item)


def find_event_in_channel(channel_id: str, name: str, start: str) -> dict | None:
    """Return an existing active event in the channel with the same name and start, or None."""
    resp = _table().scan(
        FilterExpression=Attr("channel_id").eq(channel_id) & Attr("name").eq(name) & Attr("start").eq(start),
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def store_message_ref(event_key: str, channel_id: str, message_id: str) -> None:
    """Persist the Discord channel/message IDs on the event for future channel updates."""
    _table().update_item(
        Key={"event_key": event_key},
        UpdateExpression="SET channel_id = :c, message_id = :m",
        ExpressionAttributeValues={":c": channel_id, ":m": message_id},
    )


def store_interaction_ref(event_key: str, interaction_token: str, app_id: str) -> None:
    """Persist the Edit-button interaction token and app ID for webhook-based message edits."""
    _table().update_item(
        Key={"event_key": event_key},
        UpdateExpression="SET interaction_token = :t, app_id = :a",
        ExpressionAttributeValues={":t": interaction_token, ":a": app_id},
    )


def delete_event(event_key: str) -> None:
    """Delete an event and all its RSVP data."""
    logger.debug("Deleting event %s", event_key)
    _table().delete_item(Key={"event_key": event_key})


def get_event(event_key: str) -> dict | None:
    """Return the event item or None if not found."""
    response = _table().get_item(Key={"event_key": event_key})
    return response.get("Item")


def _clear_user_from_rsvps(event: dict, user_id: str) -> None:
    """Remove user_id from all RSVP action lists in-place."""
    for a in RSVP_ACTIONS:
        users = list(event.get(a, []))
        if user_id in users:
            users.remove(user_id)
        event[a] = users


def set_rsvp(event_key: str, user_id: str, action: str, display_name: str | None = None) -> dict:
    """
    Set a user's RSVP to a specific action without toggling.

    Removes the user from any other action list and always adds them to
    the specified one. Returns the updated event item.
    """
    event = get_event(event_key)
    if event is None:
        logger.warning("Event not found: %s", event_key)
        raise ValueError(f"Event {event_key!r} not found")

    _clear_user_from_rsvps(event, user_id)
    # Remove from goalie — a user can't be in both
    if user_id in event.get(GOALIE_ACTION, []):
        event[GOALIE_ACTION] = []
    event[action] = event.get(action, []) + [user_id]
    names = dict(event.get("member_names") or {})
    if display_name:
        names[user_id] = display_name
    event["member_names"] = names
    _table().put_item(Item=event)
    return event


def remove_rsvp(event_key: str, user_id: str) -> dict:
    """Remove a user from all RSVP lists and the goalie slot. Returns the updated event item."""
    event = get_event(event_key)
    if event is None:
        logger.warning("Event not found: %s", event_key)
        raise ValueError(f"Event {event_key!r} not found")

    in_rsvp = any(user_id in event.get(a, []) for a in RSVP_ACTIONS)
    in_goalie = user_id in event.get(GOALIE_ACTION, [])
    if not in_rsvp and not in_goalie:
        raise ValueError("User is not in the RSVP list.")

    _clear_user_from_rsvps(event, user_id)
    if in_goalie:
        event[GOALIE_ACTION] = []
    names = dict(event.get("member_names") or {})
    names.pop(user_id, None)
    event["member_names"] = names
    _table().put_item(Item=event)
    return event


def set_goalie(event_key: str, user_id: str, display_name: str | None = None) -> dict:
    """
    Set a user as the goalie for an event (max 1).

    If the user is already the goalie, toggles them off.
    Otherwise replaces whoever was goalie with this user.
    Returns the updated event item.
    """
    event = get_event(event_key)
    if event is None:
        logger.warning("Event not found: %s", event_key)
        raise ValueError(f"Event {event_key!r} not found")

    current_goalie = list(event.get("goalie", []))
    names = dict(event.get("member_names") or {})

    if user_id in current_goalie:
        # Toggle off
        event["goalie"] = []
        names.pop(user_id, None)
    else:
        # Remove old goalie's name, then set new goalie
        for old_id in current_goalie:
            names.pop(old_id, None)
        event["goalie"] = [user_id]
        # Remove from RSVP lists — a user can't be in both
        _clear_user_from_rsvps(event, user_id)
        if display_name:
            names[user_id] = display_name

    event["member_names"] = names
    _table().put_item(Item=event)
    return event


def update_rsvp(event_key: str, user_id: str, action: str, display_name: str | None = None) -> dict:
    """
    Toggle a user's RSVP for an event.

    If the user already has this action, remove them (toggle off).
    Otherwise remove them from any other set and add them to this one.
    Returns the updated event item.
    """
    event = get_event(event_key)
    if event is None:
        logger.warning("Event not found: %s", event_key)
        raise ValueError(f"Event {event_key!r} not found")

    already_in_action = user_id in event.get(action, [])
    _clear_user_from_rsvps(event, user_id)
    names = dict(event.get("member_names") or {})
    if not already_in_action:
        # Remove from goalie — a user can't be in both
        if user_id in event.get(GOALIE_ACTION, []):
            event[GOALIE_ACTION] = []
        event[action] = event.get(action, []) + [user_id]
        if display_name:
            names[user_id] = display_name
    else:
        names.pop(user_id, None)
    event["member_names"] = names

    _table().put_item(Item=event)
    return event

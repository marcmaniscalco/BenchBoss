"""DynamoDB persistence for event RSVP state."""

import os
from datetime import UTC, datetime, timedelta

import boto3
from aws_lambda_powertools import Logger

logger = Logger(service="bench-boss")

RSVP_ACTIONS = ("accepted", "declined", "tentative")


def _table():
    kwargs = {}
    endpoint = os.environ.get("DYNAMODB_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.resource("dynamodb", region_name="us-east-1", **kwargs).Table(
        os.environ["DYNAMODB_TABLE"]
    )


def _ttl_timestamp(end: str | None, start: str) -> int:
    """Return a Unix timestamp 24 hours after end (or start if no end)."""
    base = datetime.fromisoformat(end if end else start)
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return int((base + timedelta(hours=24)).timestamp())


def save_event(
    event_key: str,
    name: str,
    start: str,
    end: str | None,
    location: str | None,
    description: str | None,
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
        "ttl": _ttl_timestamp(end, start),
    }
    if end is not None:
        item["end"] = end
    if location is not None:
        item["location"] = location
    if description is not None:
        item["description"] = description
    _table().put_item(Item=item)


def delete_event(event_key: str) -> None:
    """Delete an event and all its RSVP data."""
    logger.debug("Deleting event %s", event_key)
    _table().delete_item(Key={"event_key": event_key})


def get_event(event_key: str) -> dict | None:
    """Return the event item or None if not found."""
    response = _table().get_item(Key={"event_key": event_key})
    return response.get("Item")


def update_rsvp(event_key: str, user_id: str, action: str) -> dict:
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

    for a in RSVP_ACTIONS:
        users = list(event.get(a, []))
        if user_id in users:
            users.remove(user_id)
        event[a] = users

    if not already_in_action:
        event[action] = event.get(action, []) + [user_id]

    _table().put_item(Item=event)
    return event

"""Discord embed and component builders for Apollo-style event messages."""

from datetime import UTC, datetime
from urllib.parse import urlencode

BLURPLE = 0x5865F2

_RSVP_LABELS = {
    "accepted": "✅ Accepted",
    "declined": "❌ Declined",
    "tentative": "❔ Tentative",
}

_RSVP_ICONS = {
    "accepted": "✅",
    "declined": "❌",
    "tentative": "❔",
}

# Discord button styles: 3=SUCCESS (green), 4=DANGER (red), 2=SECONDARY (gray)
_RSVP_STYLES = {
    "accepted": 2,
    "declined": 2,
    "tentative": 2,
}


def _ensure_tz(dt: datetime) -> datetime:
    if not dt.tzinfo:
        return dt.replace(tzinfo=UTC)
    return dt


def _format_dt(start: datetime, end: datetime | None) -> str:
    start = _ensure_tz(start)
    tz_label = start.strftime("%Z") or "UTC"
    hour = start.hour % 12 or 12
    minute = start.strftime("%M")
    ampm = "AM" if start.hour < 12 else "PM"
    date_str = start.strftime(f"%A, %B {start.day}, %Y")
    time_str = f"{hour}:{minute} {ampm} {tz_label}"
    if end:
        end = _ensure_tz(end).astimezone(start.tzinfo)
        end_tz_label = end.strftime("%Z") or "UTC"
        end_hour = end.hour % 12 or 12
        end_minute = end.strftime("%M")
        end_ampm = "AM" if end.hour < 12 else "PM"
        return f"{date_str}\n{time_str} – {end_hour}:{end_minute} {end_ampm} {end_tz_label}"
    return f"{date_str}\n{time_str}"


def _build_gcal_url(
    name: str,
    start: datetime,
    end: datetime | None,
    location: str | None,
    description: str | None,
) -> str:

    def _fmt(dt) -> str:
        if isinstance(dt, datetime):
            return _ensure_tz(dt).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y%m%d")  # all-day

    start_str = _fmt(start)
    end_str = _fmt(end) if end else start_str

    params: dict = {"action": "TEMPLATE", "text": name, "dates": f"{start_str}/{end_str}"}
    if location:
        params["location"] = location
    if description:
        params["details"] = description

    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def _rsvp_field(action: str, users: list[str], names: dict[str, str] | None = None) -> dict:
    label = _RSVP_LABELS[action]
    count = len(users)
    if users:
        value = "\n".join(names[uid] if names and uid in names else f"<@{uid}>" for uid in users)
    else:
        value = "-"
    return {"name": f"{label} ({count})", "value": value, "inline": True}


def build_event_embed(
    name: str,
    start: datetime,
    end: datetime | None,
    location: str | None,
    description: str | None,
    accepted: list[str],
    declined: list[str],
    tentative: list[str],
    names: dict[str, str] | None = None,
    goalie: list[str] | None = None,
) -> dict:
    """Build a Discord embed dict in Apollo style."""
    fields: list[dict] = [
        {"name": "📅 When", "value": _format_dt(start, end), "inline": False},
    ]
    if location:
        fields.append({"name": "📍 Where", "value": location, "inline": False})
    if description:
        fields.append(
            {
                "name": "📋 Details",
                "value": f"[Game Details]({description})",
                "inline": False,
            }
        )

    gcal_url = _build_gcal_url(name, start, end, location, description)
    fields.append(
        {"name": "🗓️ Add to Calendar", "value": f"[Google Calendar]({gcal_url})", "inline": False}
    )

    # Blank separator before RSVP section
    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})

    goalie_list = goalie or []
    goalie_name = (names.get(goalie_list[0]) if names and goalie_list else None) or (f"<@{goalie_list[0]}>" if goalie_list else "-")
    fields.append({"name": "🇬 Goalie", "value": goalie_name, "inline": False})

    fields.extend(
        [
            _rsvp_field("accepted", accepted, names),
            _rsvp_field("declined", declined, names),
            _rsvp_field("tentative", tentative, names),
        ]
    )

    return {"title": name, "color": BLURPLE, "fields": fields}


def build_rsvp_components(event_key: str) -> list[dict]:
    """Return two action rows: RSVP/delete buttons and add/remove buttons."""
    rsvp_buttons = [
        {
            "type": 2,  # BUTTON
            "style": _RSVP_STYLES[action],
            "emoji": {"name": emoji},
            "custom_id": f"rsvp:{action}:{event_key}",
        }
        for action, emoji in _RSVP_ICONS.items()
    ]
    rsvp_buttons.append(
        {
            "type": 2,
            "style": 2,  # SECONDARY (gray)
            "emoji": {"name": "🇬"},
            "custom_id": f"goalie_rsvp:{event_key}",
        }
    )
    edit_buttons = [
        {
            "type": 2,
            "style": 1,  # PRIMARY (blue)
            "emoji": {"name": "➕"},
            "custom_id": f"add_rsvp:{event_key}",
        },
        {
            "type": 2,
            "style": 4,  # DANGER (red)
            "emoji": {"name": "➖"},
            "custom_id": f"remove_rsvp:{event_key}",
        },
        {
            "type": 2,
            "style": 4,  # DANGER (red)
            "label": "Delete",
            "custom_id": f"delete:{event_key}",
        },
    ]
    return [
        {"type": 1, "components": rsvp_buttons},
        {"type": 1, "components": edit_buttons},
    ]



def build_delete_confirm_buttons(
    event_key: str, channel_id: str, message_id: str
) -> list[dict]:
    """Return an action row with Delete and Cancel buttons for event deletion confirmation."""
    return [
        {
            "type": 1,  # ACTION_ROW
            "components": [
                {
                    "type": 2,  # BUTTON
                    "style": 4,  # DANGER (red)
                    "label": "Delete",
                    "custom_id": f"delete_confirm:{event_key}:{channel_id}:{message_id}",
                },
                {
                    "type": 2,  # BUTTON
                    "style": 2,  # SECONDARY (gray)
                    "label": "Cancel",
                    "custom_id": f"delete_cancel:{event_key}",
                },
            ],
        }
    ]


def build_no_events_embed() -> dict:
    """Build an embed shown when the calendar has no more upcoming events."""
    return {
        "title": "No More Events",
        "description": "There are no more upcoming events scheduled in this calendar.",
        "color": BLURPLE,
    }


def build_add_rsvp_modal(event_key: str) -> dict:
    """Return the modal data for adding a user to the RSVP."""
    return {
        "custom_id": f"add_rsvp_modal:{event_key}",
        "title": "Add a response",
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 4,  # TEXT_INPUT
                        "custom_id": "user",
                        "label": "User",
                        "style": 1,  # SHORT
                        "placeholder": "@username or user ID",
                        "required": True,
                    }
                ],
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 4,  # TEXT_INPUT
                        "custom_id": "action",
                        "label": "RSVP Status",
                        "style": 1,  # SHORT
                        "placeholder": "accepted / declined / tentative / goalie  (or a / d / t / g)",
                        "required": True,
                        "min_length": 1,
                        "max_length": 8,
                    }
                ],
            },
        ],
    }


def build_remove_rsvp_modal(event_key: str) -> dict:
    """Return the modal data for removing a user from the RSVP."""
    return {
        "custom_id": f"remove_rsvp_modal:{event_key}",
        "title": "Remove a response",
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 4,
                        "custom_id": "user",
                        "label": "User",
                        "style": 1,
                        "placeholder": "@username or user ID",
                        "required": True,
                    }
                ],
            },
        ],
    }

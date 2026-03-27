"""Discord embed and component builders for Apollo-style event messages."""

from datetime import UTC, datetime

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


def _ensure_utc(dt: datetime) -> datetime:
    if not dt.tzinfo:
        return dt.replace(tzinfo=UTC)
    return dt


def _format_dt(start: datetime, end: datetime | None) -> str:
    start = _ensure_utc(start)
    hour = start.hour % 12 or 12
    minute = start.strftime("%M")
    ampm = "AM" if start.hour < 12 else "PM"
    date_str = start.strftime(f"%A, %B {start.day}, %Y")
    time_str = f"{hour}:{minute} {ampm} UTC"
    if end:
        end = _ensure_utc(end)
        end_hour = end.hour % 12 or 12
        end_minute = end.strftime("%M")
        end_ampm = "AM" if end.hour < 12 else "PM"
        return f"{date_str}\n{time_str} – {end_hour}:{end_minute} {end_ampm} UTC"
    return f"{date_str}\n{time_str}"


def _rsvp_field(action: str, users: list[str]) -> dict:
    label = _RSVP_LABELS[action]
    count = len(users)
    value = "\n".join(f"<@{uid}>" for uid in users) if users else "-"
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

    # Blank separator before RSVP section
    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})

    fields.extend(
        [
            _rsvp_field("accepted", accepted),
            _rsvp_field("declined", declined),
            _rsvp_field("tentative", tentative),
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
            "style": 4,  # DANGER (red)
            "label": "Delete",
            "custom_id": f"delete:{event_key}",
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
    ]
    return [
        {"type": 1, "components": rsvp_buttons},
        {"type": 1, "components": edit_buttons},
    ]



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
                        "type": 4,
                        "custom_id": "action",
                        "label": "RSVP Status",
                        "style": 1,
                        "placeholder": "accepted / declined / tentative",
                        "required": True,
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

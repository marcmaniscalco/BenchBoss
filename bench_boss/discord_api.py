"""Discord embed and component builders for Apollo-style event messages."""

from datetime import UTC, datetime

BLURPLE = 0x5865F2

_RSVP_LABELS = {
    "accepted": "✅ Accepted",
    "declined": "❌ Declined",
    "maybe": "❓ Maybe",
    "late": "🕐 Late",
}

# Discord button styles: 3=SUCCESS (green), 4=DANGER (red), 2=SECONDARY (gray)
_RSVP_STYLES = {
    "accepted": 3,
    "declined": 4,
    "maybe": 2,
    "late": 2,
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
    maybe: list[str],
    late: list[str],
) -> dict:
    """Build a Discord embed dict in Apollo style."""
    fields: list[dict] = [
        {"name": "📅 When", "value": _format_dt(start, end), "inline": False},
    ]
    if location:
        fields.append({"name": "📍 Where", "value": location, "inline": False})
    if description:
        fields.append({"name": "📋 Details", "value": description, "inline": False})

    # Blank separator before RSVP section
    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})

    # Two RSVP columns per row, with a blank third inline field to force wrapping
    fields.extend(
        [
            _rsvp_field("accepted", accepted),
            _rsvp_field("declined", declined),
            {"name": "\u200b", "value": "\u200b", "inline": True},
            _rsvp_field("maybe", maybe),
            _rsvp_field("late", late),
            {"name": "\u200b", "value": "\u200b", "inline": True},
        ]
    )

    return {"title": name, "color": BLURPLE, "fields": fields}


def build_rsvp_components(event_key: str) -> list[dict]:
    """Return a single action row of four RSVP buttons."""
    buttons = [
        {
            "type": 2,  # BUTTON
            "style": _RSVP_STYLES[action],
            "label": label,
            "custom_id": f"rsvp:{action}:{event_key}",
        }
        for action, label in _RSVP_LABELS.items()
    ]
    return [{"type": 1, "components": buttons}]  # ACTION_ROW

"""
Discord REST API calls made by the bot (beyond interaction responses).
"""

from datetime import UTC, datetime, timedelta

import requests

DISCORD_API = "https://discord.com/api/v10"

# Entity types
EXTERNAL = 3

# Privacy levels
GUILD_ONLY = 2


def create_scheduled_event(
    guild_id: str,
    name: str,
    start: datetime,
    end: datetime | None,
    location: str | None,
    bot_token: str,
) -> dict:
    """
    Create a Discord Guild Scheduled Event and return the created event dict.

    Uses EXTERNAL entity type so no voice channel is required.
    If end is not provided, defaults to start + 1 hour.
    If location is not provided, defaults to "TBD".
    """
    if not end:
        end = start + timedelta(hours=1)

    if not start.tzinfo:
        start = start.replace(tzinfo=UTC)
    if not end.tzinfo:
        end = end.replace(tzinfo=UTC)

    payload = {
        "name": name,
        "scheduled_start_time": start.isoformat(),
        "scheduled_end_time": end.isoformat(),
        "privacy_level": GUILD_ONLY,
        "entity_type": EXTERNAL,
        "entity_metadata": {"location": location or "TBD"},
    }

    response = requests.post(
        f"{DISCORD_API}/guilds/{guild_id}/scheduled-events",
        headers={"Authorization": f"Bot {bot_token}"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

"""Shared helpers for guest RSVPs — players an admin adds who have no
Discord account, identified only by a name typed into the +/- modal.

Kept in its own module (rather than living in bot.py) so bot.py and
discord_api.py can both recognize a guest ID without either importing
from the other.
"""

import uuid

#: Prefix for synthetic IDs assigned to guest RSVPs. Never collides with a
#: real Discord snowflake (always numeric), so `is_guest_id` can tell the
#: two apart everywhere a user_id shows up (display-name lookup, goalie
#: assignment, embed rendering, etc.) without needing a separate flag
#: threaded through the RSVP lists.
GUEST_ID_PREFIX = "guest:"


def is_guest_id(user_id: str) -> bool:
    return user_id.startswith(GUEST_ID_PREFIX)


def generate_guest_id() -> str:
    return f"{GUEST_ID_PREFIX}{uuid.uuid4().hex[:8]}"

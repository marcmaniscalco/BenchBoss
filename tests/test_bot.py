import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey

from bench_boss.bot import (
    APPLICATION_COMMAND,
    CHANNEL_MESSAGE_WITH_SOURCE,
    PING,
    PONG,
    handle_interaction,
    verify_signature,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_signed_request(body: dict, signing_key: SigningKey):
    """Return (raw_body, signature, timestamp) signed with the given key."""
    raw_body = json.dumps(body, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    message = timestamp.encode() + raw_body
    signature = signing_key.sign(message).signature.hex()
    return raw_body, signature, timestamp


def make_schedule_body(url: str, guild_id: str = "123") -> dict:
    return {
        "type": APPLICATION_COMMAND,
        "guild_id": guild_id,
        "data": {
            "name": "schedule",
            "options": [{"name": "url", "value": url}],
        },
    }


def make_calendar_event(summary="Team Standup", days_ahead=1):
    from bench_boss.calendar import CalendarEvent

    start = datetime.now(tz=UTC) + timedelta(days=days_ahead)
    return CalendarEvent(
        summary=summary,
        start=start,
        end=start + timedelta(hours=1),
        location="Room 1",
        description=None,
    )


@pytest.fixture()
def keypair():
    signing_key = SigningKey.generate()
    public_key = signing_key.verify_key.encode().hex()
    return signing_key, public_key


# ---------------------------------------------------------------------------
# verify_signature
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature(self, keypair):
        signing_key, public_key = keypair
        raw_body, signature, timestamp = make_signed_request({"type": 1}, signing_key)
        assert verify_signature(raw_body, signature, timestamp, public_key) is True

    def test_wrong_public_key(self, keypair):
        signing_key, _ = keypair
        wrong_key = SigningKey.generate().verify_key.encode().hex()
        raw_body, signature, timestamp = make_signed_request({"type": 1}, signing_key)
        assert verify_signature(raw_body, signature, timestamp, wrong_key) is False

    def test_tampered_body(self, keypair):
        signing_key, public_key = keypair
        raw_body, signature, timestamp = make_signed_request({"type": 1}, signing_key)
        tampered = raw_body + b" "
        assert verify_signature(tampered, signature, timestamp, public_key) is False

    def test_invalid_signature_hex(self, keypair):
        signing_key, public_key = keypair
        raw_body, _, timestamp = make_signed_request({"type": 1}, signing_key)
        assert verify_signature(raw_body, "not-hex", timestamp, public_key) is False

    def test_empty_signature(self, keypair):
        signing_key, public_key = keypair
        raw_body, _, timestamp = make_signed_request({"type": 1}, signing_key)
        assert verify_signature(raw_body, "", timestamp, public_key) is False


# ---------------------------------------------------------------------------
# handle_interaction — PING
# ---------------------------------------------------------------------------


class TestPingInteraction:
    def test_ping_returns_pong(self):
        result = handle_interaction({"type": PING})
        assert result["statusCode"] == 200
        assert result["body"]["type"] == PONG

    def test_ping_command_returns_pong_message(self):
        result = handle_interaction(
            {"type": APPLICATION_COMMAND, "data": {"name": "ping"}}
        )
        assert result["statusCode"] == 200
        assert result["body"]["type"] == CHANNEL_MESSAGE_WITH_SOURCE
        assert result["body"]["data"]["content"] == "Pong!"


# ---------------------------------------------------------------------------
# handle_interaction — /schedule
# ---------------------------------------------------------------------------


class TestScheduleInteraction:
    def test_missing_url_returns_error(self):
        body = {
            "type": APPLICATION_COMMAND,
            "guild_id": "123",
            "data": {"name": "schedule", "options": []},
        }
        result = handle_interaction(body, bot_token="token")
        assert result["statusCode"] == 200
        assert "No calendar URL provided" in result["body"]["data"]["content"]

    def test_calendar_fetch_failure_returns_error(self):
        with patch("bench_boss.bot.WebCalReader") as mock_reader:
            mock_reader.return_value.get_upcoming.side_effect = Exception("timeout")
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics"), bot_token="token"
            )
        assert "Failed to fetch calendar" in result["body"]["data"]["content"]

    def test_empty_calendar_returns_no_events_message(self):
        with patch("bench_boss.bot.WebCalReader") as mock_reader:
            mock_reader.return_value.get_upcoming.return_value = []
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics"), bot_token="token"
            )
        assert "No upcoming events" in result["body"]["data"]["content"]

    def test_creates_discord_event_from_next_calendar_event(self):
        event = make_calendar_event("Team Standup")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.create_scheduled_event") as mock_create,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            mock_create.return_value = {"id": "999", "name": "Team Standup"}
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics", guild_id="456"),
                bot_token="token",
            )

        mock_create.assert_called_once_with(
            guild_id="456",
            name="Team Standup",
            start=event.start,
            end=event.end,
            location=event.location,
            bot_token="token",
        )
        assert result["statusCode"] == 200

    def test_success_reply_contains_event_name_and_url(self):
        event = make_calendar_event("Sprint Review")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.create_scheduled_event") as mock_create,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            mock_create.return_value = {"id": "42", "name": "Sprint Review"}
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics", guild_id="456"),
                bot_token="token",
            )

        content = result["body"]["data"]["content"]
        assert "Sprint Review" in content
        assert "https://discord.com/events/456/42" in content

    def test_discord_api_failure_returns_error(self):
        event = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.create_scheduled_event") as mock_create,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            mock_create.side_effect = Exception("403 Forbidden")
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics"), bot_token="token"
            )

        assert "Failed to create Discord event" in result["body"]["data"]["content"]

    def test_only_next_event_is_used(self):
        events = [
            make_calendar_event("First", days_ahead=1),
            make_calendar_event("Second", days_ahead=2),
        ]
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.create_scheduled_event") as mock_create,
        ):
            mock_reader.return_value.get_upcoming.return_value = events
            mock_create.return_value = {"id": "1", "name": "First"}
            handle_interaction(
                make_schedule_body("https://example.com/cal.ics"), bot_token="token"
            )

        assert mock_create.call_args[1]["name"] == "First"


# ---------------------------------------------------------------------------
# handle_interaction — edge cases
# ---------------------------------------------------------------------------


class TestHandleInteractionEdgeCases:
    def test_unknown_command_returns_message(self):
        result = handle_interaction(
            {"type": APPLICATION_COMMAND, "data": {"name": "unknown"}}
        )
        assert result["statusCode"] == 200
        assert "unknown" in result["body"]["data"]["content"]

    def test_unhandled_interaction_type_returns_400(self):
        result = handle_interaction({"type": 99})
        assert result["statusCode"] == 400

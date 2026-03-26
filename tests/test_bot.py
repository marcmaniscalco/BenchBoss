import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey

from bench_boss.bot import (
    APPLICATION_COMMAND,
    CHANNEL_MESSAGE_WITH_SOURCE,
    DEFERRED_UPDATE_MESSAGE,
    MESSAGE_COMPONENT,
    PING,
    PONG,
    UPDATE_MESSAGE,
    _delete_original_message,
    _send_edit_dm,
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


def make_rsvp_body(custom_id: str, user_id: str = "user1") -> dict:
    return {
        "type": MESSAGE_COMPONENT,
        "member": {"user": {"id": user_id}},
        "data": {"custom_id": custom_id},
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
        result = handle_interaction(body)
        assert result["statusCode"] == 200
        assert "No calendar URL provided" in result["body"]["data"]["content"]

    def test_calendar_fetch_failure_returns_error(self):
        with patch("bench_boss.bot.WebCalReader") as mock_reader:
            mock_reader.return_value.get_upcoming.side_effect = Exception("timeout")
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )
        assert "Failed to fetch calendar" in result["body"]["data"]["content"]

    def test_empty_calendar_returns_no_events_message(self):
        with patch("bench_boss.bot.WebCalReader") as mock_reader:
            mock_reader.return_value.get_upcoming.return_value = []
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )
        assert "No upcoming events" in result["body"]["data"]["content"]

    def test_dynamo_save_failure_returns_error(self):
        event = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event", side_effect=Exception("DynamoDB error")),
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )
        assert "Failed to save event" in result["body"]["data"]["content"]

    def test_success_returns_embed_and_components(self):
        event = make_calendar_event("Team Standup")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )

        assert result["statusCode"] == 200
        assert result["body"]["type"] == CHANNEL_MESSAGE_WITH_SOURCE
        data = result["body"]["data"]
        assert "embeds" in data
        assert "components" in data

    def test_embed_title_is_event_name(self):
        event = make_calendar_event("Sprint Review")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )

        embed = result["body"]["data"]["embeds"][0]
        assert embed["title"] == "Sprint Review"

    def test_components_have_five_buttons(self):
        event = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )

        buttons = result["body"]["data"]["components"][0]["components"]
        assert len(buttons) == 5

    def test_only_next_event_is_used(self):
        events = [
            make_calendar_event("First", days_ahead=1),
            make_calendar_event("Second", days_ahead=2),
        ]
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
        ):
            mock_reader.return_value.get_upcoming.return_value = events
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )

        embed = result["body"]["data"]["embeds"][0]
        assert embed["title"] == "First"

    def test_save_event_called_with_event_details(self):
        event = make_calendar_event("My Event")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event") as mock_save,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            handle_interaction(make_schedule_body("https://example.com/cal.ics"))

        mock_save.assert_called_once()
        kwargs = mock_save.call_args[1]
        assert kwargs["name"] == "My Event"
        assert kwargs["location"] == "Room 1"


# ---------------------------------------------------------------------------
# handle_interaction — RSVP button clicks
# ---------------------------------------------------------------------------


def make_stored_event(**overrides) -> dict:
    base = {
        "event_key": "test-key",
        "name": "Team Standup",
        "start": "2026-04-05T19:00:00+00:00",
        "end": "2026-04-05T20:00:00+00:00",
        "accepted": [],
        "declined": [],
        "tentative": [],
    }
    base.update(overrides)
    return base


class TestRsvpInteraction:
    def test_accept_button_updates_embed(self):
        updated = make_stored_event(accepted=["user1"])
        body = make_rsvp_body("rsvp:accepted:test-key", "user1")
        with patch("bench_boss.bot.update_rsvp", return_value=updated):
            result = handle_interaction(body)

        assert result["statusCode"] == 200
        assert result["body"]["type"] == UPDATE_MESSAGE

    def test_response_contains_updated_embed_and_components(self):
        updated = make_stored_event(accepted=["user1"])
        body = make_rsvp_body("rsvp:accepted:test-key", "user1")
        with patch("bench_boss.bot.update_rsvp", return_value=updated):
            result = handle_interaction(body)

        data = result["body"]["data"]
        assert "embeds" in data
        assert "components" in data

    def test_embed_shows_rsvp_user_mention(self):
        updated = make_stored_event(accepted=["user1"])
        body = make_rsvp_body("rsvp:accepted:test-key", "user1")
        with patch("bench_boss.bot.update_rsvp", return_value=updated):
            result = handle_interaction(body)

        fields = result["body"]["data"]["embeds"][0]["fields"]
        accepted_field = next(f for f in fields if "Accepted" in f["name"])
        assert "<@user1>" in accepted_field["value"]

    def test_update_rsvp_called_with_correct_args(self):
        updated = make_stored_event()
        with patch("bench_boss.bot.update_rsvp", return_value=updated) as mock_update:
            handle_interaction(make_rsvp_body("rsvp:tentative:abc-key", "user99"))

        mock_update.assert_called_once_with("abc-key", "user99", "tentative")

    def test_event_not_found_returns_error_message(self):
        with patch("bench_boss.bot.update_rsvp", side_effect=ValueError("not found")):
            result = handle_interaction(make_rsvp_body("rsvp:accepted:bad-key"))

        assert result["body"]["type"] == CHANNEL_MESSAGE_WITH_SOURCE
        assert "not found" in result["body"]["data"]["content"].lower()

    def test_dynamo_error_returns_error_message(self):
        with patch("bench_boss.bot.update_rsvp", side_effect=Exception("DB error")):
            result = handle_interaction(make_rsvp_body("rsvp:accepted:key1"))

        assert "Failed to update RSVP" in result["body"]["data"]["content"]

    def test_invalid_custom_id_returns_400(self):
        result = handle_interaction(
            {"type": MESSAGE_COMPONENT, "data": {"custom_id": "garbage"}}
        )
        assert result["statusCode"] == 400

    def test_user_id_from_member_when_in_guild(self):
        updated = make_stored_event()
        with patch("bench_boss.bot.update_rsvp", return_value=updated) as mock_update:
            handle_interaction(
                {
                    "type": MESSAGE_COMPONENT,
                    "member": {"user": {"id": "guild-user"}},
                    "data": {"custom_id": "rsvp:accepted:key1"},
                }
            )
        mock_update.assert_called_once_with("key1", "guild-user", "accepted")

    def test_user_id_from_user_when_in_dm(self):
        updated = make_stored_event()
        with patch("bench_boss.bot.update_rsvp", return_value=updated) as mock_update:
            handle_interaction(
                {
                    "type": MESSAGE_COMPONENT,
                    "user": {"id": "dm-user"},
                    "data": {"custom_id": "rsvp:declined:key1"},
                }
            )
        mock_update.assert_called_once_with("key1", "dm-user", "declined")


# ---------------------------------------------------------------------------
# handle_interaction — delete button
# ---------------------------------------------------------------------------


def make_delete_body(event_key: str, app_id: str = "app1", token: str = "tok1") -> dict:
    return {
        "type": MESSAGE_COMPONENT,
        "application_id": app_id,
        "token": token,
        "member": {"user": {"id": "user1"}},
        "data": {"custom_id": f"delete:{event_key}"},
    }


class TestDeleteInteraction:
    def test_delete_calls_delete_event(self):
        with (
            patch("bench_boss.bot.delete_event") as mock_delete,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_delete_body("key1"))
        mock_delete.assert_called_once_with("key1")

    def test_delete_returns_deferred_update(self):
        with (
            patch("bench_boss.bot.delete_event"),
            patch("bench_boss.bot.threading.Thread"),
        ):
            result = handle_interaction(make_delete_body("key1"))
        assert result["statusCode"] == 200
        assert result["body"]["type"] == DEFERRED_UPDATE_MESSAGE

    def test_delete_starts_background_thread(self):
        with (
            patch("bench_boss.bot.delete_event"),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            handle_interaction(make_delete_body("key1", app_id="myapp", token="mytoken"))
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _delete_original_message
        assert kwargs["args"] == ("myapp", "mytoken")

    def test_delete_skips_thread_when_no_app_id_or_token(self):
        with (
            patch("bench_boss.bot.delete_event"),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            handle_interaction(
                {"type": MESSAGE_COMPONENT, "data": {"custom_id": "delete:key1"}}
            )
        mock_thread.assert_not_called()

    def test_delete_event_failure_returns_error(self):
        with patch("bench_boss.bot.delete_event", side_effect=Exception("DB error")):
            result = handle_interaction(make_delete_body("key1"))
        assert "Failed to delete event" in result["body"]["data"]["content"]


class TestDeleteOriginalMessage:
    def test_calls_correct_webhook_url(self):
        with (
            patch("bench_boss.bot.time.sleep"),
            patch("bench_boss.bot.requests.delete") as mock_req,
        ):
            _delete_original_message("myapp", "mytoken")
        url = mock_req.call_args[0][0]
        assert "webhooks/myapp/mytoken/messages/@original" in url

    def test_sleeps_before_deleting(self):
        with (
            patch("bench_boss.bot.time.sleep") as mock_sleep,
            patch("bench_boss.bot.requests.delete"),
        ):
            _delete_original_message("app", "tok")
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] > 0


# ---------------------------------------------------------------------------
# handle_interaction — edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# handle_interaction — edit button
# ---------------------------------------------------------------------------


def make_edit_body(event_key: str = "test-key") -> dict:
    return {
        "type": MESSAGE_COMPONENT,
        "member": {"user": {"id": "user1"}},
        "data": {"custom_id": f"edit:{event_key}"},
    }


class TestEditInteraction:
    def test_edit_returns_ephemeral_message(self):
        with patch("bench_boss.bot.threading.Thread"):
            result = handle_interaction(make_edit_body(), bot_token="tok")
        assert result["statusCode"] == 200
        assert result["body"]["type"] == CHANNEL_MESSAGE_WITH_SOURCE
        assert result["body"]["data"]["flags"] == 64

    def test_edit_response_mentions_dms(self):
        with patch("bench_boss.bot.threading.Thread"):
            result = handle_interaction(make_edit_body(), bot_token="tok")
        assert "DMs" in result["body"]["data"]["content"]

    def test_edit_starts_background_thread(self):
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            handle_interaction(make_edit_body(), bot_token="mytoken")
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _send_edit_dm
        assert kwargs["args"] == ("user1", "mytoken")

    def test_edit_skips_thread_when_no_token(self):
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            handle_interaction(make_edit_body())
        mock_thread.assert_not_called()

    def test_edit_skips_thread_when_no_user_id(self):
        body = {"type": MESSAGE_COMPONENT, "data": {"custom_id": "edit:test-key"}}
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            handle_interaction(body, bot_token="tok")
        mock_thread.assert_not_called()

    def test_edit_user_id_from_top_level_user_in_dm(self):
        body = {
            "type": MESSAGE_COMPONENT,
            "user": {"id": "dm-user"},
            "data": {"custom_id": "edit:test-key"},
        }
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            handle_interaction(body, bot_token="tok")
        kwargs = mock_thread.call_args[1]
        assert kwargs["args"] == ("dm-user", "tok")


class TestSendEditDm:
    def _ok_resp(self, channel_id="chan1"):
        return type("R", (), {"ok": True, "status_code": 200, "text": "", "json": lambda self: {"id": channel_id}})()

    def test_opens_dm_channel_with_correct_user(self):
        with patch("bench_boss.bot.requests.post", return_value=self._ok_resp()) as mock_post:
            _send_edit_dm("user42", "mytoken")
        assert mock_post.call_args_list[0][1]["json"] == {"recipient_id": "user42"}

    def test_sends_message_to_dm_channel(self):
        with patch("bench_boss.bot.requests.post", return_value=self._ok_resp("chan99")) as mock_post:
            _send_edit_dm("user1", "tok")
        assert "chan99" in mock_post.call_args_list[1][0][0]

    def test_uses_bot_token_in_auth_header(self):
        with patch("bench_boss.bot.requests.post", return_value=self._ok_resp()) as mock_post:
            _send_edit_dm("u1", "secret-token")
        headers = mock_post.call_args_list[0][1]["headers"]
        assert headers["Authorization"] == "Bot secret-token"

    def test_aborts_when_dm_channel_open_fails(self):
        fail_resp = type("R", (), {"ok": False, "status_code": 403, "text": "Forbidden", "json": lambda self: {}})()
        with patch("bench_boss.bot.requests.post", return_value=fail_resp) as mock_post:
            _send_edit_dm("u1", "tok")
        assert mock_post.call_count == 1

    def test_dm_message_contains_embed(self):
        with patch("bench_boss.bot.requests.post", return_value=self._ok_resp()) as mock_post:
            _send_edit_dm("u1", "tok")
        message_body = mock_post.call_args_list[1][1]["json"]
        assert "embeds" in message_body

    def test_dm_message_has_no_components(self):
        with patch("bench_boss.bot.requests.post", return_value=self._ok_resp()) as mock_post:
            _send_edit_dm("u1", "tok")
        message_body = mock_post.call_args_list[1][1]["json"]
        assert "components" not in message_body


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

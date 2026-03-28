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
    MODAL,
    MODAL_SUBMIT,
    PING,
    PONG,
    UPDATE_MESSAGE,
    _delete_original_message,
    _fetch_and_store_message_ref,
    _format_event_line,
    _send_dm_events,
    _update_channel_message,
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
    body = {
        "type": APPLICATION_COMMAND,
        "data": {
            "name": "schedule",
            "options": [{"name": "url", "value": url}],
        },
    }
    if guild_id:
        body["guild_id"] = guild_id
    return body


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

    def test_components_have_two_action_rows(self):
        event = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            result = handle_interaction(
                make_schedule_body("https://example.com/cal.ics")
            )

        components = result["body"]["data"]["components"]
        assert len(components) == 2
        assert len(components[0]["components"]) == 4
        assert len(components[1]["components"]) == 2

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

    def test_starts_message_ref_thread_when_app_id_and_token_present(self):
        event = make_calendar_event()
        body = {
            "type": APPLICATION_COMMAND,
            "guild_id": "g1",
            "application_id": "app1",
            "token": "tok1",
            "data": {"name": "schedule", "options": [{"name": "url", "value": "https://example.com/cal.ics"}]},
        }
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            handle_interaction(body)
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _fetch_and_store_message_ref
        assert kwargs["args"] == ("app1", "tok1", mock_thread.call_args[1]["args"][2])

    def test_no_thread_when_app_id_missing(self):
        event = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event"),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            handle_interaction(make_schedule_body("https://example.com/cal.ics"))
        mock_thread.assert_not_called()

    def test_save_event_called_with_event_details(self):
        event = make_calendar_event("My Event")
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.save_event") as mock_save,
        ):
            mock_reader.return_value.get_upcoming.return_value = [event]
            handle_interaction(make_schedule_body("https://example.com/cal.ics", guild_id="g1"))

        mock_save.assert_called_once()
        kwargs = mock_save.call_args[1]
        assert kwargs["name"] == "My Event"
        assert kwargs["location"] == "Room 1"
        assert kwargs["guild_id"] == "g1"


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


class TestUpdateChannelMessage:
    def _make_event(self, **overrides):
        base = make_stored_event(channel_id="ch1", message_id="m1")
        base.update(overrides)
        return base

    def _ok_resp(self):
        return type("R", (), {"ok": True, "status_code": 200, "text": ""})()

    def test_uses_webhook_url_when_interaction_token_present(self):
        event = self._make_event(interaction_token="itoken", app_id="app1")
        with patch("bench_boss.bot.requests.patch", return_value=self._ok_resp()) as mock_patch:
            _update_channel_message(event, "tok")
        url = mock_patch.call_args[0][0]
        assert "webhooks/app1/itoken/messages/m1" in url

    def test_webhook_url_has_no_auth_header(self):
        event = self._make_event(interaction_token="itoken", app_id="app1")
        with patch("bench_boss.bot.requests.patch", return_value=self._ok_resp()) as mock_patch:
            _update_channel_message(event, "tok")
        headers = mock_patch.call_args[1]["headers"]
        assert "Authorization" not in headers

    def test_falls_back_to_channel_api_when_no_interaction_token(self):
        event = self._make_event()
        with patch("bench_boss.bot.requests.patch", return_value=self._ok_resp()) as mock_patch:
            _update_channel_message(event, "tok")
        url = mock_patch.call_args[0][0]
        assert "channels/ch1/messages/m1" in url

    def test_channel_api_uses_bot_token_in_auth_header(self):
        event = self._make_event()
        with patch("bench_boss.bot.requests.patch", return_value=self._ok_resp()) as mock_patch:
            _update_channel_message(event, "secret-tok")
        headers = mock_patch.call_args[1]["headers"]
        assert headers["Authorization"] == "Bot secret-tok"

    def test_patch_body_contains_embeds_and_components(self):
        event = self._make_event()
        with patch("bench_boss.bot.requests.patch", return_value=self._ok_resp()) as mock_patch:
            _update_channel_message(event, "tok")
        body = mock_patch.call_args[1]["json"]
        assert "embeds" in body
        assert "components" in body

    def test_skips_patch_when_no_channel_id(self):
        event = make_stored_event(message_id="m1")
        with (
            patch("bench_boss.bot.requests.patch") as mock_patch,
            patch("bench_boss.bot.logger") as mock_logger,
        ):
            _update_channel_message(event, "tok")
        mock_patch.assert_not_called()
        mock_logger.warning.assert_called()

    def test_skips_patch_when_no_message_id(self):
        event = make_stored_event(channel_id="ch1")
        with (
            patch("bench_boss.bot.requests.patch") as mock_patch,
            patch("bench_boss.bot.logger") as mock_logger,
        ):
            _update_channel_message(event, "tok")
        mock_patch.assert_not_called()
        mock_logger.warning.assert_called()


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
# _fetch_and_store_message_ref
# ---------------------------------------------------------------------------


class TestFetchAndStoreMessageRef:
    def _mock_get(self, ok=True, message_id="msg1", channel_id="ch1"):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.ok = ok
        resp.status_code = 200 if ok else 404
        resp.json.return_value = {"id": message_id, "channel_id": channel_id}
        return resp

    def test_stores_message_ref_on_success(self):
        with (
            patch("bench_boss.bot.time.sleep"),
            patch("bench_boss.bot.requests.get", return_value=self._mock_get()),
            patch("bench_boss.bot.store_message_ref") as mock_store,
        ):
            _fetch_and_store_message_ref("app1", "tok1", "key1")
        mock_store.assert_called_once_with("key1", "ch1", "msg1")

    def test_fetches_correct_webhook_url(self):
        with (
            patch("bench_boss.bot.time.sleep"),
            patch("bench_boss.bot.requests.get", return_value=self._mock_get()) as mock_get,
            patch("bench_boss.bot.store_message_ref"),
        ):
            _fetch_and_store_message_ref("app1", "tok1", "key1")
        url = mock_get.call_args[0][0]
        assert "webhooks/app1/tok1/messages/@original" in url

    def test_failed_get_skips_store(self):
        with (
            patch("bench_boss.bot.time.sleep"),
            patch("bench_boss.bot.requests.get", return_value=self._mock_get(ok=False)),
            patch("bench_boss.bot.store_message_ref") as mock_store,
        ):
            _fetch_and_store_message_ref("app1", "tok1", "key1")
        mock_store.assert_not_called()

    def test_missing_message_id_in_response_skips_store(self):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"channel_id": "ch1"}  # no "id"
        with (
            patch("bench_boss.bot.time.sleep"),
            patch("bench_boss.bot.requests.get", return_value=resp),
            patch("bench_boss.bot.store_message_ref") as mock_store,
        ):
            _fetch_and_store_message_ref("app1", "tok1", "key1")
        mock_store.assert_not_called()

    def test_sleeps_before_fetching(self):
        with (
            patch("bench_boss.bot.time.sleep") as mock_sleep,
            patch("bench_boss.bot.requests.get", return_value=self._mock_get()),
            patch("bench_boss.bot.store_message_ref"),
        ):
            _fetch_and_store_message_ref("app1", "tok1", "key1")
        mock_sleep.assert_called_once()


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


# ---------------------------------------------------------------------------
# handle_interaction — add/remove RSVP DM buttons
# ---------------------------------------------------------------------------


def make_add_rsvp_body(event_key: str, channel_id: str = "ch1", message_id: str = "m1",
                       token: str = "tok1", app_id: str = "app1") -> dict:
    return {
        "type": MESSAGE_COMPONENT,
        "channel_id": channel_id,
        "message": {"id": message_id},
        "token": token,
        "application_id": app_id,
        "data": {"custom_id": f"add_rsvp:{event_key}"},
    }


class TestAddRsvpButton:
    def test_returns_modal(self):
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            result = handle_interaction(make_add_rsvp_body("key1"))
        assert result["body"]["type"] == MODAL

    def test_modal_custom_id_contains_event_key(self):
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            result = handle_interaction(make_add_rsvp_body("ev99"))
        assert "ev99" in result["body"]["data"]["custom_id"]

    def test_stores_message_ref(self):
        with (
            patch("bench_boss.bot.store_message_ref") as mock_msg,
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            handle_interaction(make_add_rsvp_body("key1", channel_id="ch42", message_id="msg99"))
        mock_msg.assert_called_once_with("key1", "ch42", "msg99")

    def test_stores_interaction_ref(self):
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref") as mock_iref,
        ):
            handle_interaction(make_add_rsvp_body("key1", token="mytoken", app_id="myapp"))
        mock_iref.assert_called_once_with("key1", "mytoken", "myapp")


class TestRemoveRsvpButton:
    def test_returns_modal(self):
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            body = {"type": MESSAGE_COMPONENT, "data": {"custom_id": "remove_rsvp:key1"}}
            result = handle_interaction(body)
        assert result["body"]["type"] == MODAL

    def test_modal_custom_id_contains_event_key(self):
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            body = {"type": MESSAGE_COMPONENT, "data": {"custom_id": "remove_rsvp:ev99"}}
            result = handle_interaction(body)
        assert "ev99" in result["body"]["data"]["custom_id"]

    def test_stores_message_ref(self):
        body = {
            "type": MESSAGE_COMPONENT,
            "channel_id": "ch5",
            "message": {"id": "msg5"},
            "token": "t",
            "application_id": "a",
            "data": {"custom_id": "remove_rsvp:key1"},
        }
        with (
            patch("bench_boss.bot.store_message_ref") as mock_msg,
            patch("bench_boss.bot.store_interaction_ref"),
        ):
            handle_interaction(body)
        mock_msg.assert_called_once_with("key1", "ch5", "msg5")

    def test_stores_interaction_ref(self):
        body = {
            "type": MESSAGE_COMPONENT,
            "channel_id": "ch5",
            "message": {"id": "msg5"},
            "token": "mytoken",
            "application_id": "myapp",
            "data": {"custom_id": "remove_rsvp:key1"},
        }
        with (
            patch("bench_boss.bot.store_message_ref"),
            patch("bench_boss.bot.store_interaction_ref") as mock_iref,
        ):
            handle_interaction(body)
        mock_iref.assert_called_once_with("key1", "mytoken", "myapp")


# ---------------------------------------------------------------------------
# handle_interaction — RSVP edit modal submit
# ---------------------------------------------------------------------------


def make_rsvp_edit_submit(modal_type: str, event_key: str, user: str, action: str = "") -> dict:
    components = [
        {"type": 1, "components": [{"type": 4, "custom_id": "user", "value": user}]},
    ]
    if action:
        components.append(
            {"type": 1, "components": [{"type": 4, "custom_id": "action", "value": action}]}
        )
    return {
        "type": MODAL_SUBMIT,
        "data": {"custom_id": f"{modal_type}:{event_key}", "components": components},
    }


class TestRsvpEditModalSubmit:
    def test_add_calls_set_rsvp(self):
        with (
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "accepted"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "123456789", "accepted")

    def test_add_accepts_mention_format(self):
        with (
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "<@123456789>", "declined"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "123456789", "declined")

    def test_remove_calls_remove_rsvp(self):
        with (
            patch("bench_boss.bot.remove_rsvp") as mock_remove,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("remove_rsvp_modal", "key1", "123456789"), bot_token="tok")
        mock_remove.assert_called_once_with("key1", "123456789")

    def test_add_success_returns_ephemeral_confirmation(self):
        with (
            patch("bench_boss.bot.set_rsvp"),
            patch("bench_boss.bot.threading.Thread"),
        ):
            result = handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "accepted"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "123456789" in result["body"]["data"]["content"]

    def test_remove_success_returns_ephemeral_confirmation(self):
        with (
            patch("bench_boss.bot.remove_rsvp"),
            patch("bench_boss.bot.threading.Thread"),
        ):
            result = handle_interaction(make_rsvp_edit_submit("remove_rsvp_modal", "key1", "123456789"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "123456789" in result["body"]["data"]["content"]

    def test_username_resolved_via_guild_search(self):
        event = {**make_stored_event(), "guild_id": "guild1"}
        mock_get_resp = type("R", (), {"ok": True, "json": lambda self: [{"user": {"id": "999"}}]})()
        with (
            patch("bench_boss.bot.get_event", return_value=event),
            patch("bench_boss.bot.requests.get", return_value=mock_get_resp),
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "johndoe", "accepted"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "999", "accepted")

    def test_username_not_found_in_guild_returns_error(self):
        event = {**make_stored_event(), "guild_id": "guild1"}
        mock_get_resp = type("R", (), {"ok": True, "json": lambda self: []})()
        with (
            patch("bench_boss.bot.get_event", return_value=event),
            patch("bench_boss.bot.requests.get", return_value=mock_get_resp),
        ):
            result = handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "nobody", "accepted"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "Could not find" in result["body"]["data"]["content"]

    def test_no_guild_id_in_event_returns_error_for_username(self):
        with patch("bench_boss.bot.get_event", return_value=make_stored_event()):
            result = handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "johndoe", "accepted"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "Could not find" in result["body"]["data"]["content"]

    def test_single_letter_a_maps_to_accepted(self):
        with (
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "a"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "123456789", "accepted")

    def test_single_letter_d_maps_to_declined(self):
        with (
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "d"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "123456789", "declined")

    def test_single_letter_t_maps_to_tentative(self):
        with (
            patch("bench_boss.bot.set_rsvp") as mock_set,
            patch("bench_boss.bot.threading.Thread"),
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "t"), bot_token="tok")
        mock_set.assert_called_once_with("key1", "123456789", "tentative")

    def test_invalid_action_returns_ephemeral_error(self):
        with patch("bench_boss.bot.set_rsvp"):
            result = handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "bad"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "Invalid RSVP status" in result["body"]["data"]["content"]

    def test_event_not_found_returns_ephemeral_error(self):
        with patch("bench_boss.bot.set_rsvp", side_effect=ValueError):
            result = handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "accepted"), bot_token="tok")
        assert result["body"]["data"]["flags"] == 64
        assert "not found" in result["body"]["data"]["content"].lower()

    def test_add_starts_channel_update_thread(self):
        event = make_stored_event(channel_id="ch1", message_id="m1")
        with (
            patch("bench_boss.bot.set_rsvp", return_value=event),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "accepted"), bot_token="tok")
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _update_channel_message
        assert kwargs["args"] == (event, "tok")

    def test_remove_starts_channel_update_thread(self):
        event = make_stored_event(channel_id="ch1", message_id="m1")
        with (
            patch("bench_boss.bot.remove_rsvp", return_value=event),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            handle_interaction(make_rsvp_edit_submit("remove_rsvp_modal", "key1", "123456789"), bot_token="tok")
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _update_channel_message
        assert kwargs["args"] == (event, "tok")

    def test_add_skips_channel_update_when_no_token(self):
        event = make_stored_event(channel_id="ch1", message_id="m1")
        with (
            patch("bench_boss.bot.set_rsvp", return_value=event),
            patch("bench_boss.bot.threading.Thread") as mock_thread,
        ):
            handle_interaction(make_rsvp_edit_submit("add_rsvp_modal", "key1", "123456789", "accepted"))
        mock_thread.assert_not_called()

    def test_unhandled_modal_submit_returns_400(self):
        body = {"type": MODAL_SUBMIT, "data": {"custom_id": "unknown_modal:key1", "components": []}}
        result = handle_interaction(body)
        assert result["statusCode"] == 400


# ---------------------------------------------------------------------------
# handle_interaction — /events
# ---------------------------------------------------------------------------


def make_events_body(url: str, user_id: str = "user1") -> dict:
    return {
        "type": APPLICATION_COMMAND,
        "member": {"user": {"id": user_id}},
        "data": {
            "name": "events",
            "options": [{"name": "url", "value": url}],
        },
    }


class TestEventsInteraction:
    def test_missing_url_returns_ephemeral_error(self):
        body = {"type": APPLICATION_COMMAND, "data": {"name": "events", "options": []}}
        result = handle_interaction(body, bot_token="tok")
        assert result["statusCode"] == 200
        assert "No calendar URL provided" in result["body"]["data"]["content"]
        assert result["body"]["data"]["flags"] == 64

    def test_missing_bot_token_returns_ephemeral_error(self):
        result = handle_interaction(make_events_body("https://example.com/cal.ics"))
        assert result["statusCode"] == 200
        assert "Could not determine" in result["body"]["data"]["content"]
        assert result["body"]["data"]["flags"] == 64

    def test_success_returns_ephemeral_and_starts_thread(self):
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            result = handle_interaction(make_events_body("https://example.com/cal.ics"), bot_token="tok")
        assert result["statusCode"] == 200
        assert result["body"]["data"]["flags"] == 64
        assert "DM" in result["body"]["data"]["content"]
        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args[1]
        assert kwargs["target"] == _send_dm_events
        assert kwargs["args"] == ("https://example.com/cal.ics", "user1", "tok")

    def test_user_id_from_top_level_user_field(self):
        body = {
            "type": APPLICATION_COMMAND,
            "user": {"id": "user99"},
            "data": {"name": "events", "options": [{"name": "url", "value": "https://example.com/cal.ics"}]},
        }
        with patch("bench_boss.bot.threading.Thread") as mock_thread:
            handle_interaction(body, bot_token="tok")
        kwargs = mock_thread.call_args[1]
        assert kwargs["args"][1] == "user99"


class TestSendDmEvents:
    def _make_mock_requests(self, events, dm_channel_id="dm123"):
        import unittest.mock as mock

        dm_resp = mock.MagicMock()
        dm_resp.ok = True
        dm_resp.json.return_value = {"id": dm_channel_id}

        msg_resp = mock.MagicMock()
        msg_resp.ok = True

        return dm_resp, msg_resp

    def test_sends_event_list_as_dm(self):
        ev = make_calendar_event("Game Night")
        dm_resp, msg_resp = self._make_mock_requests([ev])
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.requests.post", side_effect=[dm_resp, msg_resp]) as mock_post,
        ):
            mock_reader.return_value.get_remaining.return_value = [ev]
            _send_dm_events("https://example.com/cal.ics", "user1", "tok")

        assert mock_post.call_count == 2
        # Second call sends the message to the DM channel
        msg_call_kwargs = mock_post.call_args_list[1][1]
        content = msg_call_kwargs["json"]["content"]
        assert "Game Night" in content
        assert "Remaining events from calendar" in content

    def test_empty_calendar_sends_no_events_message(self):
        dm_resp, msg_resp = self._make_mock_requests([])
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.requests.post", side_effect=[dm_resp, msg_resp]) as mock_post,
        ):
            mock_reader.return_value.get_remaining.return_value = []
            _send_dm_events("https://example.com/cal.ics", "user1", "tok")

        msg_call_kwargs = mock_post.call_args_list[1][1]
        assert "No events found" in msg_call_kwargs["json"]["content"]

    def test_calendar_fetch_failure_aborts_silently(self):
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.requests.post") as mock_post,
        ):
            mock_reader.return_value.get_remaining.side_effect = Exception("timeout")
            _send_dm_events("https://example.com/cal.ics", "user1", "tok")

        mock_post.assert_not_called()

    def test_dm_channel_creation_failure_aborts(self):
        import unittest.mock as mock

        dm_resp = mock.MagicMock()
        dm_resp.ok = False
        dm_resp.status_code = 403

        ev = make_calendar_event()
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.requests.post", return_value=dm_resp) as mock_post,
        ):
            mock_reader.return_value.get_remaining.return_value = [ev]
            _send_dm_events("https://example.com/cal.ics", "user1", "tok")

        assert mock_post.call_count == 1  # Only the DM channel creation, no message sent

    def test_long_event_list_truncated_to_2000_chars(self):
        events = [make_calendar_event(f"Event {'X' * 100} {i}") for i in range(30)]
        dm_resp, msg_resp = self._make_mock_requests(events)
        with (
            patch("bench_boss.bot.WebCalReader") as mock_reader,
            patch("bench_boss.bot.requests.post", side_effect=[dm_resp, msg_resp]) as mock_post,
        ):
            mock_reader.return_value.get_remaining.return_value = events
            _send_dm_events("https://example.com/cal.ics", "user1", "tok")

        msg_call_kwargs = mock_post.call_args_list[1][1]
        assert len(msg_call_kwargs["json"]["content"]) <= 2000


class TestFormatEventLine:
    def test_datetime_event(self):
        from bench_boss.calendar import CalendarEvent

        start = datetime(2026, 3, 28, 10, 0, tzinfo=UTC)
        ev = CalendarEvent(summary="Standup", start=start, end=None, location=None, description=None)
        line = _format_event_line(ev)
        assert "Standup" in line
        assert "Mar" in line
        assert "28" in line

    def test_all_day_event(self):
        from datetime import date

        from bench_boss.calendar import CalendarEvent

        ev = CalendarEvent(summary="All Day", start=date(2026, 4, 1), end=None, location=None, description=None)
        line = _format_event_line(ev)
        assert "All day" in line
        assert "All Day" in line

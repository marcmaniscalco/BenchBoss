from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from bench_boss.discord_api import EXTERNAL, GUILD_ONLY, create_scheduled_event

GUILD_ID = "123456789"
BOT_TOKEN = "test-token"
BASE_URL = f"https://discord.com/api/v10/guilds/{GUILD_ID}/scheduled-events"


def make_start(offset_hours: int = 2) -> datetime:
    return datetime.now(tz=UTC) + timedelta(hours=offset_hours)


def mock_post(response_json: dict, status_code: int = 200):
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_response.status_code = status_code
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            response=mock_response
        )
    else:
        mock_response.raise_for_status.return_value = None
    return patch("bench_boss.discord_api.requests.post", return_value=mock_response)


# ---------------------------------------------------------------------------
# Successful creation
# ---------------------------------------------------------------------------


class TestCreateScheduledEvent:
    def test_returns_created_event(self):
        start = make_start()
        expected = {"id": "999", "name": "Team Standup"}
        with mock_post(expected):
            result = create_scheduled_event(
                GUILD_ID, "Team Standup", start, None, None, BOT_TOKEN
            )
        assert result == expected

    def test_posts_to_correct_url(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        mock.assert_called_once()
        assert mock.call_args[0][0] == BASE_URL

    def test_sends_bot_token_header(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        headers = mock.call_args[1]["headers"]
        assert headers["Authorization"] == f"Bot {BOT_TOKEN}"

    def test_payload_entity_type_is_external(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert payload["entity_type"] == EXTERNAL

    def test_payload_privacy_level_is_guild_only(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert payload["privacy_level"] == GUILD_ONLY

    def test_payload_contains_name(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "My Event", start, None, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert payload["name"] == "My Event"

    def test_payload_location_uses_provided_value(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, "Room 1", BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert payload["entity_metadata"]["location"] == "Room 1"

    def test_payload_location_defaults_to_tbd_when_none(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert payload["entity_metadata"]["location"] == "TBD"


# ---------------------------------------------------------------------------
# End time handling
# ---------------------------------------------------------------------------


class TestEndTime:
    def test_end_defaults_to_one_hour_after_start_when_none(self):
        start = make_start()
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        start_dt = datetime.fromisoformat(payload["scheduled_start_time"])
        end_dt = datetime.fromisoformat(payload["scheduled_end_time"])
        assert end_dt - start_dt == timedelta(hours=1)

    def test_provided_end_time_is_used(self):
        start = make_start()
        end = start + timedelta(hours=3)
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, end, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        end_dt = datetime.fromisoformat(payload["scheduled_end_time"])
        start_dt = datetime.fromisoformat(payload["scheduled_start_time"])
        assert end_dt - start_dt == timedelta(hours=3)


# ---------------------------------------------------------------------------
# Timezone handling
# ---------------------------------------------------------------------------


class TestTimezone:
    def test_naive_start_gets_utc_tzinfo(self):
        naive_start = datetime(2026, 6, 1, 9, 0)
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(
                GUILD_ID, "Event", naive_start, None, None, BOT_TOKEN
            )
        payload = mock.call_args[1]["json"]
        ts = payload["scheduled_start_time"]
        assert "+00:00" in ts or "Z" in ts or "UTC" in ts or ts.endswith("+00:00")

    def test_naive_end_gets_utc_tzinfo(self):
        start = make_start()
        naive_end = datetime(2026, 6, 1, 10, 0)
        with mock_post({"id": "1"}) as mock:
            create_scheduled_event(GUILD_ID, "Event", start, naive_end, None, BOT_TOKEN)
        payload = mock.call_args[1]["json"]
        assert "scheduled_end_time" in payload


# ---------------------------------------------------------------------------
# HTTP errors
# ---------------------------------------------------------------------------


class TestHttpErrors:
    def test_raises_on_403(self):
        start = make_start()
        with mock_post({}, status_code=403):
            with pytest.raises(requests.HTTPError):
                create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)

    def test_raises_on_401(self):
        start = make_start()
        with mock_post({}, status_code=401):
            with pytest.raises(requests.HTTPError):
                create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)

    def test_raises_on_500(self):
        start = make_start()
        with mock_post({}, status_code=500):
            with pytest.raises(requests.HTTPError):
                create_scheduled_event(GUILD_ID, "Event", start, None, None, BOT_TOKEN)

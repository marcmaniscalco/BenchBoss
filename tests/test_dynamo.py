from unittest.mock import MagicMock, patch

import pytest

from bench_boss.dynamo import get_event, save_event, update_rsvp


@pytest.fixture()
def mock_table(monkeypatch):
    monkeypatch.setenv("DYNAMODB_TABLE", "test-table")
    with patch("bench_boss.dynamo.boto3") as mock_boto3:
        table = MagicMock()
        mock_boto3.resource.return_value.Table.return_value = table
        yield table


START = "2026-04-05T19:00:00+00:00"
END = "2026-04-05T20:00:00+00:00"


# ---------------------------------------------------------------------------
# save_event
# ---------------------------------------------------------------------------


class TestSaveEvent:
    def test_puts_item_with_event_key(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["event_key"] == "key1"

    def test_stores_name_and_start(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["name"] == "My Event"
        assert item["start"] == START

    def test_initializes_empty_rsvp_lists(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["accepted"] == []
        assert item["declined"] == []
        assert item["maybe"] == []
        assert item["late"] == []

    def test_omits_none_optional_fields(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "end" not in item
        assert "location" not in item
        assert "description" not in item

    def test_stores_optional_fields_when_provided(self, mock_table):
        save_event("key1", "My Event", START, END, "Room 1", "Fun event")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["end"] == END
        assert item["location"] == "Room 1"
        assert item["description"] == "Fun event"


# ---------------------------------------------------------------------------
# get_event
# ---------------------------------------------------------------------------


class TestGetEvent:
    def test_returns_item_when_found(self, mock_table):
        expected = {"event_key": "key1", "name": "My Event"}
        mock_table.get_item.return_value = {"Item": expected}
        assert get_event("key1") == expected

    def test_returns_none_when_not_found(self, mock_table):
        mock_table.get_item.return_value = {}
        assert get_event("missing") is None

    def test_passes_correct_key(self, mock_table):
        mock_table.get_item.return_value = {}
        get_event("abc123")
        mock_table.get_item.assert_called_once_with(Key={"event_key": "abc123"})


# ---------------------------------------------------------------------------
# update_rsvp
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> dict:
    base = {
        "event_key": "key1",
        "name": "My Event",
        "start": START,
        "accepted": [],
        "declined": [],
        "maybe": [],
        "late": [],
    }
    base.update(overrides)
    return base


class TestUpdateRsvp:
    def test_adds_user_to_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = update_rsvp("key1", "user1", "accepted")
        assert "user1" in result["accepted"]

    def test_moves_user_from_old_action_to_new(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = update_rsvp("key1", "user1", "declined")
        assert "user1" not in result["accepted"]
        assert "user1" in result["declined"]

    def test_toggles_off_when_clicking_same_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = update_rsvp("key1", "user1", "accepted")
        assert "user1" not in result["accepted"]

    def test_user_appears_in_only_one_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(maybe=["user1"])}
        result = update_rsvp("key1", "user1", "late")
        counts = sum(
            "user1" in result.get(a, [])
            for a in ("accepted", "declined", "maybe", "late")
        )
        assert counts == 1

    def test_raises_when_event_not_found(self, mock_table):
        mock_table.get_item.return_value = {}
        with pytest.raises(ValueError):
            update_rsvp("missing", "user1", "accepted")

    def test_saves_updated_event_to_dynamo(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        update_rsvp("key1", "user1", "accepted")
        mock_table.put_item.assert_called_once()

    def test_multiple_users_can_rsvp_same_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = update_rsvp("key1", "user2", "accepted")
        assert "user1" in result["accepted"]
        assert "user2" in result["accepted"]

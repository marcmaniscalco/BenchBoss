from unittest.mock import MagicMock, patch

import pytest

from bench_boss.dynamo import (
    _ttl_timestamp,
    delete_event,
    find_event_in_channel,
    get_event,
    remove_rsvp,
    save_event,
    set_goalie,
    set_rsvp,
    store_interaction_ref,
    store_message_ref,
    update_rsvp,
)


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
        assert item["tentative"] == []
        assert item["goalie"] == []

    def test_omits_none_optional_fields(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "end" not in item
        assert "location" not in item
        assert "description" not in item

    def test_stores_ttl_field(self, mock_table):
        save_event("key1", "My Event", START, END, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "ttl" in item
        assert isinstance(item["ttl"], int)

    def test_ttl_is_24h_after_end(self, mock_table):
        save_event("key1", "My Event", START, END, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["ttl"] == _ttl_timestamp(END, START)

    def test_ttl_falls_back_to_start_when_no_end(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["ttl"] == _ttl_timestamp(None, START)

    def test_stores_optional_fields_when_provided(self, mock_table):
        save_event("key1", "My Event", START, END, "Room 1", "Fun event")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["end"] == END
        assert item["location"] == "Room 1"
        assert item["description"] == "Fun event"

    def test_stores_guild_id_when_provided(self, mock_table):
        save_event("key1", "My Event", START, None, None, None, guild_id="guild123")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["guild_id"] == "guild123"

    def test_omits_guild_id_when_none(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "guild_id" not in item

    def test_stores_webcal_url_when_provided(self, mock_table):
        save_event("key1", "My Event", START, None, None, None, webcal_url="https://example.com/cal.ics")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["webcal_url"] == "https://example.com/cal.ics"

    def test_omits_webcal_url_when_none(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "webcal_url" not in item

    def test_stores_channel_id_when_provided(self, mock_table):
        save_event("key1", "My Event", START, None, None, None, channel_id="ch1")
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["channel_id"] == "ch1"

    def test_omits_channel_id_when_none(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "channel_id" not in item

    def test_stores_created_at_field(self, mock_table):
        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        assert "created_at" in item

    def test_created_at_is_iso8601_string(self, mock_table):
        from datetime import datetime

        save_event("key1", "My Event", START, None, None, None)
        item = mock_table.put_item.call_args[1]["Item"]
        dt = datetime.fromisoformat(item["created_at"])
        assert dt.tzinfo is not None  # timezone-aware


# ---------------------------------------------------------------------------
# find_event_in_channel
# ---------------------------------------------------------------------------


class TestFindEventInChannel:
    def test_returns_item_when_match_found(self, mock_table):
        mock_table.scan.return_value = {"Items": [{"event_key": "key1", "name": "My Event"}]}
        result = find_event_in_channel("ch1", "My Event", START)
        assert result["event_key"] == "key1"

    def test_returns_none_when_no_match(self, mock_table):
        mock_table.scan.return_value = {"Items": []}
        result = find_event_in_channel("ch1", "My Event", START)
        assert result is None

    def test_scans_with_filter_expression(self, mock_table):
        mock_table.scan.return_value = {"Items": []}
        find_event_in_channel("ch1", "My Event", START)
        mock_table.scan.assert_called_once()
        assert "FilterExpression" in mock_table.scan.call_args[1]


# ---------------------------------------------------------------------------
# delete_event
# ---------------------------------------------------------------------------


class TestDeleteEvent:
    def test_calls_delete_item_with_event_key(self, mock_table):
        delete_event("key1")
        mock_table.delete_item.assert_called_once_with(Key={"event_key": "key1"})


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
        "tentative": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# store_message_ref
# ---------------------------------------------------------------------------


class TestStoreMessageRef:
    def test_calls_update_item_with_event_key(self, mock_table):
        store_message_ref("key1", "ch1", "msg1")
        mock_table.update_item.assert_called_once()
        key = mock_table.update_item.call_args[1]["Key"]
        assert key == {"event_key": "key1"}

    def test_sets_channel_id_and_message_id(self, mock_table):
        store_message_ref("key1", "ch42", "msg99")
        kwargs = mock_table.update_item.call_args[1]
        values = kwargs["ExpressionAttributeValues"]
        assert values[":c"] == "ch42"
        assert values[":m"] == "msg99"


class TestStoreInteractionRef:
    def test_calls_update_item_with_event_key(self, mock_table):
        store_interaction_ref("key1", "tok123", "app456")
        mock_table.update_item.assert_called_once()
        key = mock_table.update_item.call_args[1]["Key"]
        assert key == {"event_key": "key1"}

    def test_sets_interaction_token_and_app_id(self, mock_table):
        store_interaction_ref("key1", "mytoken", "myapp")
        kwargs = mock_table.update_item.call_args[1]
        values = kwargs["ExpressionAttributeValues"]
        assert values[":t"] == "mytoken"
        assert values[":a"] == "myapp"


# ---------------------------------------------------------------------------
# set_rsvp
# ---------------------------------------------------------------------------


class TestSetRsvp:
    def test_adds_user_to_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = set_rsvp("key1", "user1", "accepted")
        assert "user1" in result["accepted"]

    def test_always_adds_even_if_already_in_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = set_rsvp("key1", "user1", "accepted")
        assert "user1" in result["accepted"]

    def test_moves_user_from_old_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(declined=["user1"])}
        result = set_rsvp("key1", "user1", "tentative")
        assert "user1" not in result["declined"]
        assert "user1" in result["tentative"]

    def test_user_appears_in_only_one_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = set_rsvp("key1", "user1", "declined")
        counts = sum("user1" in result.get(a, []) for a in ("accepted", "declined", "tentative"))
        assert counts == 1

    def test_raises_when_event_not_found(self, mock_table):
        mock_table.get_item.return_value = {}
        with pytest.raises(ValueError):
            set_rsvp("missing", "user1", "accepted")

    def test_saves_updated_event_to_dynamo(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        set_rsvp("key1", "user1", "accepted")
        mock_table.put_item.assert_called_once()

    def test_stores_display_name_when_provided(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = set_rsvp("key1", "user1", "accepted", display_name="Bob")
        assert result["member_names"]["user1"] == "Bob"

    def test_no_display_name_stored_when_none(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = set_rsvp("key1", "user1", "accepted", display_name=None)
        assert "user1" not in result.get("member_names", {})

    def test_removes_user_from_goalie_when_set_rsvp(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = set_rsvp("key1", "user1", "accepted")
        assert result["goalie"] == []
        assert "user1" in result["accepted"]


# ---------------------------------------------------------------------------
# remove_rsvp
# ---------------------------------------------------------------------------


class TestRemoveRsvp:
    def test_removes_user_from_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = remove_rsvp("key1", "user1")
        assert "user1" not in result["accepted"]

    def test_user_absent_from_all_actions_after_remove(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(tentative=["user1"])}
        result = remove_rsvp("key1", "user1")
        for a in ("accepted", "declined", "tentative"):
            assert "user1" not in result.get(a, [])

    def test_raises_when_user_not_in_any_action(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        with pytest.raises(ValueError, match="not in the RSVP list"):
            remove_rsvp("key1", "user1")

    def test_removes_user_from_goalie(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = remove_rsvp("key1", "user1")
        assert result["goalie"] == []

    def test_user_only_in_goalie_does_not_raise(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = remove_rsvp("key1", "user1")
        assert result["goalie"] == []

    def test_raises_when_event_not_found(self, mock_table):
        mock_table.get_item.return_value = {}
        with pytest.raises(ValueError):
            remove_rsvp("missing", "user1")

    def test_saves_updated_event_to_dynamo(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        remove_rsvp("key1", "user1")
        mock_table.put_item.assert_called_once()

    def test_removes_display_name_on_removal(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(
            accepted=["user1"], member_names={"user1": "Alice"}
        )}
        result = remove_rsvp("key1", "user1")
        assert "user1" not in result["member_names"]


# ---------------------------------------------------------------------------
# update_rsvp
# ---------------------------------------------------------------------------


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
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = update_rsvp("key1", "user1", "tentative")
        counts = sum(
            "user1" in result.get(a, [])
            for a in ("accepted", "declined", "tentative")
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

    def test_stores_display_name_when_adding(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = update_rsvp("key1", "user1", "accepted", display_name="Alice")
        assert result["member_names"]["user1"] == "Alice"

    def test_removes_display_name_on_toggle_off(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(
            accepted=["user1"], member_names={"user1": "Alice"}
        )}
        result = update_rsvp("key1", "user1", "accepted")
        assert "user1" not in result["member_names"]

    def test_no_display_name_stored_when_none(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = update_rsvp("key1", "user1", "accepted", display_name=None)
        assert "user1" not in result.get("member_names", {})

    def test_removes_user_from_goalie_when_update_rsvp(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = update_rsvp("key1", "user1", "accepted")
        assert result["goalie"] == []
        assert "user1" in result["accepted"]


# ---------------------------------------------------------------------------
# set_goalie
# ---------------------------------------------------------------------------


class TestSetGoalie:
    def test_sets_user_as_goalie(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = set_goalie("key1", "user1")
        assert result["goalie"] == ["user1"]

    def test_replaces_existing_goalie(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = set_goalie("key1", "user2")
        assert result["goalie"] == ["user2"]
        assert "user1" not in result["goalie"]

    def test_toggles_off_when_user_is_already_goalie(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(goalie=["user1"])}
        result = set_goalie("key1", "user1")
        assert result["goalie"] == []

    def test_stores_display_name_when_provided(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        result = set_goalie("key1", "user1", display_name="Alice")
        assert result["member_names"]["user1"] == "Alice"

    def test_removes_display_name_on_toggle_off(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(
            goalie=["user1"], member_names={"user1": "Alice"}
        )}
        result = set_goalie("key1", "user1")
        assert "user1" not in result["member_names"]

    def test_removes_old_goalie_display_name_on_replace(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(
            goalie=["user1"], member_names={"user1": "Alice"}
        )}
        result = set_goalie("key1", "user2", display_name="Bob")
        assert "user1" not in result["member_names"]
        assert result["member_names"]["user2"] == "Bob"

    def test_raises_when_event_not_found(self, mock_table):
        mock_table.get_item.return_value = {}
        with pytest.raises(ValueError):
            set_goalie("missing", "user1")

    def test_saves_updated_event_to_dynamo(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event()}
        set_goalie("key1", "user1")
        mock_table.put_item.assert_called_once()

    def test_removes_user_from_rsvp_lists_when_set_as_goalie(self, mock_table):
        mock_table.get_item.return_value = {"Item": _make_event(accepted=["user1"])}
        result = set_goalie("key1", "user1")
        assert "user1" not in result["accepted"]
        assert result["goalie"] == ["user1"]

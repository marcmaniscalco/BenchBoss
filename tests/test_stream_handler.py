from unittest.mock import MagicMock, patch

from bench_boss.stream_handler import handle_stream_records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_remove_record(
    event_key="key1",
    channel_id="ch1",
    message_id="msg1",
    identity_type="Service",
):
    record = {
        "eventName": "REMOVE",
        "dynamodb": {
            "OldImage": {
                "event_key": {"S": event_key},
            }
        },
    }
    if identity_type:
        record["userIdentity"] = {"type": identity_type, "principalId": "dynamodb.amazonaws.com"}
    if channel_id:
        record["dynamodb"]["OldImage"]["channel_id"] = {"S": channel_id}
    if message_id:
        record["dynamodb"]["OldImage"]["message_id"] = {"S": message_id}
    return record


def make_insert_record():
    return {
        "eventName": "INSERT",
        "dynamodb": {"NewImage": {"event_key": {"S": "key1"}}},
    }


def make_modify_record():
    return {
        "eventName": "MODIFY",
        "dynamodb": {
            "NewImage": {"event_key": {"S": "key1"}},
            "OldImage": {"event_key": {"S": "key1"}},
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHandleStreamRecords:
    def test_ttl_expiration_deletes_discord_message(self):
        record = make_remove_record()
        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("bench_boss.stream_handler.requests.delete", return_value=mock_resp) as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_called_once_with(
            "https://discord.com/api/v10/channels/ch1/messages/msg1",
            headers={"Authorization": "Bot tok"},
        )

    def test_manual_delete_is_ignored(self):
        record = make_remove_record(identity_type="IAMUser")
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()

    def test_non_remove_event_is_ignored(self):
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([make_insert_record(), make_modify_record()], bot_token="tok")
        mock_del.assert_not_called()

    def test_missing_channel_id_skips_discord_delete(self):
        record = make_remove_record(channel_id=None)
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()

    def test_missing_message_id_skips_discord_delete(self):
        record = make_remove_record(message_id=None)
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()

    def test_discord_delete_failure_does_not_raise(self):
        record = make_remove_record()
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 404
        mock_resp.text = "Unknown Message"
        with patch("bench_boss.stream_handler.requests.delete", return_value=mock_resp):
            handle_stream_records([record], bot_token="tok")  # should not raise

    def test_empty_records_does_nothing(self):
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([], bot_token="tok")
        mock_del.assert_not_called()

    def test_processes_multiple_records(self):
        records = [make_remove_record(event_key=f"key{i}", channel_id=f"ch{i}", message_id=f"msg{i}") for i in range(3)]
        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("bench_boss.stream_handler.requests.delete", return_value=mock_resp) as mock_del:
            handle_stream_records(records, bot_token="tok")
        assert mock_del.call_count == 3

    def test_missing_user_identity_is_ignored(self):
        record = make_remove_record(identity_type="ignored")
        record.pop("userIdentity", None)
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()
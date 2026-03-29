from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from bench_boss.calendar import CalendarEvent
from bench_boss.stream_handler import handle_stream_records

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_remove_record(
    event_key="key1",
    channel_id="ch1",
    message_id="msg1",
    webcal_url="https://example.com/cal.ics",
    guild_id="guild1",
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
    if webcal_url:
        record["dynamodb"]["OldImage"]["webcal_url"] = {"S": webcal_url}
    if guild_id:
        record["dynamodb"]["OldImage"]["guild_id"] = {"S": guild_id}
    return record


def make_insert_record():
    return {"eventName": "INSERT", "dynamodb": {"NewImage": {"event_key": {"S": "key1"}}}}


def make_calendar_event(summary="Game Night", days_ahead=1):
    start = datetime.now(tz=UTC) + timedelta(days=days_ahead)
    return CalendarEvent(
        summary=summary,
        start=start,
        end=start + timedelta(hours=1),
        location=None,
        description=None,
    )


def mock_ok_response(body=None):
    resp = MagicMock()
    resp.ok = True
    resp.json.return_value = body or {}
    return resp


def mock_fail_response(status=404, text="Not Found"):
    resp = MagicMock()
    resp.ok = False
    resp.status_code = status
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Non-TTL / non-REMOVE records are ignored
# ---------------------------------------------------------------------------


class TestIgnoredRecords:
    def test_insert_event_is_ignored(self):
        with patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([make_insert_record()], bot_token="tok")
        mock_post.assert_not_called()
        mock_del.assert_not_called()

    def test_manual_delete_is_ignored(self):
        record = make_remove_record(identity_type="IAMUser")
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()

    def test_missing_user_identity_is_ignored(self):
        record = make_remove_record()
        record.pop("userIdentity", None)
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_del.assert_not_called()

    def test_missing_channel_id_skips_all_discord_calls(self):
        record = make_remove_record(channel_id=None)
        with patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_post.assert_not_called()
        mock_del.assert_not_called()

    def test_missing_message_id_skips_all_discord_calls(self):
        record = make_remove_record(message_id=None)
        with patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([record], bot_token="tok")
        mock_post.assert_not_called()
        mock_del.assert_not_called()

    def test_empty_records_does_nothing(self):
        with patch("bench_boss.stream_handler.requests.delete") as mock_del:
            handle_stream_records([], bot_token="tok")
        mock_del.assert_not_called()


# ---------------------------------------------------------------------------
# TTL expiration — next event exists
# ---------------------------------------------------------------------------


class TestNextEventPosted:
    def test_posts_new_embed_then_deletes_old_message(self):
        ev = make_calendar_event("Playoffs")
        post_resp = mock_ok_response({"id": "new_msg_id"})
        del_resp = mock_ok_response()

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event"), \
             patch("bench_boss.stream_handler.store_message_ref"), \
             patch("bench_boss.stream_handler.requests.post", return_value=post_resp) as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=del_resp) as mock_del:
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_post.assert_called_once()
        mock_del.assert_called_once_with(
            "https://discord.com/api/v10/channels/ch1/messages/msg1",
            headers={"Authorization": "Bot tok"},
            timeout=10,
        )

    def test_new_embed_posted_to_same_channel(self):
        ev = make_calendar_event()
        post_resp = mock_ok_response({"id": "new_msg_id"})

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event"), \
             patch("bench_boss.stream_handler.store_message_ref"), \
             patch("bench_boss.stream_handler.requests.post", return_value=post_resp) as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()):
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        assert "ch1" in mock_post.call_args[0][0]

    def test_saves_new_event_to_dynamo_with_webcal_url(self):
        ev = make_calendar_event()
        post_resp = mock_ok_response({"id": "new_msg_id"})

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event") as mock_save, \
             patch("bench_boss.stream_handler.store_message_ref"), \
             patch("bench_boss.stream_handler.requests.post", return_value=post_resp), \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()):
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_save.assert_called_once()
        kwargs = mock_save.call_args[1]
        assert kwargs["webcal_url"] == "https://example.com/cal.ics"
        assert kwargs["guild_id"] == "guild1"
        assert kwargs["name"] == "Game Night"

    def test_stores_new_message_ref_after_post(self):
        ev = make_calendar_event()
        post_resp = mock_ok_response({"id": "new_msg_999"})

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event"), \
             patch("bench_boss.stream_handler.store_message_ref") as mock_store, \
             patch("bench_boss.stream_handler.requests.post", return_value=post_resp), \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()):
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_store.assert_called_once()
        args = mock_store.call_args[0]
        assert args[1] == "ch1"
        assert args[2] == "new_msg_999"

    def test_dynamo_save_failure_skips_post_but_still_deletes(self):
        ev = make_calendar_event()

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event", side_effect=Exception("DynamoDB down")), \
             patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()) as mock_del:
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_post.assert_not_called()
        mock_del.assert_called_once()

    def test_discord_post_failure_still_deletes_old_message(self):
        ev = make_calendar_event()

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.save_event"), \
             patch("bench_boss.stream_handler.store_message_ref"), \
             patch("bench_boss.stream_handler.requests.post", return_value=mock_fail_response()), \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()) as mock_del:
            mock_reader.return_value.get_remaining.return_value = [ev]
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_del.assert_called_once()


# ---------------------------------------------------------------------------
# TTL expiration — no more events
# ---------------------------------------------------------------------------


class TestNoMoreEvents:
    def test_posts_no_more_events_message_with_url(self):
        post_resp = mock_ok_response()

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.requests.post", return_value=post_resp) as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()):
            mock_reader.return_value.get_remaining.return_value = []
            handle_stream_records([make_remove_record()], bot_token="tok")

        content = mock_post.call_args[1]["json"]["content"]
        assert "https://example.com/cal.ics" in content
        assert "No more events" in content

    def test_no_more_events_still_deletes_old_message(self):
        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.requests.post", return_value=mock_ok_response()), \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()) as mock_del:
            mock_reader.return_value.get_remaining.return_value = []
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_del.assert_called_once()

    def test_no_webcal_url_skips_calendar_fetch_and_just_deletes(self):
        record = make_remove_record(webcal_url=None)

        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()):
            handle_stream_records([record], bot_token="tok")

        mock_reader.assert_not_called()
        mock_post.assert_not_called()

    def test_calendar_fetch_failure_still_deletes_old_message(self):
        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.requests.post") as mock_post, \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()) as mock_del:
            mock_reader.return_value.get_remaining.side_effect = Exception("timeout")
            handle_stream_records([make_remove_record()], bot_token="tok")

        mock_post.assert_not_called()
        mock_del.assert_called_once()

    def test_discord_delete_failure_does_not_raise(self):
        with patch("bench_boss.stream_handler.WebCalReader") as mock_reader, \
             patch("bench_boss.stream_handler.requests.post", return_value=mock_ok_response()), \
             patch("bench_boss.stream_handler.requests.delete", return_value=mock_fail_response()):
            mock_reader.return_value.get_remaining.return_value = []
            handle_stream_records([make_remove_record()], bot_token="tok")  # must not raise


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    def test_processes_multiple_records(self):
        records = [
            make_remove_record(event_key=f"key{i}", channel_id=f"ch{i}", message_id=f"msg{i}", webcal_url=None)
            for i in range(3)
        ]
        with patch("bench_boss.stream_handler.requests.delete", return_value=mock_ok_response()) as mock_del:
            handle_stream_records(records, bot_token="tok")
        assert mock_del.call_count == 3

"""Tests for the Lambda DynamoDB stream handler entry point."""

import os
from unittest.mock import patch

os.environ["DISCORD_TOKEN"] = "test-bot-token"

import stream_lambda_handler  # noqa: E402


def test_records_are_forwarded_with_bot_token():
    event = {"Records": [{"eventName": "REMOVE"}, {"eventName": "REMOVE"}]}

    with patch("stream_lambda_handler.handle_stream_records") as mock_handle:
        result = stream_lambda_handler.stream_lambda_handler(event, context=None)

    assert result is None
    mock_handle.assert_called_once_with(
        event["Records"], bot_token="test-bot-token"
    )


def test_missing_records_passes_empty_list():
    with patch("stream_lambda_handler.handle_stream_records") as mock_handle:
        stream_lambda_handler.stream_lambda_handler({}, context=None)

    mock_handle.assert_called_once_with([], bot_token="test-bot-token")

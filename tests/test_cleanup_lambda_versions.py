from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from cleanup_lambda_versions import (
    GRACE_PERIOD,
    _cleanup_function,
    _older_than_grace_period,
)


def _make_lambda_client(live_version: str, versions: list[dict]) -> MagicMock:
    client = MagicMock()
    client.get_alias.return_value = {"FunctionVersion": live_version}
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Versions": versions}]
    client.get_paginator.return_value = paginator
    return client


# ---------------------------------------------------------------------------
# _older_than_grace_period
# ---------------------------------------------------------------------------


class TestOlderThanGracePeriod:
    def test_timestamp_older_than_grace_period(self):
        now = datetime.now(UTC)
        old = (now - GRACE_PERIOD - timedelta(minutes=1)).isoformat()
        assert _older_than_grace_period(old, now, function_name="f", version="5")

    def test_timestamp_within_grace_period(self):
        now = datetime.now(UTC)
        recent = (now - timedelta(minutes=1)).isoformat()
        assert not _older_than_grace_period(recent, now, function_name="f", version="8")

    def test_real_lambda_format_is_parsed_correctly(self):
        # Lambda's actual LastModified format -- "+0000", no colon in the
        # offset -- not .isoformat()'s "+00:00". The other tests here all
        # use .isoformat() and would stay green even if fromisoformat
        # stopped accepting Lambda's real format, so this one pins that
        # specifically.
        now = datetime.now(UTC)
        real_format = "2024-01-01T12:00:00.000+0000"
        assert _older_than_grace_period(
            real_format, now, function_name="f", version="5"
        )

    def test_unparseable_timestamp_is_kept(self):
        now = datetime.now(UTC)
        assert not _older_than_grace_period(
            "not-a-timestamp", now, function_name="f", version="4"
        )

    def test_missing_timestamp_is_kept(self):
        now = datetime.now(UTC)
        assert not _older_than_grace_period("", now, function_name="f", version="4")

    def test_unparseable_timestamp_prints_a_warning(self, capsys):
        now = datetime.now(UTC)
        _older_than_grace_period(
            "not-a-timestamp", now, function_name="my-func", version="4"
        )
        output = capsys.readouterr().out
        assert "my-func:4" in output
        assert "not-a-timestamp" in output


# ---------------------------------------------------------------------------
# _cleanup_function
# ---------------------------------------------------------------------------


class TestCleanupFunction:
    def test_deletes_version_older_than_grace_period(self):
        now = datetime.now(UTC)
        old_time = (now - GRACE_PERIOD - timedelta(minutes=1)).isoformat()
        client = _make_lambda_client(
            "7",
            [
                {"Version": "$LATEST", "LastModified": now.isoformat()},
                {"Version": "7", "LastModified": old_time},
                {"Version": "5", "LastModified": old_time},
            ],
        )
        _cleanup_function(client, "my-func")
        client.delete_function.assert_called_once_with(
            FunctionName="my-func", Qualifier="5"
        )

    def test_skips_version_newer_than_grace_period(self):
        # The exact scenario that caused the production incident this
        # grace period fixes: a version published moments ago by a
        # still-in-flight deploy, not yet pointed to by `live`.
        now = datetime.now(UTC)
        recent_time = (now - timedelta(minutes=1)).isoformat()
        client = _make_lambda_client(
            "7",
            [
                {"Version": "$LATEST", "LastModified": now.isoformat()},
                {"Version": "7", "LastModified": recent_time},
                {"Version": "8", "LastModified": recent_time},
            ],
        )
        _cleanup_function(client, "my-func")
        client.delete_function.assert_not_called()

    def test_latest_and_live_version_are_never_deleted(self):
        now = datetime.now(UTC)
        old_time = (now - GRACE_PERIOD - timedelta(minutes=1)).isoformat()
        client = _make_lambda_client(
            "7",
            [
                {"Version": "$LATEST", "LastModified": old_time},
                {"Version": "7", "LastModified": old_time},
            ],
        )
        _cleanup_function(client, "my-func")
        client.delete_function.assert_not_called()

    def test_unparseable_timestamp_is_kept_not_deleted(self):
        now = datetime.now(UTC)
        client = _make_lambda_client(
            "7",
            [
                {"Version": "$LATEST", "LastModified": now.isoformat()},
                {"Version": "7", "LastModified": now.isoformat()},
                {"Version": "4", "LastModified": "garbage"},
            ],
        )
        _cleanup_function(client, "my-func")
        client.delete_function.assert_not_called()

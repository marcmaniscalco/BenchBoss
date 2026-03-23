from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from bench_boss.calendar import CalendarEvent, WebCalReader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ical(events: list[dict]) -> bytes:
    """Build a minimal iCal byte string from a list of event dicts."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for e in events:
        lines += ["BEGIN:VEVENT"]
        lines += [f"{k}:{v}" for k, v in e.items()]
        lines += ["END:VEVENT"]
    lines += ["END:VCALENDAR"]
    return "\r\n".join(lines).encode()


def dt_str(dt: datetime) -> str:
    """Format a datetime as iCal DTSTART/DTEND value with UTC timezone."""
    return dt.strftime("%Y%m%dT%H%M%SZ")


def future(days: int = 1) -> datetime:
    return datetime.now(tz=UTC) + timedelta(days=days)


def past(days: int = 1) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days)


# ---------------------------------------------------------------------------
# CalendarEvent
# ---------------------------------------------------------------------------


class TestCalendarEvent:
    def test_is_all_day_with_date(self):
        event = CalendarEvent(
            summary="All day",
            start=date(2026, 3, 22),
            end=None,
            location=None,
            description=None,
        )
        assert event.is_all_day() is True

    def test_is_not_all_day_with_datetime(self):
        event = CalendarEvent(
            summary="Timed",
            start=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            end=None,
            location=None,
            description=None,
        )
        assert event.is_all_day() is False


# ---------------------------------------------------------------------------
# WebCalReader._normalize_url
# ---------------------------------------------------------------------------


class TestNormalizeUrl:
    def test_webcal_converted_to_https(self):
        reader = WebCalReader("webcal://example.com/cal.ics")
        assert reader.url == "https://example.com/cal.ics"

    def test_webcal_case_insensitive(self):
        reader = WebCalReader("WEBCAL://example.com/cal.ics")
        assert reader.url == "https://example.com/cal.ics"

    def test_https_unchanged(self):
        reader = WebCalReader("https://example.com/cal.ics")
        assert reader.url == "https://example.com/cal.ics"

    def test_http_unchanged(self):
        reader = WebCalReader("http://example.com/cal.ics")
        assert reader.url == "http://example.com/cal.ics"


# ---------------------------------------------------------------------------
# WebCalReader._parse
# ---------------------------------------------------------------------------


class TestParse:
    def test_parses_summary(self):
        raw = make_ical([{"SUMMARY": "Team Standup", "DTSTART": dt_str(future(1))}])
        events = WebCalReader._parse(raw)
        assert events[0].summary == "Team Standup"

    def test_parses_location(self):
        raw = make_ical(
            [{"SUMMARY": "Meeting", "DTSTART": dt_str(future(1)), "LOCATION": "Room 1"}]
        )
        events = WebCalReader._parse(raw)
        assert events[0].location == "Room 1"

    def test_parses_description(self):
        event_data = {
            "SUMMARY": "Event",
            "DTSTART": dt_str(future(1)),
            "DESCRIPTION": "Details here",
        }
        raw = make_ical([event_data])
        events = WebCalReader._parse(raw)
        assert events[0].description == "Details here"

    def test_empty_location_is_none(self):
        raw = make_ical([{"SUMMARY": "Event", "DTSTART": dt_str(future(1))}])
        events = WebCalReader._parse(raw)
        assert events[0].location is None

    def test_empty_description_is_none(self):
        raw = make_ical([{"SUMMARY": "Event", "DTSTART": dt_str(future(1))}])
        events = WebCalReader._parse(raw)
        assert events[0].description is None

    def test_parses_multiple_events(self):
        raw = make_ical(
            [
                {"SUMMARY": "Event A", "DTSTART": dt_str(future(1))},
                {"SUMMARY": "Event B", "DTSTART": dt_str(future(2))},
            ]
        )
        events = WebCalReader._parse(raw)
        assert len(events) == 2

    def test_empty_calendar_returns_empty_list(self):
        raw = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR"
        events = WebCalReader._parse(raw)
        assert events == []


# ---------------------------------------------------------------------------
# WebCalReader.get_events (mocked HTTP)
# ---------------------------------------------------------------------------


class TestGetEvents:
    def _mock_reader(self, ical_bytes: bytes) -> WebCalReader:
        mock_response = MagicMock()
        mock_response.content = ical_bytes
        with patch("bench_boss.calendar.requests.get", return_value=mock_response):
            reader = WebCalReader("https://example.com/cal.ics")
            reader._fetch = lambda: ical_bytes
        return reader

    def test_returns_all_events(self):
        raw = make_ical(
            [
                {"SUMMARY": "Event A", "DTSTART": dt_str(future(1))},
                {"SUMMARY": "Event B", "DTSTART": dt_str(future(2))},
            ]
        )
        reader = self._mock_reader(raw)
        assert len(reader.get_events()) == 2

    def test_fetch_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404")
        with patch("bench_boss.calendar.requests.get", return_value=mock_response):
            reader = WebCalReader("https://example.com/cal.ics")
            with pytest.raises(Exception, match="404"):
                reader.get_events()


# ---------------------------------------------------------------------------
# WebCalReader.get_upcoming
# ---------------------------------------------------------------------------


class TestGetUpcoming:
    def _reader_with_events(self, events: list[dict]) -> WebCalReader:
        raw = make_ical(events)
        reader = WebCalReader("https://example.com/cal.ics")
        reader._fetch = lambda: raw
        return reader

    def test_returns_events_within_window(self):
        reader = self._reader_with_events(
            [
                {"SUMMARY": "Soon", "DTSTART": dt_str(future(2))},
            ]
        )
        assert len(reader.get_upcoming(days=7)) == 1

    def test_excludes_past_events(self):
        reader = self._reader_with_events(
            [
                {"SUMMARY": "Past", "DTSTART": dt_str(past(1))},
            ]
        )
        assert reader.get_upcoming(days=7) == []

    def test_excludes_events_beyond_window(self):
        reader = self._reader_with_events(
            [
                {"SUMMARY": "Far future", "DTSTART": dt_str(future(30))},
            ]
        )
        assert reader.get_upcoming(days=7) == []

    def test_results_sorted_by_start(self):
        reader = self._reader_with_events(
            [
                {"SUMMARY": "Later", "DTSTART": dt_str(future(3))},
                {"SUMMARY": "Sooner", "DTSTART": dt_str(future(1))},
            ]
        )
        events = reader.get_upcoming(days=7)
        assert events[0].summary == "Sooner"
        assert events[1].summary == "Later"

    def test_empty_calendar_returns_empty_list(self):
        reader = self._reader_with_events([])
        assert reader.get_upcoming(days=7) == []

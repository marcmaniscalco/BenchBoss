"""
Reads a webcal/iCal URL and returns a list of calendar events.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import requests
from icalendar import Calendar

logger = logging.getLogger(__name__)

# esportsdesk's webcal feed is intermittently flaky — a 200 with an empty
# body, a connection error, or a 5xx. A short retry clears it up without
# needing to wait for the next trigger (e.g. the next event's TTL
# expiration) to retry.
_FETCH_ATTEMPTS = 3
_FETCH_RETRY_DELAY_SECONDS = 1


@dataclass
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime | None
    location: str | None
    description: str | None

    def is_all_day(self) -> bool:
        return isinstance(self.start, date) and not isinstance(self.start, datetime)


class WebCalReader:
    def __init__(self, url: str):
        self.url = self._normalize_url(url)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_events(self) -> list[CalendarEvent]:
        """Fetch and return all events from the calendar."""
        raw = self._fetch()
        return self._parse(raw)

    def get_upcoming(self, days: int = 7) -> list[CalendarEvent]:
        """Return events starting within the next `days` days, sorted by start time."""
        now = datetime.now(tz=UTC)
        cutoff = self._add_days(now, days)
        events = [e for e in self.get_events() if now <= self._start_dt(e) <= cutoff]

        return sorted(events, key=lambda e: self._start_dt(e))

    def get_remaining(self) -> list[CalendarEvent]:
        """Return all events starting from now onward, sorted by start time."""
        now = datetime.now(tz=UTC)
        events = [e for e in self.get_events() if self._start_dt(e) >= now]
        return sorted(events, key=lambda e: self._start_dt(e))

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Convert webcal:// to https:// so requests can fetch it."""
        return re.sub(r"^webcal://", "https://", url, flags=re.IGNORECASE)

    def _fetch(self) -> bytes:
        logger.debug("Fetching calendar from %s", self.url)
        last_error: Exception
        for attempt in range(1, _FETCH_ATTEMPTS + 1):
            try:
                response = requests.get(self.url, timeout=10)
                response.raise_for_status()
                if response.content:
                    return response.content
                last_error = ValueError(
                    f"Calendar fetch from {self.url} returned an empty body"
                )
            except requests.RequestException as e:
                last_error = e
            logger.warning(
                "Calendar fetch from %s failed (attempt %d/%d): %s",
                self.url,
                attempt,
                _FETCH_ATTEMPTS,
                last_error,
            )
            if attempt < _FETCH_ATTEMPTS:
                time.sleep(_FETCH_RETRY_DELAY_SECONDS)
        raise last_error

    @staticmethod
    def _parse(raw: bytes) -> list[CalendarEvent]:
        cal = Calendar.from_ical(raw)
        events = []
        for component in cal.walk("VEVENT"):
            start = component.decoded("DTSTART", None)
            end = component.decoded("DTEND", None)
            events.append(
                CalendarEvent(
                    summary=str(component.get("SUMMARY", "")),
                    start=start,
                    end=end,
                    location=str(component.get("LOCATION", "")) or None,
                    description=str(component.get("DESCRIPTION", "")) or None,
                )
            )
        logger.debug("Parsed %d events from calendar", len(events))
        return events

    @staticmethod
    def _start_dt(event: CalendarEvent) -> datetime:
        """Return event start as a timezone-aware datetime for comparison."""
        s = event.start
        if isinstance(s, datetime):
            return s if s.tzinfo else s.replace(tzinfo=UTC)
        if isinstance(s, date):
            return datetime(s.year, s.month, s.day, tzinfo=UTC)
        return datetime.min.replace(tzinfo=UTC)

    @staticmethod
    def _add_days(dt: datetime, days: int) -> datetime:
        return dt + timedelta(days=days)

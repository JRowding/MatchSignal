"""Explicit UTC storage; date-only results are never treated as timed fixtures."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utc_now():
    return datetime.now(timezone.utc)


def instant(value, naive_zone="UTC"):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(naive_zone))
    return parsed.astimezone(timezone.utc)


def utc_text(value, naive_zone="UTC"):
    return instant(value, naive_zone).isoformat(timespec="seconds")


def football_day(value):
    if len(value) == 10:
        return value
    return instant(value).astimezone(ZoneInfo("Europe/London")).date().isoformat()

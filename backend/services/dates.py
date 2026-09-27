"""
Date parsing shared by every news source.

Handles RFC-822 dates with US zone abbreviations (EST/PDT…), ISO strings,
SerpAPI's "04/05/2026, 07:00 AM, +0000 UTC" format and relative strings
such as "3 hours ago" or "2 days ago". Always returns an aware UTC datetime
or None — never guesses "now" for an unknown date.
"""
import re
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as dtparser

TZINFOS = {
    "EST": timezone(timedelta(hours=-5)), "EDT": timezone(timedelta(hours=-4)),
    "CST": timezone(timedelta(hours=-6)), "CDT": timezone(timedelta(hours=-5)),
    "MST": timezone(timedelta(hours=-7)), "MDT": timezone(timedelta(hours=-6)),
    "PST": timezone(timedelta(hours=-8)), "PDT": timezone(timedelta(hours=-7)),
    "BST": timezone(timedelta(hours=1)),  "IST": timezone(timedelta(hours=5, minutes=30)),
    "CET": timezone(timedelta(hours=1)),  "CEST": timezone(timedelta(hours=2)),
    "GMT": timezone.utc, "UTC": timezone.utc, "Z": timezone.utc,
}

_UNIT_SECONDS = {
    "second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600,
    "day": 86400, "week": 604800, "month": 2592000, "year": 31536000,
}
_RELATIVE = re.compile(
    r"^\s*(an?|\d+)\s*(second|sec|minute|min|hour|hr|day|week|month|year)s?\s+ago\s*$", re.I
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value, now: Optional[datetime] = None) -> Optional[datetime]:
    if value is None or value == "":
        return None
    now = now or utcnow()

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        low = text.lower()
        if low in {"just now", "now"}:
            return now
        if low == "yesterday":
            return now - timedelta(days=1)

        m = _RELATIVE.match(text)
        if m:
            amount = 1 if m.group(1).lower() in {"a", "an"} else int(m.group(1))
            return now - timedelta(seconds=amount * _UNIT_SECONDS[m.group(2).lower()])

        # SerpAPI: "04/05/2026, 07:00 AM, +0000 UTC"
        text = re.sub(r",\s*([+-]\d{4})\s*UTC$", r" \1", text)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dt = dtparser.parse(text, tzinfos=TZINFOS)
        except (ValueError, OverflowError, TypeError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    # Feeds occasionally publish slightly-future timestamps; never show "in 3 hours"
    return min(dt, now)


def is_fresh(dt: Optional[datetime], hours: int, now: Optional[datetime] = None) -> bool:
    """Unknown dates count as fresh — callers decide how to rank them."""
    if dt is None:
        return True
    return dt >= (now or utcnow()) - timedelta(hours=hours)

"""
Economic calendar from Forex Factory's official public weekly feed
(nfs.faireconomy.media — the export Forex Factory publishes for its calendar).

The feed is updated roughly hourly and asks consumers not to poll it heavily, so it
is fetched at most once per CACHE_TTL for all visitors, and the last good copy is
served if a fetch fails. Events carry: title, currency, time, impact, forecast, previous.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from dateutil import parser as dtparser

from services.dates import utcnow
from services.news_service import HTTP_HEADERS

log = logging.getLogger(__name__)

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE_URL = "https://www.forexfactory.com/calendar"
CACHE_TTL = 60 * 60
RETRY_AFTER_FAILURE = 10 * 60
IMPACT_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Holiday": 3}

_cache: Dict[str, Any] = {"events": None, "fetched_at": None, "expires": 0.0}
_lock = asyncio.Lock()


def _event_time(value: Optional[str]) -> Optional[datetime]:
    """Feed times are ISO with an offset (e.g. 2026-09-29T00:30:00-04:00). Unlike
    dates.parse_date this must not clamp to "now" — calendar events are in the future."""
    if not value:
        return None
    try:
        dt = dtparser.isoparse(value)
    except (ValueError, TypeError):
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def normalize(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clean feed rows into UTC-timestamped events, sorted by time then impact."""
    events = []
    for e in raw:
        when = _event_time(e.get("date"))
        impact = e.get("impact") or "Low"
        events.append({
            "title":    (e.get("title") or "").strip(),
            "currency": (e.get("country") or "").strip().upper(),
            "time":     when.isoformat() if when else None,
            "impact":   impact if impact in IMPACT_ORDER else "Low",
            "forecast": (e.get("forecast") or "").strip() or None,
            "previous": (e.get("previous") or "").strip() or None,
        })
    events.sort(key=lambda x: (x["time"] or "", IMPACT_ORDER[x["impact"]]))
    return [e for e in events if e["title"]]


async def get_week() -> Dict[str, Any]:
    """This week's events (cached). Raises only if nothing has ever been fetched."""
    if _cache["events"] is not None and time.monotonic() < _cache["expires"]:
        return _snapshot(stale=False)

    async with _lock:
        if _cache["events"] is not None and time.monotonic() < _cache["expires"]:
            return _snapshot(stale=False)
        try:
            async with httpx.AsyncClient(timeout=15, headers=HTTP_HEADERS, follow_redirects=True) as client:
                resp = await client.get(FEED_URL)
            resp.raise_for_status()
            _cache.update(events=normalize(resp.json()), fetched_at=utcnow().isoformat(),
                          expires=time.monotonic() + CACHE_TTL)
            return _snapshot(stale=False)
        except Exception as e:
            log.warning("Economic calendar fetch failed: %s", type(e).__name__)
            _cache["expires"] = time.monotonic() + RETRY_AFTER_FAILURE
            if _cache["events"] is None:
                raise
            return _snapshot(stale=True)


def _snapshot(stale: bool) -> Dict[str, Any]:
    return {"events": _cache["events"], "fetched_at": _cache["fetched_at"], "stale": stale,
            "source": "Forex Factory", "source_url": SOURCE_URL}


def filter_events(events: List[Dict[str, Any]], impacts: Optional[set] = None) -> List[Dict[str, Any]]:
    return [e for e in events if not impacts or e["impact"] in impacts]

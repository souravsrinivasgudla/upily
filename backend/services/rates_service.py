"""
Currency reference rates from the European Central Bank, via Frankfurter (api.frankfurter.app).

These are the ECB's official daily reference rates (published around 16:00 CET on
working days), not intraday prices — the UI labels them as such. Truly live FX quotes
need a paid data feed. Cached for CACHE_TTL; the last good copy is served on failure.
"""
import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List

import httpx

from services.dates import utcnow
from services.news_service import HTTP_HEADERS

log = logging.getLogger(__name__)

API = "https://api.frankfurter.app"
CACHE_TTL = 30 * 60
RETRY_AFTER_FAILURE = 5 * 60

# Pairs as traders quote them. "inverse" pairs are quoted against USD (EUR/USD = 1 / USD→EUR).
PAIRS = [
    ("EUR/USD", "EUR", True), ("GBP/USD", "GBP", True), ("USD/JPY", "JPY", False),
    ("USD/INR", "INR", False), ("AUD/USD", "AUD", True), ("USD/CAD", "CAD", False),
    ("USD/CHF", "CHF", False), ("USD/CNY", "CNY", False),
]

_cache: Dict[str, Any] = {"data": None, "expires": 0.0}
_lock = asyncio.Lock()


def build_pairs(series: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    """From a USD-based daily time series, the latest quote and change vs the previous day."""
    days = sorted(series)
    if not days:
        raise ValueError("empty rate series")
    latest, prev = series[days[-1]], series[days[-2]] if len(days) > 1 else None
    pairs: List[Dict[str, Any]] = []
    for label, code, inverse in PAIRS:
        if code not in latest:
            continue
        value = 1 / latest[code] if inverse else latest[code]
        change = None
        if prev and code in prev:
            before = 1 / prev[code] if inverse else prev[code]
            change = (value - before) / before * 100
        decimals = 2 if value >= 20 else 4
        pairs.append({"pair": label, "rate": round(value, decimals),
                      "change_pct": round(change, 3) if change is not None else None})
    return {"as_of": days[-1], "previous": days[-2] if len(days) > 1 else None, "pairs": pairs,
            "source": "European Central Bank reference rates (via Frankfurter)",
            "source_url": "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html"}


async def get_rates() -> Dict[str, Any]:
    if _cache["data"] and time.monotonic() < _cache["expires"]:
        return {**_cache["data"], "stale": False}
    async with _lock:
        if _cache["data"] and time.monotonic() < _cache["expires"]:
            return {**_cache["data"], "stale": False}
        start = (utcnow() - timedelta(days=10)).date().isoformat()   # covers weekends + holidays
        symbols = ",".join(code for _, code, _ in PAIRS)
        try:
            async with httpx.AsyncClient(timeout=15, headers=HTTP_HEADERS, follow_redirects=True) as client:
                resp = await client.get(f"{API}/{start}..", params={"from": "USD", "to": symbols})
            resp.raise_for_status()
            data = build_pairs(resp.json().get("rates") or {})
            _cache.update(data=data, expires=time.monotonic() + CACHE_TTL)
            return {**data, "stale": False}
        except Exception as e:
            log.warning("Currency rates fetch failed: %s", type(e).__name__)
            _cache["expires"] = time.monotonic() + RETRY_AFTER_FAILURE
            if not _cache["data"]:
                raise
            return {**_cache["data"], "stale": True}

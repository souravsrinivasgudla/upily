"""
Currency rates for the Forex desk.

  Live:      Coinbase's public exchange-rates API (no key) — indicative mid-market
             rates that update through the trading day. Cached for LIVE_TTL, shared
             by all readers.
  Baseline:  the European Central Bank's latest daily reference rate (via Frankfurter),
             used for the "change" figure — i.e. the move since the last ECB fix.
  Fallback:  if the live source fails, the ECB reference rates alone, flagged live=False
             so the UI says so.

Indicative rates are fine for a news site; they are not dealer quotes you can trade on.
"""
import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

import httpx

from services.dates import utcnow
from services.news_service import HTTP_HEADERS

log = logging.getLogger(__name__)

LIVE_URL = "https://api.coinbase.com/v2/exchange-rates"
ECB_API = "https://api.frankfurter.app"
ECB_SOURCE_URL = ("https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
                  "euro_reference_exchange_rates/html/index.en.html")
LIVE_TTL = 30                 # seconds
ECB_TTL = 6 * 60 * 60         # the ECB publishes once per working day
RETRY_AFTER_FAILURE = 60

# Pairs as traders quote them. "inverse" pairs are quoted against USD (EUR/USD = 1 / USD→EUR).
PAIRS = [
    ("EUR/USD", "EUR", True), ("GBP/USD", "GBP", True), ("USD/JPY", "JPY", False),
    ("USD/INR", "INR", False), ("AUD/USD", "AUD", True), ("USD/CAD", "CAD", False),
    ("USD/CHF", "CHF", False), ("USD/CNY", "CNY", False),
]
CODES = [code for _, code, _ in PAIRS]

_live: Dict[str, Any] = {"rates": None, "at": None, "expires": 0.0}
_ecb: Dict[str, Any] = {"series": None, "expires": 0.0}
_live_lock, _ecb_lock = asyncio.Lock(), asyncio.Lock()


def _quote(usd_rates: Dict[str, float], code: str, inverse: bool) -> Optional[float]:
    v = usd_rates.get(code)
    if not v:
        return None
    return 1 / v if inverse else v


def _round(value: float) -> float:
    return round(value, 2 if value >= 20 else 4)


def build_pairs(current: Dict[str, float], baseline: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
    """Quote each pair from USD-based rates; change_pct is measured against `baseline`."""
    pairs = []
    for label, code, inverse in PAIRS:
        value = _quote(current, code, inverse)
        if value is None:
            continue
        before = _quote(baseline, code, inverse) if baseline else None
        change = (value - before) / before * 100 if before else None
        pairs.append({"pair": label, "rate": _round(value),
                      "change_pct": round(change, 3) if change is not None else None})
    return pairs


async def _ecb_series() -> Dict[str, Dict[str, float]]:
    """Recent ECB reference rates (USD-based), newest last. Cached; raises if never fetched."""
    if _ecb["series"] and time.monotonic() < _ecb["expires"]:
        return _ecb["series"]
    async with _ecb_lock:
        if _ecb["series"] and time.monotonic() < _ecb["expires"]:
            return _ecb["series"]
        start = (utcnow() - timedelta(days=10)).date().isoformat()   # covers weekends + holidays
        try:
            async with httpx.AsyncClient(timeout=15, headers=HTTP_HEADERS, follow_redirects=True) as client:
                resp = await client.get(f"{ECB_API}/{start}..", params={"from": "USD", "to": ",".join(CODES)})
            resp.raise_for_status()
            series = resp.json().get("rates") or {}
            if not series:
                raise ValueError("empty ECB series")
            _ecb.update(series=series, expires=time.monotonic() + ECB_TTL)
        except Exception as e:
            log.warning("ECB reference rates fetch failed: %s", type(e).__name__)
            _ecb["expires"] = time.monotonic() + RETRY_AFTER_FAILURE
            if not _ecb["series"]:
                raise
        return _ecb["series"]


async def _live_rates() -> tuple[Dict[str, float], str]:
    if _live["rates"] and time.monotonic() < _live["expires"]:
        return _live["rates"], _live["at"]
    async with _live_lock:
        if _live["rates"] and time.monotonic() < _live["expires"]:
            return _live["rates"], _live["at"]
        async with httpx.AsyncClient(timeout=8, headers=HTTP_HEADERS) as client:
            resp = await client.get(LIVE_URL, params={"currency": "USD"})
        resp.raise_for_status()
        raw = (resp.json().get("data") or {}).get("rates") or {}
        rates = {c: float(raw[c]) for c in CODES if c in raw}
        if len(rates) < len(CODES) // 2:
            raise ValueError("live source returned too few rates")
        _live.update(rates=rates, at=utcnow().isoformat(), expires=time.monotonic() + LIVE_TTL)
        return rates, _live["at"]


async def get_rates() -> Dict[str, Any]:
    series: Dict[str, Dict[str, float]] = {}
    try:
        series = await _ecb_series()
    except Exception:
        pass
    days = sorted(series)

    try:
        current, at = await _live_rates()
        baseline_day = days[-1] if days else None
        return {
            "live": True,
            "as_of": at,
            "pairs": build_pairs(current, series.get(baseline_day) if baseline_day else None),
            "change_basis": f"since the ECB reference rate of {baseline_day}" if baseline_day else None,
            "baseline_date": baseline_day,
            "source": "Coinbase exchange rates (indicative, mid-market)",
            "source_url": "https://www.coinbase.com/converter",
            "refresh_seconds": LIVE_TTL,
        }
    except Exception as e:
        log.warning("Live currency rates unavailable (%s); falling back to ECB reference", type(e).__name__)

    if not days:
        raise RuntimeError("no currency data available")
    return {
        "live": False,
        "as_of": days[-1],
        "pairs": build_pairs(series[days[-1]], series[days[-2]] if len(days) > 1 else None),
        "change_basis": "vs the previous ECB reference rate",
        "baseline_date": days[-2] if len(days) > 1 else None,
        "source": "European Central Bank reference rates (via Frankfurter)",
        "source_url": ECB_SOURCE_URL,
        "refresh_seconds": LIVE_TTL,
    }

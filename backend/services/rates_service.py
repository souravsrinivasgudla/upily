"""
Currency rates for the Forex desk — three sources, each used for what it's good at.

  Twelve Data (TWELVE_DATA_API_KEY)   real market quotes: previous daily close, day
      high/low, market open/closed. The free Basic plan allows 8 credits/minute and
      800/day, and every pair costs a credit, so all 8 pairs are refreshed every
      TD_TTL (15 min ≈ 770 credits/day) with a daily cap as a safety net.
  Coinbase public exchange rates      indicative mid-market prices that move through
      the day; no key. Refreshed every LIVE_TTL (30 s) for the ticking price.
  European Central Bank (Frankfurter) official daily reference rates; the baseline
      for the day change when Twelve Data isn't configured or is unavailable.

Price shown:   Coinbase (live) → else Twelve Data close (≤15 min old) → else ECB.
Day change:    vs Twelve Data previous close → else vs the last ECB reference rate.
"""
import asyncio
import logging
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

import httpx

from config import settings
from services.dates import utcnow
from services.news_service import HTTP_HEADERS

log = logging.getLogger(__name__)

LIVE_URL = "https://api.coinbase.com/v2/exchange-rates"
TD_URL = "https://api.twelvedata.com/quote"
ECB_API = "https://api.frankfurter.app"
ECB_SOURCE_URL = ("https://www.ecb.europa.eu/stats/policy_and_exchange_rates/"
                  "euro_reference_exchange_rates/html/index.en.html")

LIVE_TTL = 30                 # seconds
TD_TTL = 15 * 60              # 8 pairs x 96 refreshes/day = 768 of 800 free credits
TD_DAILY_CREDIT_CAP = 780
ECB_TTL = 6 * 60 * 60         # the ECB publishes once per working day
RETRY_AFTER_FAILURE = 60

# Pairs as traders quote them. "inverse" pairs are quoted against USD (EUR/USD = 1 / USD→EUR).
PAIRS = [
    ("EUR/USD", "EUR", True), ("GBP/USD", "GBP", True), ("USD/JPY", "JPY", False),
    ("USD/INR", "INR", False), ("AUD/USD", "AUD", True), ("USD/CAD", "CAD", False),
    ("USD/CHF", "CHF", False), ("USD/CNY", "CNY", False),
]
CODES = [code for _, code, _ in PAIRS]

_live: Dict[str, Any] = {"prices": None, "at": None, "expires": 0.0}
_td: Dict[str, Any] = {"quotes": None, "at": None, "expires": 0.0}
_td_credits: Dict[str, Any] = {"day": None, "used": 0}
_ecb: Dict[str, Any] = {"series": None, "expires": 0.0}
_live_lock, _td_lock, _ecb_lock = asyncio.Lock(), asyncio.Lock(), asyncio.Lock()


def usd_to_pairs(usd_rates: Dict[str, float]) -> Dict[str, float]:
    """USD-based rates (USD→XXX) → prices keyed by pair label."""
    out = {}
    for label, code, inverse in PAIRS:
        v = usd_rates.get(code)
        if v:
            out[label] = 1 / v if inverse else v
    return out


def _round(value: float) -> float:
    return round(value, 2 if value >= 20 else 4)


def build_pairs(prices: Dict[str, float], baseline: Optional[Dict[str, float]],
                extra: Optional[Dict[str, Dict[str, float]]] = None) -> List[Dict[str, Any]]:
    """One row per pair: price, change vs baseline, and day high/low when known."""
    rows = []
    for label, _, _ in PAIRS:
        price = prices.get(label)
        if price is None:
            continue
        before = (baseline or {}).get(label)
        change = (price - before) / before * 100 if before else None
        e = (extra or {}).get(label, {})
        rows.append({
            "pair": label,
            "rate": _round(price),
            "change_pct": round(change, 3) if change is not None else None,
            "high": _round(e["high"]) if e.get("high") else None,
            "low": _round(e["low"]) if e.get("low") else None,
        })
    return rows


# ── Sources ───────────────────────────────────────────────────────────────────

async def _live_prices() -> tuple[Dict[str, float], str]:
    if _live["prices"] and time.monotonic() < _live["expires"]:
        return _live["prices"], _live["at"]
    async with _live_lock:
        if _live["prices"] and time.monotonic() < _live["expires"]:
            return _live["prices"], _live["at"]
        async with httpx.AsyncClient(timeout=8, headers=HTTP_HEADERS) as client:
            resp = await client.get(LIVE_URL, params={"currency": "USD"})
        resp.raise_for_status()
        raw = (resp.json().get("data") or {}).get("rates") or {}
        prices = usd_to_pairs({c: float(raw[c]) for c in CODES if c in raw})
        if len(prices) < len(PAIRS) // 2:
            raise ValueError("live source returned too few rates")
        _live.update(prices=prices, at=utcnow().isoformat(), expires=time.monotonic() + LIVE_TTL)
        return prices, _live["at"]


def _spend_td_credits(n: int) -> bool:
    today = utcnow().date()
    if _td_credits["day"] != today:
        _td_credits.update(day=today, used=0)
    if _td_credits["used"] + n > TD_DAILY_CREDIT_CAP:
        return False
    _td_credits["used"] += n
    return True


def parse_td_quotes(body: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Twelve Data /quote for several symbols → {pair: {close, previous_close, high, low, open}}."""
    if body.get("status") == "error" or "code" in body:
        raise ValueError(f"Twelve Data error {body.get('code')}: {str(body.get('message'))[:120]}")
    quotes = {}
    for label, _, _ in PAIRS:
        q = body.get(label)
        if not isinstance(q, dict) or q.get("status") == "error":
            continue
        try:
            quotes[label] = {
                "close": float(q["close"]),
                "previous_close": float(q["previous_close"]),
                "high": float(q["high"]) if q.get("high") else None,
                "low": float(q["low"]) if q.get("low") else None,
                "is_market_open": bool(q.get("is_market_open")),
            }
        except (KeyError, TypeError, ValueError):
            continue
    if not quotes:
        raise ValueError("Twelve Data returned no usable quotes")
    return quotes


async def _td_quotes() -> Optional[Dict[str, Dict[str, Any]]]:
    """Cached Twelve Data quotes, or None when not configured / over budget / failing."""
    if not settings.TWELVE_DATA_API_KEY:
        return None
    if _td["quotes"] and time.monotonic() < _td["expires"]:
        return _td["quotes"]
    async with _td_lock:
        if _td["quotes"] and time.monotonic() < _td["expires"]:
            return _td["quotes"]
        if time.monotonic() < _td["expires"]:          # recent failure: don't hammer
            return _td["quotes"]
        if not _spend_td_credits(len(PAIRS)):
            log.warning("Twelve Data daily credit cap reached; using last quotes")
            _td["expires"] = time.monotonic() + TD_TTL
            return _td["quotes"]
        try:
            async with httpx.AsyncClient(timeout=12, headers=HTTP_HEADERS) as client:
                resp = await client.get(TD_URL, params={
                    "symbol": ",".join(label for label, _, _ in PAIRS),
                    "apikey": settings.TWELVE_DATA_API_KEY,
                })
            quotes = parse_td_quotes(resp.json())
            _td.update(quotes=quotes, at=utcnow().isoformat(), expires=time.monotonic() + TD_TTL)
        except Exception as e:
            # Log the type/message only — never the request URL (it carries the key)
            log.warning("Twelve Data quotes unavailable: %s", str(e)[:160] or type(e).__name__)
            _td["expires"] = time.monotonic() + RETRY_AFTER_FAILURE * 5
        return _td["quotes"]


async def _ecb_series() -> Dict[str, Dict[str, float]]:
    """Recent ECB reference rates (USD-based), keyed by date. Cached; raises if never fetched."""
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


# ── Combined view ─────────────────────────────────────────────────────────────

async def get_rates() -> Dict[str, Any]:
    live_prices, live_at = None, None
    try:
        live_prices, live_at = await _live_prices()
    except Exception as e:
        log.warning("Live currency prices unavailable: %s", type(e).__name__)

    td = await _td_quotes()

    ecb, ecb_days = {}, []
    if not td or not live_prices:
        try:
            ecb = await _ecb_series()
            ecb_days = sorted(ecb)
        except Exception:
            pass

    # Price
    if live_prices:
        prices, as_of, price_source, live = live_prices, live_at, "Coinbase (indicative, mid-market)", True
    elif td:
        prices = {p: q["close"] for p, q in td.items()}
        as_of, price_source, live = _td["at"], "Twelve Data (delayed up to 15 min)", False
    elif ecb_days:
        prices = usd_to_pairs(ecb[ecb_days[-1]])
        as_of, price_source, live = ecb_days[-1], "European Central Bank reference rates", False
    else:
        raise RuntimeError("no currency data available")

    # Baseline for the change figure
    if td:
        baseline = {p: q["previous_close"] for p, q in td.items()}
        change_basis, baseline_date = "vs the previous daily close", None
        extra = {p: {"high": q["high"], "low": q["low"]} for p, q in td.items()}
        market_open = any(q["is_market_open"] for q in td.values())
    else:
        use_day = ecb_days[-1] if live and ecb_days else (ecb_days[-2] if len(ecb_days) > 1 else None)
        baseline = usd_to_pairs(ecb[use_day]) if use_day else None
        change_basis = f"since the ECB reference rate of {use_day}" if use_day else None
        baseline_date, extra, market_open = use_day, None, None

    return {
        "live": live,
        "market_open": market_open,
        "as_of": as_of,
        "pairs": build_pairs(prices, baseline, extra),
        "change_basis": change_basis,
        "baseline_date": baseline_date,
        "price_source": price_source,
        "quotes_source": "Twelve Data" if td else "European Central Bank",
        "quotes_as_of": _td["at"] if td else None,
        "refresh_seconds": LIVE_TTL,
        "source_url": "https://twelvedata.com/" if td else ECB_SOURCE_URL,
    }

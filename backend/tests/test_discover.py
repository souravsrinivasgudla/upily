from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import agents.orchestrator as orchestrator
from api import deps
from api.routes import discover
from main import app
from services import calendar_service, rates_service


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset():
    for limiter in (deps.refresh_limit, deps.trending_limit, discover.search_limit):
        limiter._hits.clear()
    orchestrator._last_refresh.clear()


def _story(n, category, title, source):
    return {"title": title, "url": f"https://example.com/{category}/{n}", "source": source,
            "published_at": datetime.now(timezone.utc), "category": category,
            "content": title, "summary": title}


def test_search_finds_stories_and_validates_query(client, monkeypatch):
    async def fetch(self, category):
        return [_story(1, category, "Central bank raises interest rates to fight inflation", "CNBC"),
                _story(2, category, "Streaming service announces price increase", "Variety")]
    monkeypatch.setattr(orchestrator.OrchestratorAgent, "_fetch", fetch)
    client.post("/api/news/refresh/business")

    body = client.get("/api/search", params={"q": "interest rates"}).json()
    assert body["results"][0]["title"].startswith("Central bank raises")
    assert all("score" in r for r in body["results"])
    assert client.get("/api/search", params={"q": "x"}).status_code == 422       # too short
    assert client.get("/api/search", params={"q": "klingon treaty"}).json()["results"] == []


def test_briefing_has_one_top_story_per_section(client, monkeypatch):
    async def no_calendar():
        raise RuntimeError("offline")
    monkeypatch.setattr(calendar_service, "get_week", no_calendar)   # briefing must still work

    body = client.get("/api/briefing").json()
    sections = [i["section"] for i in body["items"]]
    assert "business" in sections and len(sections) == len(set(sections))
    assert body["editors_note"] is None          # no LLM configured in tests
    assert body["market_events"] == [] and body["reading_minutes"] >= 1


def test_rate_pairs_are_quoted_the_trader_way():
    prices = rates_service.usd_to_pairs({"EUR": 0.8000 * 1.01, "INR": 96.00})
    baseline = rates_service.usd_to_pairs({"EUR": 0.8000, "INR": 95.00})
    pairs = {p["pair"]: p for p in rates_service.build_pairs(prices, baseline)}
    assert pairs["EUR/USD"]["rate"] == pytest.approx(1 / 0.808, abs=1e-4)   # inverted
    assert pairs["EUR/USD"]["change_pct"] == pytest.approx(-0.990, abs=1e-3)
    assert pairs["USD/INR"]["rate"] == 96.0 and pairs["USD/INR"]["change_pct"] == pytest.approx(1.053, abs=1e-3)
    assert rates_service.build_pairs(prices, None)[0]["change_pct"] is None


def test_twelve_data_quotes_parse_and_errors():
    body = {"EUR/USD": {"close": "1.1377", "previous_close": "1.13832", "high": "1.139", "low": "1.1370",
                        "is_market_open": True},
            "USD/INR": {"status": "error", "message": "symbol not found"}}
    q = rates_service.parse_td_quotes(body)
    assert list(q) == ["EUR/USD"] and q["EUR/USD"]["previous_close"] == 1.13832
    with pytest.raises(ValueError):
        rates_service.parse_td_quotes({"code": 429, "message": "run out of API credits", "status": "error"})


def test_rates_combine_sources_and_fall_back(monkeypatch):
    import asyncio

    async def live_ok():
        return rates_service.usd_to_pairs({"EUR": 0.80, "INR": 97.0}), "2026-09-28T06:00:00+00:00"

    async def live_down():
        raise RuntimeError("coinbase down")

    async def td_quotes():
        return {"EUR/USD": {"close": 1.24, "previous_close": 1.25, "high": 1.26, "low": 1.23, "is_market_open": True},
                "USD/INR": {"close": 96.9, "previous_close": 96.0, "high": 97.1, "low": 95.9, "is_market_open": True}}

    async def td_none():
        return None

    async def ecb():
        return {"2026-09-24": {"EUR": 0.80, "INR": 95.0}, "2026-09-25": {"EUR": 0.81, "INR": 96.0}}

    monkeypatch.setattr(rates_service, "_ecb_series", ecb)

    # Live price + Twelve Data previous close / high / low
    monkeypatch.setattr(rates_service, "_live_prices", live_ok)
    monkeypatch.setattr(rates_service, "_td_quotes", td_quotes)
    d = asyncio.run(rates_service.get_rates())
    inr = {p["pair"]: p for p in d["pairs"]}["USD/INR"]
    assert d["live"] and d["market_open"] and d["quotes_source"] == "Twelve Data"
    assert inr["rate"] == 97.0 and inr["change_pct"] == pytest.approx(1.042, abs=1e-3) and inr["high"] == 97.1

    # Live source down → Twelve Data close, not labelled live
    monkeypatch.setattr(rates_service, "_live_prices", live_down)
    d = asyncio.run(rates_service.get_rates())
    assert not d["live"] and {p["pair"]: p for p in d["pairs"]}["USD/INR"]["rate"] == 96.9

    # No Twelve Data → live price vs last ECB fix
    monkeypatch.setattr(rates_service, "_live_prices", live_ok)
    monkeypatch.setattr(rates_service, "_td_quotes", td_none)
    d = asyncio.run(rates_service.get_rates())
    assert d["live"] and d["market_open"] is None and d["baseline_date"] == "2026-09-25"


def test_twelve_data_credit_cap():
    rates_service._td_credits.update(day=None, used=0)
    spent = sum(rates_service._spend_td_credits(8) for _ in range(200))
    assert spent * 8 <= rates_service.TD_DAILY_CREDIT_CAP and spent == 97


def test_rates_endpoint_reports_outage(client, monkeypatch):
    async def down():
        raise RuntimeError("offline")
    monkeypatch.setattr(rates_service, "get_rates", down)
    assert client.get("/api/rates").status_code == 503

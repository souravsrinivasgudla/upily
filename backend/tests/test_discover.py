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
    pairs = {p["pair"]: p for p in rates_service.build_pairs(
        {"EUR": 0.8000 * 1.01, "INR": 96.00},          # now
        {"EUR": 0.8000, "INR": 95.00},                 # baseline (last ECB fix)
    )}
    assert pairs["EUR/USD"]["rate"] == pytest.approx(1 / 0.808, abs=1e-4)   # inverted
    assert pairs["EUR/USD"]["change_pct"] == pytest.approx(-0.990, abs=1e-3)
    assert pairs["USD/INR"]["rate"] == 96.0 and pairs["USD/INR"]["change_pct"] == pytest.approx(1.053, abs=1e-3)
    assert rates_service.build_pairs({"EUR": 0.8}, None)[0]["change_pct"] is None


def test_rates_fall_back_to_ecb_when_live_source_fails(monkeypatch):
    import asyncio

    async def ecb():
        return {"2026-09-24": {"EUR": 0.80, "INR": 95.0}, "2026-09-25": {"EUR": 0.81, "INR": 96.0}}

    async def live_down():
        raise RuntimeError("coinbase down")

    async def live_ok():
        return {"EUR": 0.82, "INR": 97.0}, "2026-09-28T06:00:00+00:00"

    monkeypatch.setattr(rates_service, "_ecb_series", ecb)
    monkeypatch.setattr(rates_service, "_live_rates", live_ok)
    live = asyncio.run(rates_service.get_rates())
    assert live["live"] is True and live["baseline_date"] == "2026-09-25"
    assert {p["pair"]: p for p in live["pairs"]}["USD/INR"]["rate"] == 97.0

    monkeypatch.setattr(rates_service, "_live_rates", live_down)
    fallback = asyncio.run(rates_service.get_rates())
    assert fallback["live"] is False and fallback["as_of"] == "2026-09-25"
    assert {p["pair"]: p for p in fallback["pairs"]}["USD/INR"]["rate"] == 96.0


def test_rates_endpoint_reports_outage(client, monkeypatch):
    async def down():
        raise RuntimeError("offline")
    monkeypatch.setattr(rates_service, "get_rates", down)
    assert client.get("/api/rates").status_code == 503

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
    data = rates_service.build_pairs({
        "2026-09-24": {"EUR": 0.8000, "INR": 95.00},
        "2026-09-25": {"EUR": 0.8000 * 1.01, "INR": 96.00},
    })
    pairs = {p["pair"]: p for p in data["pairs"]}
    assert pairs["EUR/USD"]["rate"] == pytest.approx(1 / 0.808, abs=1e-4)   # inverted
    assert pairs["EUR/USD"]["change_pct"] == pytest.approx(-0.990, abs=1e-3)
    assert pairs["USD/INR"]["rate"] == 96.0 and pairs["USD/INR"]["change_pct"] == pytest.approx(1.053, abs=1e-3)
    assert data["as_of"] == "2026-09-25" and data["previous"] == "2026-09-24"


def test_rates_endpoint_reports_outage(client, monkeypatch):
    async def down():
        raise RuntimeError("offline")
    monkeypatch.setattr(rates_service, "get_rates", down)
    assert client.get("/api/rates").status_code == 503

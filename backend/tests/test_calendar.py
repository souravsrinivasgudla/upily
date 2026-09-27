from datetime import datetime, timezone

from services import calendar_service
from services.news_service import belongs_elsewhere

SAMPLE = [
    {"title": "CPI y/y", "country": "AUD", "date": "2026-09-29T21:30:00-04:00", "impact": "High",
     "forecast": "4.1%", "previous": "3.5%"},
    {"title": "Bank Holiday", "country": "cny", "date": "2026-09-29T00:00:00-04:00", "impact": "Holiday",
     "forecast": "", "previous": ""},
    {"title": "", "country": "USD", "date": "2026-09-30T08:30:00-04:00", "impact": "Low"},
]


def test_normalize_converts_to_utc_and_keeps_future_times():
    events = calendar_service.normalize(SAMPLE)
    assert [e["title"] for e in events] == ["Bank Holiday", "CPI y/y"]   # sorted by time; blank titles dropped
    cpi = events[1]
    assert cpi["time"] == datetime(2026, 9, 30, 1, 30, tzinfo=timezone.utc).isoformat()
    assert cpi["forecast"] == "4.1%" and cpi["currency"] == "AUD"
    assert events[0]["forecast"] is None and events[0]["currency"] == "CNY"


def test_filter_by_impact():
    events = calendar_service.normalize(SAMPLE)
    assert [e["title"] for e in calendar_service.filter_events(events, {"High"})] == ["CPI y/y"]


def test_forex_story_stays_in_business_and_forex():
    story = {"title": "Dollar slips as Fed rate cut bets grow; EUR/USD climbs", "content": ""}
    assert not belongs_elsewhere(story, "forex")
    assert not belongs_elsewhere(story, "business")   # forex never pulls stories out of business


def test_calendar_endpoint_filters_and_survives_outage(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    async def fake_week():
        return {"events": calendar_service.normalize(SAMPLE), "fetched_at": None, "stale": False,
                "source": "Forex Factory", "source_url": calendar_service.SOURCE_URL}

    monkeypatch.setattr(calendar_service, "get_week", fake_week)
    with TestClient(app) as client:
        body = client.get("/api/calendar", params={"impact": "high"}).json()
        assert [e["title"] for e in body["events"]] == ["CPI y/y"]
        assert body["source"] == "Forex Factory"

        async def down():
            raise RuntimeError("feed down")
        monkeypatch.setattr(calendar_service, "get_week", down)
        assert client.get("/api/calendar").status_code == 503

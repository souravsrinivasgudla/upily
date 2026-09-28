from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.routes import local as local_route
from main import app
from services import local_news, locations


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset():
    local_route.local_limit._hits.clear()
    local_news._cache.clear()


# ── Location data ─────────────────────────────────────────────────────────────

def test_india_states_and_districts():
    assert len(locations.states("IN")) == 36
    assert len(locations.districts("IN", "Andhra Pradesh")) == 26
    assert "Nalgonda" in locations.districts("IN", "Telangana")
    assert sum(len(locations.districts("IN", s)) for s in locations.states("IN")) == 780


def test_validation():
    assert locations.validate("IN", "Telangana", "Nalgonda") is None
    assert locations.validate("IN", "Telangana", None) is None
    assert "not a district of Telangana" in locations.validate("IN", "Telangana", "Guntur")
    assert "India only" in locations.validate("US", "Texas", None)
    assert locations.validate("IN", None, None) == "Choose a state or union territory"


# ── Matching and filtering ────────────────────────────────────────────────────

def _a(title, content=""):
    return {"title": title, "content": content}


def test_district_mentions_use_aliases_and_word_boundaries():
    terms = local_news.mention_terms("Visakhapatnam")
    assert local_news.mentions(_a("Vizag port handles record cargo"), terms)
    assert not local_news.mentions(_a("Vizagapatam-style drama unfolds"), terms)
    # Short names need "district", so "Mon" doesn't match "Monday"
    assert local_news.mention_terms("Mon") == ["Mon district"]
    assert not local_news.mentions(_a("Monday rally in Kohima"), local_news.mention_terms("Mon"))


def test_low_quality_filter():
    for junk in ["Gold Rate Today in Nalgonda", "[116] The Nalgonda Plate, Div II --- Terms",
                 "TS Police Recruitment 2026 notification", "FreeJobAlert.Com",
                 "Anumana Pakshi Movie Show Time in Nalgonda"]:
        assert local_news.LOW_QUALITY.search(junk), junk
    assert not local_news.LOW_QUALITY.search("Foundation stone laid for 4-lane ROB at Guntur")


# ── API ───────────────────────────────────────────────────────────────────────

def test_location_endpoints(client):
    assert client.get("/api/locations/countries").json()["countries"] == [{"code": "IN", "name": "India"}]
    assert len(client.get("/api/locations/states").json()["states"]) == 36
    assert len(client.get("/api/locations/districts", params={"state": "Andhra Pradesh"}).json()["districts"]) == 26
    assert client.get("/api/locations/districts", params={"state": "Atlantis"}).status_code == 404


def test_local_news_stores_caches_and_stays_out_of_sections(client, monkeypatch):
    calls = []

    async def fake_gather(state, district):
        calls.append((state, district))
        now = datetime.now(timezone.utc)
        story = lambda n, t: {"title": t, "url": f"https://local.example/{n}", "source": "The Hindu",
                              "published_at": now, "content": t, "summary": t, "category": "local"}
        return {"district": [story(1, "Foundation stone laid for ROB at Guntur")],
                "state": [story(2, "Andhra Pradesh to expand irrigation network")]}

    monkeypatch.setattr(local_news, "gather", fake_gather)

    params = {"state": "Andhra Pradesh", "district": "Guntur"}
    first = client.get("/api/local", params=params).json()
    assert [s["title"] for s in first["district_stories"]] == ["Foundation stone laid for ROB at Guntur"]
    assert first["state_stories"][0]["category"] == "local" and first["cached"] is False

    second = client.get("/api/local", params=params).json()
    assert second["cached"] is True and len(calls) == 1          # served from the per-location cache

    story_id = first["district_stories"][0]["id"]
    assert client.get(f"/api/news/{story_id}").status_code == 200  # opens in the article page
    listed = {a["id"] for a in client.get("/api/news", params={"limit": 50}).json()["articles"]}
    assert story_id not in listed                                  # not in national sections / ticker

    assert client.get("/api/local", params={"state": "Telangana", "district": "Guntur"}).status_code == 404
    assert client.get("/api/local", params={"state": "Texas"}).status_code == 404


def test_edition_pages_are_filtered():
    assert local_news.LOW_QUALITY.search("Guntur edition - Sep 28, 2026")
    assert local_news.LOW_QUALITY.search("Prajasakti ePaper")
    assert not local_news.LOW_QUALITY.search("Special edition of the Guntur book fair opens")


def test_same_local_story_from_several_outlets_is_collapsed():
    from db.models import Article
    rows = [Article(id=i, title=t, source=s, url=f"https://x/{i}", category="local", raw_content="", summary="")
            for i, (t, s) in enumerate([
                ("Worker from Tamil Nadu found dead in Nalgonda", "The New Indian Express"),
                ("Tamil Nadu worker found murdered in Nalgonda", "The Times of India"),
                ("Tamil Nadu worker found dead in Nalgonda apartment", "The Siasat Daily"),
                ("Collector inspects paddy procurement centres in Nalgonda", "Telangana Today"),
                ("New bus depot proposed for Miryalaguda", "The Hindu"),
            ], start=1)]
    stories = local_news.collapse(rows)
    assert [s["coverage_count"] for s in stories] == [3, 1, 1]
    assert stories[0]["title"] == "Worker from Tamil Nadu found dead in Nalgonda"
    assert {c["source"] for c in stories[0]["coverage"]} == {"The Times of India", "The Siasat Daily"}

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import agents.orchestrator as orchestrator
from api import deps
from main import app

ADMIN = {"X-Admin-Token": "test-admin-token"}


def _fake_article(n: int, category: str = "technology") -> dict:
    return {
        "title": f"New AI chip number {n} unveiled",
        "url": f"https://example.com/{category}/{n}",
        "source": "Example",
        "published_at": datetime.now(timezone.utc),
        "content": "An AI chip from a startup promises faster software.",
        "summary": "An AI chip from a startup.",
        "category": category,
    }


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_limits():
    for limiter in (deps.chat_limit, deps.analyze_limit, deps.refresh_limit, deps.trending_limit):
        limiter._hits.clear()
    orchestrator._last_refresh.clear()


def test_health_reports_features(client):
    body = client.get("/api/health").json()
    assert body["service"] == "Upily"
    assert body["database"] == "ok"
    assert body["features"]["ai_analysis"] is False


def test_unknown_category_is_rejected(client):
    assert client.get("/api/news", params={"category": "nope"}).status_code == 404
    assert client.post("/api/news/refresh/nope").status_code == 404


def test_refresh_adds_articles_and_never_deletes_on_empty_fetch(client, monkeypatch):
    async def fetch_two(self, category):
        return [_fake_article(1, category), _fake_article(2, category)]

    monkeypatch.setattr(orchestrator.OrchestratorAgent, "_fetch", fetch_two)
    res = client.post("/api/news/refresh/technology")
    assert res.status_code == 200, res.text
    assert res.json()["added"] == 2

    # Immediate second refresh of the same category is on cooldown
    assert client.post("/api/news/refresh/technology").status_code == 429

    # A failed/empty fetch must leave existing articles alone
    orchestrator._last_refresh.clear()

    async def fetch_none(self, category):
        return []

    monkeypatch.setattr(orchestrator.OrchestratorAgent, "_fetch", fetch_none)
    res = client.post("/api/news/refresh/technology")
    assert res.status_code == 200
    assert res.json()["added"] == 0
    assert len(res.json()["articles"]) == 2

    listing = client.get("/api/news", params={"category": "technology"}).json()
    assert listing["total"] == 2
    first = listing["articles"][0]
    assert first["published_at"].endswith("+00:00")   # timezone is always explicit
    assert "raw_content" not in first                 # list payload stays light


def test_article_detail_and_404(client):
    article_id = client.get("/api/news").json()["articles"][0]["id"]
    assert client.get(f"/api/news/{article_id}").json()["id"] == article_id
    assert client.get("/api/news/999999").status_code == 404


def test_ai_endpoints_report_unconfigured(client):
    article_id = client.get("/api/news").json()["articles"][0]["id"]
    assert client.post(f"/api/news/{article_id}/analyze").status_code == 503
    assert client.post("/api/chat", json={"question": "What is new in AI?"}).status_code == 503


def test_chat_validates_input(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/api/chat", json={"question": "hi", "article_data": {"title": "x"}}).status_code in (422, 503)


def test_enrich_requires_admin_token(client):
    article_id = client.get("/api/news").json()["articles"][0]["id"]
    payload = {"summary": "Edited", "deep_explanation": "Edited body"}
    assert client.patch(f"/api/news/{article_id}/enrich", json=payload).status_code == 401
    assert client.patch(f"/api/news/{article_id}/enrich", json=payload,
                        headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.patch(f"/api/news/{article_id}/enrich", json=payload, headers=ADMIN).status_code == 200
    assert client.get(f"/api/news/{article_id}").json()["is_analyzed"] is True


def test_rate_limit(client):
    codes = [client.post("/api/chat", json={"question": "hello there"}).status_code for _ in range(14)]
    assert codes[-1] == 429
    assert codes.count(429) == 2


def test_rate_limit_key_cannot_be_spoofed():
    from starlette.requests import Request
    req = Request({"type": "http", "headers": [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.9")], "client": ("10.0.0.1", 1)})
    assert deps.client_ip(req) == "203.0.113.9"   # the proxy-appended entry, not the client-supplied one


def test_story_groups_collapse_with_coverage(client, monkeypatch):
    async def fetch_same_story(self, category):
        base = {"published_at": datetime.now(timezone.utc), "category": category,
                "content": "Pumpkin enzyme weakens peanut allergy proteins in lab tests.",
                "summary": "Pumpkin enzyme and peanut allergy."}
        return [
            {**base, "title": "Pumpkin-derived enzyme weakens peanut allergy proteins",
             "url": "https://a.example/pumpkin", "source": "Phys.org"},
            {**base, "title": "Enzyme from pumpkins weakens peanut allergy proteins, study finds",
             "url": "https://b.example/pumpkin", "source": "New Scientist"},
        ]

    monkeypatch.setattr(orchestrator.OrchestratorAgent, "_fetch", fetch_same_story)
    assert client.post("/api/news/refresh/science").json()["added"] == 2

    stories = client.get("/api/news", params={"category": "science"}).json()["articles"]
    assert len(stories) == 1                      # two outlets, one story
    assert stories[0]["coverage_count"] == 2
    other = stories[0]["coverage"][0]
    assert other["source"] in {"Phys.org", "New Scientist"} and other["source"] != stories[0]["source"]

    detail = client.get(f"/api/news/{stories[0]['id']}").json()
    assert detail["coverage"][0]["id"] == other["id"]


def test_migrations_match_models(client):
    """Works on SQLite and PostgreSQL alike (uses the app's own async driver)."""
    import asyncio

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine
    from db.database import Base, DATABASE_URL

    async def check():
        eng = create_async_engine(DATABASE_URL)
        async with eng.connect() as conn:
            diff = await conn.run_sync(lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata))
            version = (await conn.exec_driver_sql("select version_num from alembic_version")).scalar()
        await eng.dispose()
        return diff, version

    diff, version = asyncio.run(check())
    assert diff == []
    assert version == "0002"

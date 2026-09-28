"""Reader-facing discovery endpoints: search, the daily briefing, currency rates."""
import logging
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import RateLimiter, trending_limit
from api.routes.news import collapse_groups
from db.database import get_db
from db.models import Article
from services import calendar_service, llm_service, rates_service
from services.dates import utcnow
from services.news_service import CATEGORIES
from services.search_service import rank

log = logging.getLogger(__name__)
router = APIRouter()

search_limit = RateLimiter(max_calls=40, per_seconds=60, scope="search")


# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search", dependencies=[Depends(search_limit)])
async def search(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Keyword search over stored stories (same ranking as the chat's retrieval), one hit per story group."""
    rows = (await db.execute(select(Article).order_by(desc(Article.fetched_at)).limit(600))).scalars().all()
    ranked = rank(q, rows)
    scores = {a.id: s for s, a in ranked}
    stories = await collapse_groups(db, [a for _, a in ranked])
    for s in stories:
        s["score"] = round(scores.get(s["id"], 0.0), 3)
    return {"query": q, "results": stories[:limit], "total": len(stories)}


# ── Daily briefing ────────────────────────────────────────────────────────────

BRIEFING_HOURS = 24
_intro_cache: dict = {"key": None, "text": None, "expires": 0.0}

INTRO_SYSTEM = (
    "You are the editor of Upily, writing the two-to-three sentence opening of today's briefing. "
    "Use ONLY the headlines and summaries given; do not add facts. Plain text, no lists, no markdown."
)


def _lead_score(story: dict) -> float:
    return (story.get("importance_score") or 0) + 0.05 * min(story.get("coverage_count", 1) - 1, 4)


async def _editors_note(items: list[dict]) -> str | None:
    """One cached LLM call per edition; the briefing works without it."""
    if not items or not llm_service.is_llm_configured():
        return None
    key = tuple(i["story"]["id"] for i in items)
    if _intro_cache["key"] == key and time.monotonic() < _intro_cache["expires"]:
        return _intro_cache["text"]
    lines = "\n".join(f"- [{i['section']}] {i['story']['title']}: {i['story'].get('summary') or ''}" for i in items)
    try:
        text = await llm_service.chat(f"Today's top stories:\n{lines}\n\nWrite the opening.",
                                      system=INTRO_SYSTEM, max_tokens=220, retries=0)
    except llm_service.LLMError as e:
        log.info("Briefing intro skipped: %s", e)
        return None
    _intro_cache.update(key=key, text=text.strip(), expires=time.monotonic() + 60 * 60)
    return _intro_cache["text"]


@router.get("/briefing", dependencies=[Depends(trending_limit)])
async def briefing(db: AsyncSession = Depends(get_db)):
    """The day in brief: the top story from each section, an editor's note, and key market events."""
    since = utcnow() - timedelta(hours=BRIEFING_HOURS)
    items = []
    for cat in CATEGORIES:
        rows = (await db.execute(
            select(Article).where(Article.category == cat, Article.fetched_at >= since)
            .order_by(desc(Article.importance_score), desc(Article.fetched_at)).limit(40)
        )).scalars().all()
        if not rows:
            # Quiet desk (e.g. forex at the weekend): fall back to its latest story
            rows = (await db.execute(
                select(Article).where(Article.category == cat).order_by(desc(Article.fetched_at)).limit(10)
            )).scalars().all()
        if rows:
            top = max(await collapse_groups(db, rows), key=_lead_score)
            items.append({"section": cat, "story": top})

    # Don't list the same event twice when it made the top of two sections
    seen, unique = set(), []
    for item in items:
        key = item["story"].get("cluster_id") or -item["story"]["id"]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    events = []
    try:
        week = await calendar_service.get_week()
        now, horizon = utcnow().isoformat(), (utcnow() + timedelta(hours=36)).isoformat()
        events = [e for e in week["events"] if e["impact"] == "High" and e["time"] and now <= e["time"] <= horizon][:5]
    except Exception:
        pass

    words = sum(len((i["story"].get("summary") or "").split()) + len(i["story"]["title"].split()) for i in unique)
    return {
        "generated_at": utcnow().isoformat(),
        "editors_note": await _editors_note(unique),
        "items": unique,
        "market_events": events,
        "reading_minutes": max(1, round(words / 200)),
    }


# ── Currency rates ────────────────────────────────────────────────────────────

@router.get("/rates", dependencies=[Depends(trending_limit)])
async def currency_rates():
    try:
        return await rates_service.get_rates()
    except Exception:
        raise HTTPException(status_code=503, detail="Currency rates are unavailable right now.")

"""
Trending route — fetches LIVE top headlines from GNews + SerpAPI,
then uses LLM to extract the hottest topics right now.
Cached for 30 minutes to avoid hammering the APIs.
"""
import json
import re
import time
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtparser

from fastapi import APIRouter
from config import settings
from services import llm_service
from services.news_service import sanitize_summary

router = APIRouter()

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_ts: float = 0
CACHE_TTL = 30 * 60  # 30 minutes

SYSTEM = (
    "You are a real-time news trend analyst. "
    "Identify what topics are HOT and being widely discussed right now. "
    "Be specific, punchy, and insightful."
)


# ─────────────────────────────────────────────────────────────────────────────
# Live news fetchers
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_gnews_top() -> list[dict]:
    """Fetch top headlines from GNews across all categories."""
    if not settings.GNEWS_API_KEY:
        return []
    articles = []
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://gnews.io/api/v4/top-headlines",
                params={
                    "apikey": settings.GNEWS_API_KEY,
                    "lang":   "en",
                    "max":    20,
                },
            )
            if resp.status_code == 200:
                for a in resp.json().get("articles", []):
                    articles.append({
                        "title":        a.get("title", ""),
                        "url":          a.get("url", ""),
                        "source":       a.get("source", {}).get("name", "GNews"),
                        "published_at": a.get("publishedAt", ""),
                        "summary":      sanitize_summary(a.get("description") or a.get("title") or ""),
                        "image":        a.get("image", ""),
                    })
            else:
                print(f"[Trending] GNews {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[Trending] GNews fetch failed: {e}")
    return articles


async def _fetch_serpapi_trending() -> list[dict]:
    """Fetch Google News top stories via SerpAPI."""
    if not settings.SERPAPI_API_KEY:
        return []
    articles = []
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine":  "google_news",
                    "api_key": settings.SERPAPI_API_KEY,
                    "gl":      "us",
                    "hl":      "en",
                    # No 'q' param = Google News top stories
                },
            )
            if resp.status_code == 200:
                for a in resp.json().get("news_results", [])[:20]:
                    raw_date = a.get("date", "")
                    # Normalize SerpAPI date
                    pub_at = _normalize_date(raw_date)
                    articles.append({
                        "title":        a.get("title", ""),
                        "url":          a.get("link", ""),
                        "source":       a.get("source", {}).get("name", "Google News"),
                        "published_at": pub_at,
                        "summary":      sanitize_summary(a.get("snippet") or a.get("title") or ""),
                        "image":        a.get("thumbnail", ""),
                    })
            else:
                print(f"[Trending] SerpAPI {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[Trending] SerpAPI fetch failed: {e}")
    return articles


def _normalize_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    if "ago" in raw.lower() or "hour" in raw.lower() or "minute" in raw.lower():
        return datetime.now(timezone.utc).isoformat()
    try:
        cleaned = raw.replace(", +0000 UTC", "+00:00").replace(", +0000", "+00:00")
        return dtparser.parse(cleaned).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def _deduplicate(articles: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in articles:
        key = a.get("title", "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# LLM topic extraction
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_topics(articles: list[dict]) -> list[dict]:
    headlines = "\n".join(
        f"{i+1}. [{a.get('source','')}] {a.get('title','')}"
        for i, a in enumerate(articles[:30])
    )

    prompt = f"""These are the top news headlines right now. Identify the 5 HOTTEST trending topics.

For each topic return a JSON object with:
- "topic": short name (3-5 words)
- "emoji": one relevant emoji  
- "headline": one punchy sentence about what's happening (max 20 words)
- "why_trending": 1-2 sentences on why this is hot right now
- "category": one of: technology, world, science, business, health, entertainment, sports
- "article_indices": list of headline numbers (1-based) that relate to this topic

Headlines:
{headlines}

Return ONLY a valid JSON array of 5 objects. No markdown, no extra text."""

    try:
        raw = await llm_service.chat(prompt, system=SYSTEM, max_tokens=700)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        parsed = json.loads(m.group())
        topics = []
        for t in parsed[:5]:
            indices = [i - 1 for i in (t.get("article_indices") or []) if isinstance(i, int)]
            related = [articles[i] for i in indices if 0 <= i < len(articles)][:3]
            topics.append({
                "topic":        t.get("topic", ""),
                "emoji":        t.get("emoji", "📰"),
                "headline":     t.get("headline", ""),
                "why_trending": t.get("why_trending", ""),
                "category":     t.get("category", "general"),
                "articles":     related,
            })
        return topics
    except Exception as e:
        print(f"[Trending] LLM topic extraction failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/trending")
async def get_trending():
    global _cache, _cache_ts

    # Serve from cache if still fresh
    if _cache and (time.time() - _cache_ts) < CACHE_TTL:
        print("[Trending] Serving from cache")
        return _cache

    print("[Trending] Fetching live news from GNews + SerpAPI...")

    # Fetch from both APIs in parallel
    gnews_articles, serp_articles = await asyncio.gather(
        _fetch_gnews_top(),
        _fetch_serpapi_trending(),
    )

    all_articles = _deduplicate(gnews_articles + serp_articles)
    print(f"[Trending] Got {len(all_articles)} unique articles (gnews={len(gnews_articles)}, serp={len(serp_articles)})")

    if not all_articles:
        return {"topics": [], "articles": [], "total": 0, "source": "live"}

    # Extract trending topics with LLM
    topics = await _extract_topics(all_articles)

    # Fallback topics if LLM fails — group by source
    if not topics:
        topics = [
            {
                "topic":        a["title"][:45],
                "emoji":        "🔥",
                "headline":     a.get("summary", a["title"])[:100],
                "why_trending": "Currently one of the top stories.",
                "category":     "general",
                "articles":     [a],
            }
            for a in all_articles[:5]
        ]

    result = {
        "topics":   topics,
        "articles": all_articles[:12],   # top 12 raw articles for the feed
        "total":    len(all_articles),
        "source":   "live",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    _cache    = result
    _cache_ts = time.time()

    return result

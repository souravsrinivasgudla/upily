"""
SearchService — keyword search over stored articles ("memory") and optional web search.

Memory search is plain lexical scoring, so it works on SQLite and Postgres with
any LLM provider (the previous pgvector design only worked with OpenAI embeddings
on Postgres, and silently returned nothing everywhere else).
"""
import logging
import re
from typing import Any, Dict, List

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Article

log = logging.getLogger(__name__)

_STOPWORDS = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into
is it its me more most my no not of on or our so than that the their them then there these they
this to up us was we were what when where which who why will with would you your about tell
explain latest news today any some give show whats what's happening happened
story stories headline headlines big biggest top recent current week now new
""".split())

# Section names and common synonyms → category
SECTION_WORDS = {
    "technology": "technology", "tech": "technology", "ai": "technology",
    "world": "world", "international": "world", "global": "world",
    "science": "science", "scientific": "science", "space": "science",
    "business": "business", "markets": "business", "market": "business", "economy": "business",
    "finance": "business", "health": "health", "medical": "health", "medicine": "health",
    "entertainment": "entertainment", "movies": "entertainment", "film": "entertainment",
    "music": "entertainment", "sports": "sports", "sport": "sports",
}


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if t not in _STOPWORDS and len(t) > 1]


def score_article(tokens: List[str], article: Article) -> float:
    """0..1 — fraction of query terms found, weighting title and section matches higher."""
    if not tokens:
        return 0.0
    sections = {SECTION_WORDS[t] for t in tokens if t in SECTION_WORDS}
    if sections and article.category in sections:
        # Asking about a section: its stories match; other terms refine the order
        others = [t for t in tokens if t not in SECTION_WORDS]
        return 0.7 + 0.3 * (score_article(others, article) if others else 1.0)
    title = set(tokenize(article.title))
    body = set(tokenize(" ".join(filter(None, [
        article.summary, article.raw_content, " ".join(article.tags or []), article.category,
    ]))))
    total = sum(1.0 if t in title else 0.6 if t in body else 0.0 for t in set(tokens))
    return min(total / len(set(tokens)), 1.0)


async def search_memory(query: str, db: AsyncSession, top_k: int = 5) -> List[Dict[str, Any]]:
    tokens = tokenize(query)
    rows = (await db.execute(
        select(Article).order_by(desc(Article.fetched_at)).limit(400)
    )).scalars().all()

    if not tokens:
        # Generic "what's in the news?" — the most important recent stories
        # — one per section first, so a tie on importance doesn't return only one desk
        ranked = sorted(rows, key=lambda a: a.importance_score or 0, reverse=True)
        picked, seen = [], set()
        for a in ranked:
            if a.category not in seen:
                picked.append(a)
                seen.add(a.category)
        picked += [a for a in ranked if a not in picked]
        return [_hit(a, 0.5) for a in picked[:top_k]]

    scored = [(score_article(tokens, a), a) for a in rows]
    scored = [(s, a) for s, a in scored if s >= 0.3]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_hit(a, s) for s, a in scored[:top_k]]


def _hit(a: Article, score: float) -> Dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "summary": a.summary or "",
        "source": a.source,
        "category": a.category,
        "similarity": round(score, 3),
    }


async def search_web(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """Serper (Google) when a key is set, else DuckDuckGo instant answers. Never raises."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if settings.SERPER_API_KEY:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": settings.SERPER_API_KEY},
                    json={"q": query, "num": max_results},
                )
                if resp.status_code != 200:
                    return []
                return [
                    {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")}
                    for i in (resp.json().get("organic") or [])[:max_results]
                ]

            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            if data.get("AbstractText"):
                results.append({"title": data.get("Heading") or query,
                                 "url": data.get("AbstractURL", ""),
                                 "snippet": data["AbstractText"]})
            for rel in data.get("RelatedTopics") or []:
                if len(results) >= max_results:
                    break
                if isinstance(rel, dict) and rel.get("Text"):
                    results.append({"title": rel["Text"][:80], "url": rel.get("FirstURL", ""),
                                    "snippet": rel["Text"]})
            return results
    except Exception as e:
        log.info("Web search failed: %s", type(e).__name__)
        return []

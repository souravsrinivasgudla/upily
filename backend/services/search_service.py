"""
SearchService — retrieval over stored articles ("memory") and optional web search.

Memory search is lexical (BM25-style): rare terms weigh more than common ones,
simple suffix stemming matches plurals/tenses, and acronyms like "C.D.C." are
normalised. It needs no embeddings, so it works on SQLite and Postgres with any
LLM provider.
"""
import logging
import math
import re
from collections import Counter
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
he she him her his hers one also just get got over after before out
going go goes doing anything something everything know like update updates info information things
""".split())

# A query made only of these words browses that section ("science news", "sport stories").
# Mixed with other words they add a small boost, never override the match.
SECTION_WORDS = {
    "technology": "technology", "tech": "technology",
    "world": "world",
    "science": "science",
    "business": "business",
    "health": "health",
    "entertainment": "entertainment",
    "sport": "sports",
    "india": "india",
}
SECTION_BOOST = 0.15
MIN_SCORE = 0.35
TITLE_WEIGHT, BODY_WEIGHT = 1.0, 0.7

_ACRONYM = re.compile(r"\b(?:[a-z]\.){2,}")


def stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith(("sses", "shes", "ches", "xes")):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    if len(t) > 5 and t.endswith("ing"):
        return t[:-3]
    if len(t) > 4 and t.endswith("ed"):
        return t[:-2]
    return t


def tokenize(text: str) -> List[str]:
    text = (text or "").lower().replace("’", "'")
    text = _ACRONYM.sub(lambda m: m.group(0).replace(".", ""), text)   # c.d.c. → cdc
    text = re.sub(r"'s\b", "", text)                                     # cdc's → cdc
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text)
            if t not in _STOPWORDS and len(t) > 1]


def _doc_terms(a: Article) -> tuple[set, set]:
    title = set(tokenize(a.title))
    body = set(tokenize(" ".join(filter(None, [
        a.summary, a.raw_content, " ".join(a.tags or []), (a.deep_explanation or "")[:2000],
    ]))))
    return title, body


def rank(query: str, articles: List[Article]) -> List[tuple[float, Article]]:
    """Score every article 0..1 for the query; returns matches above MIN_SCORE, best first."""
    q = list(dict.fromkeys(tokenize(query)))
    if not q or not articles:
        return []

    sections = {SECTION_WORDS[t] for t in q if t in SECTION_WORDS}
    terms = [t for t in q if t not in SECTION_WORDS] if sections else q

    if sections and not terms:   # pure section browse
        hits = [a for a in articles if a.category in sections]
        hits.sort(key=lambda a: a.importance_score or 0, reverse=True)
        return [(0.8, a) for a in hits]

    docs = [(a, *_doc_terms(a)) for a in articles]
    n = len(docs)
    df = Counter(t for _, title, body in docs for t in (title | body))
    # Terms no stored story contains can't discriminate — score on the ones that can
    known = [t for t in terms if df[t]]
    if not known:
        return []
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in known}
    denom = sum(idf.values())

    scored = []
    for a, title, body in docs:
        s = sum(idf[t] * (TITLE_WEIGHT if t in title else BODY_WEIGHT if t in body else 0) for t in known)
        s /= denom
        # Penalise when most of what was asked is unknown to our coverage
        s *= len(known) / len(terms) if len(known) < len(terms) / 2 else 1.0
        if sections and a.category in sections:
            s += SECTION_BOOST
        if s >= MIN_SCORE:
            scored.append((min(s, 1.0), a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


async def search_memory(query: str, db: AsyncSession, top_k: int = 5) -> List[Dict[str, Any]]:
    rows = (await db.execute(
        select(Article).order_by(desc(Article.fetched_at)).limit(400)
    )).scalars().all()

    if not tokenize(query):
        # Generic "what's in the news?" — the most important recent stories,
        # one per section first so a tie on importance doesn't return a single desk
        ranked = sorted(rows, key=lambda a: a.importance_score or 0, reverse=True)
        picked, seen = [], set()
        for a in ranked:
            if a.category not in seen:
                picked.append(a)
                seen.add(a.category)
        picked += [a for a in ranked if a not in picked]
        return [_hit(a, 0.5) for a in picked[:top_k]]

    hits, groups = [], set()
    for s, a in rank(query, rows):
        key = a.cluster_id if a.cluster_id is not None else -a.id
        if key in groups:        # another outlet's version of a story already included
            continue
        groups.add(key)
        hits.append(_hit(a, s))
        if len(hits) == top_k:
            break
    return hits


def _hit(a: Article, score: float) -> Dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "summary": a.summary or "",
        "excerpt": (a.deep_explanation or a.raw_content or "")[:700],
        "source": a.source,
        "category": a.category,
        "published_at": a.published_at.isoformat() if a.published_at else None,
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

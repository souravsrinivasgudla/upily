"""
SearchService — web search and semantic memory search.
Agents call these directly; no MCP layer.
"""
import json
import httpx
from typing import List, Dict, Any, Optional
from config import settings


# ── Web Search ────────────────────────────────────────────────────────────────

async def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search the web for real-time information.
    Uses Serper (Google) if key available, else DuckDuckGo instant answers.
    """
    if settings.SERPER_API_KEY:
        return await _serper_search(query, max_results)
    return await _duckduckgo_search(query, max_results)


async def _serper_search(query: str, max_results: int) -> List[Dict]:
    results = []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.SERPER_API_KEY},
            json={"q": query, "num": max_results},
        )
        if resp.status_code == 200:
            for item in resp.json().get("organic", [])[:max_results]:
                results.append({
                    "title":   item.get("title", ""),
                    "url":     item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
    return results


async def _duckduckgo_search(query: str, max_results: int) -> List[Dict]:
    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("AbstractText"):
                    results.append({
                        "title":   data.get("Heading", query),
                        "url":     data.get("AbstractURL", ""),
                        "snippet": data["AbstractText"],
                    })
                for rel in data.get("RelatedTopics", [])[:max_results - 1]:
                    if isinstance(rel, dict) and rel.get("Text"):
                        results.append({
                            "title":   rel["Text"][:80],
                            "url":     rel.get("FirstURL", ""),
                            "snippet": rel["Text"],
                        })
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
    return results


# ── Memory Search (pgvector) ──────────────────────────────────────────────────

async def search_memory(
    query: str,
    top_k: int = 5,
    db=None,
) -> List[Dict[str, Any]]:
    """
    Semantic search over stored articles using pgvector cosine similarity.
    Requires a live DB session.
    """
    if db is None:
        return []

    from db.database import is_sqlite
    if is_sqlite:
        # SQLite doesn't support pgvector operators like <=>
        # TODO: Implement local vector search (e.g. with FAISS or simple numpy)
        return []

    query_embedding = await embed_text(query)
    if not query_embedding:
        return []

    from sqlalchemy import text as sa_text
    sql = sa_text("""
        SELECT id, title, summary, deep_explanation, why_it_matters,
               1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM articles
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :top_k
    """)
    result = await db.execute(sql, {
        "embedding": json.dumps(query_embedding),
        "top_k": top_k,
    })
    rows = result.fetchall()
    return [
        {
            "id":              row.id,
            "title":           row.title,
            "summary":         row.summary,
            "deep_explanation":row.deep_explanation,
            "why_it_matters":  row.why_it_matters,
            "similarity":      float(row.similarity),
        }
        for row in rows
    ]


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed_text(text_input: str) -> Optional[List[float]]:
    """Generate an embedding vector using OpenAI."""
    if not (settings.OPENAI_API_KEY and settings.LLM_PROVIDER == "openai"):
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text_input[:8000],
        )
        return resp.data[0].embedding
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

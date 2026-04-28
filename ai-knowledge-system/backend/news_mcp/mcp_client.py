"""
MCP Client — calls the MCP News Server via the fast /invoke endpoint.

Uses a single HTTP POST instead of the multi-round-trip SSE protocol,
which reduces latency from ~5-10 s down to ~1-3 s (first load).
Subsequent calls for the same category are served from cache on the
MCP server side in <50 ms.

Gracefully falls back to news_service if the MCP server is offline.
"""

import asyncio
import httpx
from typing import Optional

from config import settings

INVOKE_URL  = f"{settings.MCP_SERVER_URL}/invoke"
HEALTH_URL  = f"{settings.MCP_SERVER_URL}/health"
HTTP_TIMEOUT = 30   # seconds — RSS + GNews + SerpApi can each take up to ~8s in parallel


# ─────────────────────────────────────────────────────────────────────────────
# Core: one-shot POST to /invoke
# ─────────────────────────────────────────────────────────────────────────────

async def _invoke(tool: str, args: dict) -> list[dict]:
    """
    Call a tool on the MCP server via POST /invoke.
    Returns a list of article dicts or raises on error.
    """
    payload = {"tool": tool, "args": args}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(INVOKE_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        elapsed = data.get("elapsed_ms", "?")
        cached  = data.get("cached", False)
        count   = data.get("count", 0)
        print(f"[MCP Client] {tool} -> {count} articles  ({elapsed} ms{'  [cached]' if cached else ''})")
        return data.get("articles", [])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def is_mcp_server_available() -> bool:
    """Quick health check — non-blocking, 3-second timeout."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(HEALTH_URL)
            return resp.status_code == 200
    except Exception:
        return False


async def get_live_news(
    category: str = "general",
    max_results: int = 20,
) -> list[dict]:
    """
    Fetch live news via MCP /invoke tool.
    Falls back to news_service if MCP server is unreachable.
    """
    try:
        return await _invoke("get_live_news", {"category": category, "max_results": max_results})
    except Exception as e:
        print(f"[MCP Client] invoke failed ({e}), falling back to news_service...")
        from services import news_service
        return await news_service.fetch_articles(category=category, max_results=max_results)


async def search_news(query: str, max_results: int = 10) -> list[dict]:
    """
    Search news via MCP /invoke tool.
    Falls back to news_service if MCP server is unreachable.
    """
    try:
        return await _invoke("search_news", {"query": query, "max_results": max_results})
    except Exception as e:
        print(f"[MCP Client] search invoke failed ({e}), falling back...")
        from services import news_service
        return await news_service.fetch_articles(query=query, max_results=max_results)


async def get_trending_news(max_results: int = 15) -> list[dict]:
    """
    Get trending news via MCP /invoke tool.
    Falls back to news_service if MCP server is unreachable.
    """
    try:
        return await _invoke("get_trending_news", {"max_results": max_results})
    except Exception as e:
        print(f"[MCP Client] trending invoke failed ({e}), falling back...")
        from services import news_service
        return await news_service.fetch_articles(trending=True, max_results=max_results)

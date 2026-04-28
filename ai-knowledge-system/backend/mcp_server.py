"""
MCP News Server — Standalone Model Context Protocol server.

Exposes live news fetching as MCP tools AND a fast /invoke REST endpoint.

Run with:
    python mcp_server.py

Server starts on http://localhost:8002
"""

import asyncio
import os
import time as _time
import httpx
import feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser as dtparser
from dotenv import load_dotenv

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ── MCP SDK ───────────────────────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types

# ── Config ────────────────────────────────────────────────────────────────────
GNEWS_API_KEY   = os.getenv("GNEWS_API_KEY", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
NEWS_API_KEY    = os.getenv("NEWS_API_KEY", "")
PORT            = int(os.getenv("MCP_PORT", "8002"))
CACHE_TTL       = 300   # seconds (5 minutes)

# ── RSS feeds ─────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.wired.com/feed/rss",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index/",
    ],
    "world": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
    "science": [
        "https://phys.org/rss-feed/",
        "https://www.newscientist.com/feed/home/",
        "https://www.space.com/feeds/all",
        "https://rss.scientificamerican.com/scientific-american/all-articles",
    ],
    "business": [
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "https://finance.yahoo.com/news/rssindex",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    ],
    "health": [
        # Confirmed working health RSS feeds
        "https://www.healthline.com/rss/health-news",
        "https://feeds.npr.org/1128/rss.xml",        # NPR Health
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://www.theguardian.com/society/health/rss",
        "https://www.statnews.com/feed/",
        "https://www.who.int/rss-feeds/news-english.xml",
    ],
    "entertainment": [
        "https://variety.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
        "https://deadline.com/feed/",
    ],
    "sports": [
        "https://www.espn.com/espn/rss/news",
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://rssfeeds.usatoday.com/UsatodaycomSports-TopStories",
        "https://www.skysports.com/rss/12040",  # Sky Sports latest
    ],
    "general": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://www.theguardian.com/world/rss",
    ],
}

QUERY_MAP = {
    "technology":    "latest technology AI artificial intelligence robotics gadgets software hardware",
    "world":         "breaking international news global events geopolitics war diplomacy",
    "science":       "scientific research discovery space biology physics astronomy climate",
    "business":      "business finance markets economy stocks earnings startup",
    "health":        "medical health disease treatment vaccine drug FDA hospital patient",
    "entertainment": "movies music celebrity Hollywood box office streaming awards",
    "sports":        "sports game match score goal win championship league NFL NBA FIFA",
    "general":       "top headlines breaking news today",
}

ALL_CATEGORIES = list(QUERY_MAP.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize(text: str, max_len: int = 200) -> str:
    import re, html
    clean = re.sub(r'<.*?>', '', text)
    clean = html.unescape(clean)
    clean = ' '.join(clean.split())
    if len(clean) <= max_len:
        return clean
    return clean[:max_len].rsplit(' ', 1)[0] + "..."


def _is_fresh(pub_str, hours: int = 20) -> bool:
    """Return True if the article was published within `hours` hours. 
    Returns False (not fresh) if date is missing or unparseable — 
    better to skip than show stale content."""
    if not pub_str:
        return False  # no date = unknown age, skip it
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        dt = dtparser.parse(str(pub_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except Exception:
        return False  # unparseable date = skip


def _deduplicate(articles: list, max_results: int) -> list:
    seen: set = set()
    out: list = []
    for a in articles:
        key = a.get("title", "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(a)
        if len(out) >= max_results:
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fetch helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_rss(category: str, max_results: int) -> list:
    urls = RSS_FEEDS.get(category.lower(), RSS_FEEDS["general"])

    async def _one(url: str):
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    out = []
                    for entry in feed.entries[:max_results * 2]:
                        pub = entry.get("published") or entry.get("updated")
                        if not _is_fresh(pub, hours=20):
                            continue
                        src = feed.feed.get("title", "RSS")
                        summary = _sanitize(
                            entry.get("summary") or entry.get("description") or entry.get("title") or ""
                        )
                        out.append({
                            "title":        entry.get("title", "").strip(),
                            "url":          entry.get("link", ""),
                            "source":       src,
                            "published_at": pub,
                            "summary":      summary,
                            "raw_content":  summary,
                            "category":     category,
                        })
                    if not out:
                        print(f"[MCP] RSS {url}: 0 fresh articles (all older than 20h)")
                    return out
                else:
                    print(f"[MCP] RSS {url}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[MCP] RSS error {url}: {e}")
        return []

    results = await asyncio.gather(*[_one(u) for u in urls])
    articles = [a for sub in results for a in sub]

    def _ts(a):
        try: return dtparser.parse(str(a["published_at"])).timestamp()
        except: return 0
    articles.sort(key=_ts, reverse=True)
    return articles[:max_results * 2]


async def _fetch_gnews(query: str, max_results: int) -> list:
    if not GNEWS_API_KEY:
        return []
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://gnews.io/api/v4/search",
                params={"q": query, "apikey": GNEWS_API_KEY, "max": max_results,
                        "lang": "en", "sortby": "publishedAt", "from": yesterday},
            )
            if resp.status_code == 200:
                return [
                    {"title": a.get("title", ""), "url": a.get("url", ""),
                     "source": a.get("source", {}).get("name", "GNews"),
                     "published_at": a.get("publishedAt"),
                     "summary": _sanitize(a.get("description") or a.get("title") or "")}
                    for a in resp.json().get("articles", [])
                ]
            print(f"[MCP] GNews {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[MCP] GNews error: {e}")
    return []


async def _fetch_serpapi(query: str, max_results: int, trending: bool = False) -> list:
    if not SERPAPI_API_KEY:
        return []
    params = {"engine": "google_news", "api_key": SERPAPI_API_KEY, "gl": "us", "hl": "en"}
    if not trending:
        params["q"] = query
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            if resp.status_code == 200:
                articles = []
                for a in resp.json().get("news_results", [])[:max_results]:
                    # SerpAPI date format: "04/05/2026, 07:00 AM, +0000 UTC"
                    # Normalize to ISO so _is_fresh can parse it
                    raw_date = a.get("date", "")
                    iso_date = _normalize_serpapi_date(raw_date)
                    # Skip stale articles — SerpAPI often returns old cached results
                    if not _is_fresh(iso_date):
                        continue
                    summary = _sanitize(a.get("snippet") or a.get("title") or "")
                    articles.append({
                        "title":        a.get("title", ""),
                        "url":          a.get("link", ""),
                        "source":       a.get("source", {}).get("name", "Google News"),
                        "published_at": iso_date,
                        "summary":      summary,
                        "raw_content":  summary,
                        "is_trending":  trending,
                    })
                return articles
            print(f"[MCP] SerpApi {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[MCP] SerpApi error: {e}")
    return []


def _normalize_serpapi_date(raw: str) -> str:
    """Convert SerpAPI date strings to ISO 8601 that dateutil can parse."""
    if not raw:
        return ""
    # Already ISO-ish
    if "T" in raw or raw.count("-") >= 2:
        return raw
    # Format: "04/05/2026, 07:00 AM, +0000 UTC"
    try:
        # Strip trailing timezone label like "UTC" after the offset
        cleaned = raw.replace(", +0000 UTC", "+00:00").replace(", +0000", "+00:00")
        dt = dtparser.parse(cleaned)
        return dt.isoformat()
    except Exception:
        pass
    # Relative like "2 hours ago" — treat as fresh
    if "ago" in raw.lower() or "hour" in raw.lower() or "minute" in raw.lower():
        return datetime.now(timezone.utc).isoformat()
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# In-memory cache
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict[str, tuple[list, float]] = {}


def _ck(tool: str, **kw) -> str:
    return tool + "|" + "|".join(f"{k}={v}" for k, v in sorted(kw.items()))


def _cache_get(key: str) -> list | None:
    entry = _cache.get(key)
    if entry and _time.monotonic() < entry[1]:
        print(f"[MCP Cache] HIT  {key}")
        return entry[0]
    _cache.pop(key, None)
    print(f"[MCP Cache] MISS {key}")
    return None


def _cache_set(key: str, articles: list) -> None:
    _cache[key] = (articles, _time.monotonic() + CACHE_TTL)


# ─────────────────────────────────────────────────────────────────────────────
# Cached fetch wrappers
# ─────────────────────────────────────────────────────────────────────────────

async def _cached_live_news(category: str, max_results: int) -> list:
    key = _ck("live", category=category)
    cached = _cache_get(key)
    if cached is not None:
        return cached[:max_results]

    query = QUERY_MAP.get(category.lower(), category)
    rss, gnews, serp = await asyncio.gather(
        _fetch_rss(category, max_results),
        _fetch_gnews(query, max_results),
        _fetch_serpapi(query, max_results),
    )
    merged = rss + gnews + serp

    # If we got nothing fresh, relax to 48h for RSS only as a fallback
    if not merged:
        print(f"[MCP] No fresh articles for {category}, relaxing to 48h window...")
        merged = await _fetch_rss_relaxed(category, max_results, hours=48)

    # Always enforce the requested category
    for a in merged:
        a["category"] = category

    result = _deduplicate(merged, max_results * 2)
    if result:
        _cache_set(key, result)
    print(f"[MCP] {category}: {len(result)} articles (rss={len(rss)}, gnews={len(gnews)}, serp={len(serp)})")
    return result[:max_results]


async def _fetch_rss_relaxed(category: str, max_results: int, hours: int = 48) -> list:
    """Fallback RSS fetch with relaxed freshness window."""
    urls = RSS_FEEDS.get(category.lower(), RSS_FEEDS["general"])

    async def _one(url: str):
        try:
            async with httpx.AsyncClient(
                timeout=10, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"},
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    out = []
                    for entry in feed.entries[:max_results]:
                        pub = entry.get("published") or entry.get("updated")
                        if not _is_fresh(pub, hours=hours):
                            continue
                        summary = _sanitize(
                            entry.get("summary") or entry.get("description") or entry.get("title") or ""
                        )
                        out.append({
                            "title":        entry.get("title", "").strip(),
                            "url":          entry.get("link", ""),
                            "source":       feed.feed.get("title", "RSS"),
                            "published_at": pub,
                            "summary":      summary,
                            "raw_content":  summary,
                            "category":     category,
                        })
                    return out
        except Exception:
            pass
        return []

    results = await asyncio.gather(*[_one(u) for u in urls])
    return [a for sub in results for a in sub]


async def _cached_search(query: str, max_results: int) -> list:
    key = _ck("search", q=query)
    cached = _cache_get(key)
    if cached is not None:
        return cached[:max_results]
    gnews, serp = await asyncio.gather(
        _fetch_gnews(query, max_results),
        _fetch_serpapi(query, max_results),
    )
    result = _deduplicate(gnews + serp, max_results)
    _cache_set(key, result)
    return result


async def _cached_trending(max_results: int) -> list:
    key = _ck("trending")
    cached = _cache_get(key)
    if cached is not None:
        return cached[:max_results]
    result = _deduplicate(
        await _fetch_serpapi("top stories", max_results, trending=True), max_results
    )
    _cache_set(key, result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MCP Server (SSE)
# ─────────────────────────────────────────────────────────────────────────────

mcp_server = Server("ai-knowledge-news-server")


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_live_news",
            description="Fetch the latest live news articles for a given category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string",
                                 "enum": ["technology","world","science","business",
                                          "health","entertainment","sports","general"]},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["category"],
            },
        ),
        types.Tool(
            name="search_news",
            description="Search for news articles matching a keyword query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_trending_news",
            description="Fetch current trending top stories from Google News.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "default": 15},
                },
                "required": [],
            },
        ),
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    import json
    print(f"[MCP] Tool called: {name}")
    if name == "get_live_news":
        articles = await _cached_live_news(
            arguments.get("category", "general"),
            int(arguments.get("max_results", 20)),
        )
    elif name == "search_news":
        articles = await _cached_search(
            arguments.get("query", ""), int(arguments.get("max_results", 10))
        )
    elif name == "get_trending_news":
        articles = await _cached_trending(int(arguments.get("max_results", 15)))
    else:
        articles = []
    return [types.TextContent(type="text", text=json.dumps(articles))]


# ─────────────────────────────────────────────────────────────────────────────
# Cache pre-warm on startup
# ─────────────────────────────────────────────────────────────────────────────

async def _prewarm_cache():
    print(f"[MCP] Pre-warming cache for {len(ALL_CATEGORIES)} categories...")
    tasks = [_cached_live_news(cat, 20) for cat in ALL_CATEGORIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    ok = sum(1 for r in results if not isinstance(r, Exception))
    print(f"[MCP] Cache pre-warm done: {ok}/{len(ALL_CATEGORIES)} categories OK")


# ─────────────────────────────────────────────────────────────────────────────
# Starlette HTTP app
# ─────────────────────────────────────────────────────────────────────────────

def build_starlette_app():
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse, Response
    from starlette.requests import Request

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )

    async def health(request):
        return JSONResponse({
            "status": "ok", "version": "3.0.0",
            "cache_entries": len(_cache),
            "tools": ["get_live_news", "search_news", "get_trending_news"],
        })

    async def invoke(request: Request):
        """POST /invoke — single-round-trip tool call (much faster than SSE)."""
        if request.method == "OPTIONS":
            return Response(status_code=200, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            })
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        tool         = body.get("tool", "")
        args         = body.get("args", {})
        t0           = _time.monotonic()
        cache_before = len(_cache)

        if tool == "get_live_news":
            articles = await _cached_live_news(
                args.get("category", "general"), int(args.get("max_results", 20))
            )
        elif tool == "search_news":
            articles = await _cached_search(
                args.get("query", ""), int(args.get("max_results", 10))
            )
        elif tool == "get_trending_news":
            articles = await _cached_trending(int(args.get("max_results", 15)))
        else:
            return JSONResponse({"error": f"Unknown tool: {tool}"}, status_code=400)

        return JSONResponse(
            {"articles": articles, "count": len(articles),
             "cached": len(_cache) == cache_before,
             "elapsed_ms": int((_time.monotonic() - t0) * 1000)},
            headers={"Access-Control-Allow-Origin": "*"},
        )

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        await _prewarm_cache()
        yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Route("/",          health),
            Route("/health",    health),
            Route("/invoke",    invoke, methods=["GET", "POST", "OPTIONS"]),
            Route("/sse",       handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("[MCP] -------------------------------------------------")
    print(f"[MCP] AI Knowledge News MCP Server  (port {PORT})")
    print("[MCP] -------------------------------------------------")
    print(f"[MCP] GNews API:   {'OK set' if GNEWS_API_KEY else 'MISSING'}")
    print(f"[MCP] SerpApi:     {'OK set' if SERPAPI_API_KEY else 'MISSING'}")
    print(f"[MCP] Health:      http://localhost:{PORT}/health")
    print(f"[MCP] Invoke:      http://localhost:{PORT}/invoke  (POST)")
    print(f"[MCP] Cache TTL:   {CACHE_TTL}s  |  Categories: {len(ALL_CATEGORIES)}")
    print("[MCP] -------------------------------------------------")

    uvicorn.run(build_starlette_app(), host="0.0.0.0", port=PORT, log_level="info")

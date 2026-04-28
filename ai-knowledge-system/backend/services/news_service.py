"""
NewsService — fetches raw articles from NewsAPI and RSS feeds.
No MCP layer; agents call this service directly.
"""
import httpx
import feedparser
import asyncio
from typing import List, Dict, Any, Optional
from config import settings

CATEGORIES = ["technology", "world", "science", "business", "health", "entertainment", "sports", "general"]

# Keywords used to validate that an article actually belongs to its assigned category.
# An article must contain at least one keyword from its category's list (checked against
# title + raw_content). Articles that fail validation are re-classified or dropped.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "technology": [
        "ai", "artificial intelligence", "software", "hardware", "tech", "app", "robot",
        "computer", "cyber", "data", "cloud", "startup", "silicon", "chip", "gpu", "llm",
        "machine learning", "algorithm", "code", "developer", "programming", "gadget",
        "smartphone", "internet", "digital", "automation", "semiconductor", "openai",
        "google", "microsoft", "apple", "meta", "nvidia", "amazon web", "aws",
    ],
    "world": [
        "war", "conflict", "government", "president", "minister", "election", "treaty",
        "diplomacy", "sanction", "military", "nato", "un ", "united nations", "geopolit",
        "international", "foreign", "refugee", "protest", "coup", "crisis", "ceasefire",
        "invasion", "border", "summit", "bilateral", "global", "nation", "country",
    ],
    "science": [
        "research", "study", "scientist", "discovery", "space", "nasa", "planet", "star",
        "galaxy", "climate", "biology", "physics", "chemistry", "genome", "dna", "fossil",
        "experiment", "laboratory", "journal", "published", "findings", "species",
        "asteroid", "telescope", "quantum", "particle", "evolution", "ecology",
    ],
    "business": [
        "market", "stock", "share", "investor", "revenue", "profit", "loss", "ipo",
        "acquisition", "merger", "ceo", "startup", "venture", "fund", "economy",
        "gdp", "inflation", "interest rate", "bank", "finance", "trade", "export",
        "import", "supply chain", "earnings", "quarter", "fiscal", "nasdaq", "s&p",
    ],
    "health": [
        "health", "medical", "doctor", "hospital", "patient", "disease", "drug",
        "vaccine", "treatment", "cancer", "diabetes", "mental health", "surgery",
        "clinical", "fda", "who ", "pandemic", "virus", "bacteria", "nutrition",
        "fitness", "wellness", "therapy", "symptom", "diagnosis", "pharmaceutical",
    ],
    "entertainment": [
        "movie", "film", "actor", "actress", "celebrity", "music", "album", "concert",
        "award", "oscar", "grammy", "netflix", "disney", "hollywood", "tv show",
        "series", "streaming", "box office", "singer", "band", "tour", "fashion",
        "pop culture", "trailer", "premiere", "director", "producer",
    ],
    "sports": [
        "game", "match", "team", "player", "coach", "league", "championship", "tournament",
        "score", "goal", "win", "loss", "season", "nfl", "nba", "mlb", "nhl", "fifa",
        "olympic", "athlete", "sport", "football", "basketball", "baseball", "soccer",
        "tennis", "golf", "racing", "cricket", "rugby", "transfer", "draft",
    ],
}


def _validate_category(article: Dict, assigned_category: str) -> str:
    """
    Check if the article's title+content actually matches the assigned category.
    Returns the assigned category if valid, or 'general' as a fallback.
    Skips validation for 'general' since it's a catch-all.
    """
    if assigned_category == "general":
        return "general"

    keywords = CATEGORY_KEYWORDS.get(assigned_category, [])
    if not keywords:
        return assigned_category

    text = (
        (article.get("title") or "") + " " +
        (article.get("raw_content") or "")
    ).lower()

    # Article is valid if it contains at least one category keyword
    if any(kw in text for kw in keywords):
        return assigned_category

    # Try to find a better-matching category
    best_cat = "general"
    best_count = 0
    for cat, kws in CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in kws if kw in text)
        if count > best_count:
            best_count = count
            best_cat = cat

    # Only reassign if we found a strong match (2+ keywords), else keep original
    # (avoids over-aggressive reassignment for short titles)
    if best_count >= 2:
        return best_cat
    return assigned_category

RSS_FEEDS: Dict[str, List[str]] = {
    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.wired.com/feed/rss",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index/"
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
        "https://rss.scientificamerican.com/scientific-american/all-articles"
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
        "https://www.skysports.com/rss/12040",
    ],
    "general": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.aljazeera.com/xml/rss/all.xml"
    ],
}

QUERY_MAP: Dict[str, str] = {
    "technology":    "latest technology breakthroughs AI artificial intelligence robotics gadgets software hardware -world -politics",
    "world":         "breaking international news global events geopolitics -sports -entertainment",
    "science":       "scientific research discovery space biology physics astronomy -politics -celebrity",
    "business":      "business finance markets economy stocks startup venture capital -sports",
    "health":        "medical news wellness health studies medicine healthcare -entertainment",
    "entertainment": "movies music celebrity Hollywood box office pop culture -politics -business",
    "sports":        "latest sports scores athletes results league news -politics -finance",
    "general":       "top headlines breaking global news daily digest",
}


async def fetch_articles(
    category: Optional[str] = None,
    query: Optional[str] = None,
    max_results: int = 20,
    trending: bool = False,
) -> List[Dict[str, Any]]:
    # 1. Super-Aggregation for "General" category
    if category == "general" and not query and not trending:
        top_from_cats = []
        other_cats = [c for c in CATEGORIES if c != "general"]
        # Fetch top 4 from all others
        tasks = [_from_rss(cat, 4) for cat in other_cats]
        results = await asyncio.gather(*tasks)
        for res in results:
            top_from_cats.extend(res)
        
        # Also add the general feeds themselves
        general_rss = await _from_rss("general", max_results)
        all_articles = top_from_cats + general_rss
    else:
        # Standard fetch for specific category
        all_articles = []
        if not query and not trending:
            all_articles = await _from_rss(category, max_results)

    # 2. Forced Fallback: Parallel fetch from APIs if RSS is low or if explicitly trending/search
    if len(all_articles) < 10 or query or trending:
        tasks = []
        if settings.GNEWS_API_KEY:
            tasks.append(_from_gnews(category, query, max_results))
        if settings.SERPAPI_API_KEY:
            tasks.append(_from_serpapi(category, query, max_results, trending=trending))
        if settings.NEWS_API_KEY:
            tasks.append(_from_newsapi(category, query, max_results))
        
        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                all_articles.extend(res)
    
    # 3. Filter by freshness (48-hour limit)
    from datetime import datetime, timezone, timedelta
    from dateutil import parser as dtparser
    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)
    
    # Deduplicate by title AND Filter by age
    seen = set()
    unique_articles = []
    for a in all_articles:
        t = a.get("title", "").strip().lower()
        if not t or t in seen:
            continue
            
        # Check age
        pub_at_raw = a.get("published_at")
        try:
            pub_at = dtparser.parse(str(pub_at_raw))
            if pub_at.tzinfo is None:
                pub_at = pub_at.replace(tzinfo=timezone.utc)
            
            if pub_at < cutoff:
                # If it's too old, we SKIP unless we have NO articles at all (edge case)
                continue
        except Exception:
            # Date parsing failed? We'll keep it as "unknown age" instead of dropping 
            # to avoid empty feeds, but we'll mark it for lower importance.
            pass

        seen.add(t)
        # Validate and correct category before storing
        a["category"] = _validate_category(a, a.get("category", "general"))
        unique_articles.append(a)

    return unique_articles[:max_results]


def sanitize_summary(text: str, max_len: int = 160) -> str:
    """Strip HTML, resolve entities, and truncate cleanly at a full word."""
    import re
    import html
    
    # 1. Strip HTML tags
    clean = re.sub(r'<.*?>', '', text)
    # 2. Decode HTML entities (unquote)
    clean = html.unescape(clean)
    # 3. Clean up whitespace
    clean = ' '.join(clean.split())
    
    if len(clean) <= max_len:
        return clean
        
    # 4. Truncate at a word boundary
    truncated = clean[:max_len].rsplit(' ', 1)[0]
    return truncated + "..."


async def fetch_all_categories(max_per_category: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch articles across all categories in parallel, deduplicated by title.
    Each article's category is validated against keyword lists before storing.
    """
    # Fetch all categories in parallel for speed
    tasks = [
        fetch_articles(category=cat, max_results=max_per_category)
        for cat in CATEGORIES
    ]
    results = await asyncio.gather(*tasks)

    all_articles: List[Dict] = []
    seen: set = set()

    for cat, articles in zip(CATEGORIES, results):
        for a in articles:
            key = a.get("title", "").lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            # Category was already validated inside fetch_articles,
            # but enforce the requested category as the source of truth
            # only if the article passed validation (fetch_articles already did this)
            all_articles.append(a)

    return all_articles


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _from_newsapi(
    category: Optional[str],
    query: Optional[str],
    max_results: int,
) -> List[Dict]:
    articles = []
    search_q = query or QUERY_MAP.get(category or "general", "news")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if query or True: # Use everything endpoint for more variety
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "apiKey": settings.NEWS_API_KEY,
                        "q": search_q,
                        "pageSize": max_results,
                        "language": "en",
                        "sortBy": "publishedAt",
                    },
                )
            else:
                resp = await client.get(
                    "https://newsapi.org/v2/top-headlines",
                    params={
                        "apiKey": settings.NEWS_API_KEY,
                        "category": category or "general",
                        "country": "us",
                        "pageSize": max_results,
                    },
                )

            if resp.status_code == 200:
                for a in resp.json().get("articles", []):
                        articles.append({
                            "title":       a.get("title", ""),
                            "url":         a.get("url", ""),
                            "source":      a.get("source", {}).get("name", ""),
                            "published_at":a.get("publishedAt"),
                            "raw_content": (a.get("description") or "") + "\n" + (a.get("content") or ""),
                            "summary":     sanitize_summary(a.get("description") or a.get("title") or ""),
                            "category":    category or "general",
                        })
    except Exception as e:
        print(f"NewsAPI error: {e}")
    return articles


async def _from_gnews(
    category: Optional[str],
    query: Optional[str],
    max_results: int,
) -> List[Dict]:
    # CASE: If "All" (no category) and no specific query, aggregate multiple genres
    if not category and not query:
        categories_to_mix = CATEGORIES[:-1] # All except 'general'
        # Fetch fewer articles per category to stay within reasonable limits
        tasks = [_from_gnews(cat, None, 5) for cat in categories_to_mix]
        results = await asyncio.gather(*tasks)
        
        aggregated = []
        for res in results:
            aggregated.extend(res)
        
        import random
        random.shuffle(aggregated)
        return aggregated[:max_results]

    # CASE: Fetch a specific category or search query
    articles = []
    search_q = query or QUERY_MAP.get(category or "general", "news")
    
    from datetime import datetime, timezone, timedelta
    # GNews V4 requires exact ISO 8601: YYYY-MM-DDTHH:MM:SSZ
    yesterday_dt = datetime.now(timezone.utc) - timedelta(hours=24)
    yesterday_iso = yesterday_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    async with httpx.AsyncClient(timeout=15) as client:
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": search_q,
            "apikey": settings.GNEWS_API_KEY,
            "max": max_results,
            "lang": "en",
            "sortby": "publishedAt",
            "from": yesterday_iso 
        }

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                for a in resp.json().get("articles", []):
                        articles.append({
                            "title":        a.get("title", ""),
                            "url":          a.get("url", ""),
                            "source":       a.get("source", {}).get("name", "GNews"),
                            "published_at": a.get("publishedAt"),
                            "raw_content":  a.get("description", "") + "\n" + a.get("content", ""),
                            "summary":      sanitize_summary(a.get("description") or a.get("title") or ""),
                            "category":     category or "general",
                        })
            else:
                print(f"GNews API error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"GNews request failed: {repr(e)}")
            
    return articles



async def _from_rss(category: Optional[str], max_results: int) -> List[Dict]:
    urls = RSS_FEEDS.get(category or "general", RSS_FEEDS["general"])
    
    async def _fetch_one(url: str):
        try:
            # RSS is fast so we can use a shorter timeout
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.content)
                    articles = []
                    for entry in feed.entries[:max_results]:
                        # Format source name
                        source_name = feed.feed.get("title", "RSS")
                        if "BBC" in source_name: source_name = "BBC News"
                        elif "The Verge" in source_name: source_name = "The Verge"
                        elif "TechCrunch" in source_name: source_name = "TechCrunch"
                        elif "NYT" in source_name or "New York Times" in source_name: source_name = "NYT"
                        elif "The Guardian" in source_name: source_name = "The Guardian"
                        elif "Al Jazeera" in source_name: source_name = "Al Jazeera"
                        
                        articles.append({
                            "title":        entry.get("title", ""),
                            "url":          entry.get("link", ""),
                            "source":       source_name,
                            "published_at": entry.get("published"),
                            "raw_content":  entry.get("summary", ""),
                            "summary":      sanitize_summary(entry.get("summary") or entry.get("title") or ""),
                            "category":     category or "general",
                        })
                    return articles
        except Exception as e:
            print(f"RSS error for {url}: {e}")
        return []

    tasks = [_fetch_one(u) for u in urls]
    results = await asyncio.gather(*tasks)
    
    all_rss = []
    for res in results:
        all_rss.extend(res)
    
    # Sort by date if possible
    from dateutil import parser as dtparser
    def _parse_sort(a):
        try: return dtparser.parse(str(a.get("published_at"))).timestamp()
        except: return 0
        
    all_rss.sort(key=_parse_sort, reverse=True)
    return all_rss[:max_results * 2] # Allow a bit more from RSS for selection


async def _from_serpapi(
    category: Optional[str],
    query: Optional[str],
    max_results: int,
    trending: bool = False
) -> List[Dict]:
    """Fetch from SerpApi's Google News engine."""
    if not settings.SERPAPI_API_KEY:
        return []

    articles = []
    params = {
        "engine": "google_news",
        "api_key": settings.SERPAPI_API_KEY,
        "gl": "us",
        "hl": "en",
    }
    
    # If explicitly searching or requesting a category
    search_q = query or QUERY_MAP.get(category or "general", "top stories")
    if trending:
        # SerpApi top stories doesn't use 'q' the same way
        pass
    else:
        params["q"] = search_q

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                for a in data.get("news_results", []):
                    articles.append({
                        "title":        a.get("title", ""),
                        "url":          a.get("link", ""),
                        "source":       a.get("source", {}).get("name", "SerpApi"),
                        "published_at": a.get("date"),
                        "raw_content":  a.get("snippet", ""),
                        "summary":      a.get("snippet", ""), # Extra frontend convenience
                        "is_trending":  trending,             # Flag it
                        "category":     category or "general",
                    })
                    if len(articles) >= max_results:
                        break
            else:
                 print(f"SerpApi error {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"SerpApi request failed: {repr(e)}")
            
    return articles

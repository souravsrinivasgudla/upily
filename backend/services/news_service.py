"""
NewsService — fetches raw articles for one category from RSS feeds, with
GNews / NewsAPI / SerpAPI as optional top-ups when RSS returns too little.

Every article is normalised to:
    {title, url, source, published_at (aware datetime | None), content, summary, category}
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from config import settings
from services.dates import is_fresh, parse_date
from services.text import clean_excerpt

log = logging.getLogger(__name__)

CATEGORIES = ["technology", "india", "world", "science", "business", "health", "entertainment", "sports"]

MIN_RSS_RESULTS = 8          # below this, top up from the keyed APIs
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; UpilyBot/1.0; +https://upily.app)"}

RSS_FEEDS: Dict[str, List[str]] = {
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
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.theguardian.com/uk/business/rss",
    ],
    "health": [
        "https://www.healthline.com/rss/health-news",
        "https://feeds.npr.org/1128/rss.xml",
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
}

# The Hindu — direct RSS with full excerpts, one feed per section
THE_HINDU_FEEDS = {
    "technology":    "https://www.thehindu.com/sci-tech/technology/feeder/default.rss",
    "india":         "https://www.thehindu.com/news/national/feeder/default.rss",
    "world":         "https://www.thehindu.com/news/international/feeder/default.rss",
    "science":       "https://www.thehindu.com/sci-tech/science/feeder/default.rss",
    "business":      "https://www.thehindu.com/business/feeder/default.rss",
    "health":        "https://www.thehindu.com/sci-tech/health/feeder/default.rss",
    "entertainment": "https://www.thehindu.com/entertainment/feeder/default.rss",
    "sports":        "https://www.thehindu.com/sport/feeder/default.rss",
}
for _cat, _url in THE_HINDU_FEEDS.items():
    RSS_FEEDS.setdefault(_cat, []).append(_url)

# Short OR-queries: news APIs treat spaces as AND, so long keyword lists match nothing.
SEARCH_QUERIES: Dict[str, str] = {
    "india":         "India OR Delhi OR Mumbai",
    "technology":    "technology OR AI OR software",
    "world":         "world OR international OR diplomacy",
    "science":       "science OR research OR space",
    "business":      "business OR markets OR economy",
    "health":        "health OR medicine OR medical",
    "entertainment": "entertainment OR film OR music",
    "sports":        "sports OR football OR basketball",
}
# Native category names for top-headlines endpoints (NewsAPI has no "world")
GNEWS_CATEGORY   = {c: c for c in CATEGORIES} | {"india": "nation"}   # "nation" + country=in
NEWSAPI_CATEGORY = {c: c for c in CATEGORIES if c not in ("world", "india")}

# Used to drop articles that plainly belong to another section. Matched on whole words.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "india": [
        "india", "indian", "delhi", "new delhi", "mumbai", "bengaluru", "chennai", "kolkata",
        "hyderabad", "kerala", "tamil nadu", "karnataka", "maharashtra", "bihar", "uttar pradesh",
        "gujarat", "punjab", "kashmir", "modi", "bjp", "congress", "lok sabha", "rajya sabha",
        "chief minister", "supreme court", "high court", "rupee", "rbi", "isro",
    ],
    "technology": [
        "ai", "artificial intelligence", "software", "hardware", "tech", "app", "apps", "robot",
        "computer", "cyber", "data", "cloud", "startup", "silicon", "chip", "chips", "gpu", "llm",
        "machine learning", "algorithm", "developer", "programming", "gadget", "smartphone",
        "internet", "digital", "automation", "semiconductor", "openai", "google", "microsoft",
        "apple", "meta", "nvidia", "aws",
    ],
    "world": [
        "war", "conflict", "government", "president", "minister", "election", "treaty",
        "diplomacy", "sanctions", "military", "nato", "united nations", "international",
        "foreign", "refugee", "refugees", "protest", "coup", "crisis", "ceasefire",
        "invasion", "border", "summit", "bilateral", "nation", "country",
    ],
    "science": [
        "research", "study", "scientist", "scientists", "discovery", "space", "nasa", "planet",
        "galaxy", "climate", "biology", "physics", "chemistry", "genome", "dna", "fossil",
        "experiment", "laboratory", "species", "asteroid", "telescope", "quantum", "particle",
        "evolution", "ecology",
    ],
    "business": [
        "market", "markets", "stock", "stocks", "shares", "investor", "investors", "revenue",
        "profit", "ipo", "acquisition", "merger", "ceo", "venture", "economy", "gdp",
        "inflation", "interest rate", "bank", "finance", "trade", "tariff", "tariffs",
        "supply chain", "earnings", "fiscal", "nasdaq", "dow",
    ],
    "health": [
        "health", "medical", "doctor", "doctors", "hospital", "patient", "patients", "disease",
        "drug", "vaccine", "treatment", "cancer", "diabetes", "mental health", "surgery",
        "clinical", "fda", "pandemic", "virus", "bacteria", "nutrition", "fitness", "therapy",
        "symptom", "symptoms", "diagnosis", "pharmaceutical",
    ],
    "entertainment": [
        "movie", "film", "actor", "actress", "celebrity", "music", "album", "concert",
        "oscar", "oscars", "grammy", "grammys", "netflix", "disney", "hollywood", "tv show",
        "series", "streaming", "box office", "singer", "band", "fashion", "pop culture",
        "trailer", "premiere", "director",
    ],
    "sports": [
        "match", "team", "player", "players", "coach", "league", "championship", "tournament",
        "nfl", "nba", "mlb", "nhl", "fifa", "olympic", "olympics", "athlete", "football",
        "basketball", "baseball", "soccer", "tennis", "golf", "racing", "cricket", "rugby",
        "transfer", "draft", "playoffs",
    ],
}
_KEYWORD_RE = {
    cat: re.compile(r"\b(?:" + "|".join(re.escape(k) for k in kws) + r")\b", re.I)
    for cat, kws in CATEGORY_KEYWORDS.items()
}


def keyword_hits(text: str, category: str) -> int:
    return len(set(m.group(0).lower() for m in _KEYWORD_RE[category].finditer(text)))


def belongs_elsewhere(article: Dict, category: str) -> bool:
    """True when an article has no keyword for its own section but clearly matches another."""
    text = f"{article.get('title', '')} {article.get('content', '')}"
    if keyword_hits(text, category) > 0:
        return False
    # "india" is geographic and overlaps every topic section, so it never pulls stories away
    return any(keyword_hits(text, other) >= 2 for other in CATEGORIES
               if other not in (category, "india"))


# ── Sources ───────────────────────────────────────────────────────────────────

def _article(title, url, source, published, content, category) -> Optional[Dict[str, Any]]:
    title = clean_excerpt(title, 480)
    url = (url or "").strip()
    if not title or not url.startswith(("http://", "https://")) or len(url) > 2000:
        return None   # 2000 = Article.url column length (Postgres enforces it)
    content = clean_excerpt(content, 4000)
    return {
        "title":        title,
        "url":          url,
        "source":       (source or "").strip()[:200] or "Unknown",
        "published_at": parse_date(published),
        "content":      content,
        "summary":      clean_excerpt(content or title, 280),
        "category":     category,
    }


_SOURCE_NAMES = [
    ("BBC", "BBC News"), ("The Verge", "The Verge"), ("TechCrunch", "TechCrunch"),
    ("NYT", "The New York Times"), ("New York Times", "The New York Times"),
    ("Guardian", "The Guardian"), ("Al Jazeera", "Al Jazeera"),
]
# Feeds whose titles don't name the publisher (The Hindu's are "Technology News Today, …")
_SOURCE_BY_DOMAIN = {"thehindu.com": "The Hindu"}


def _source_name(feed_title: str, feed_url: str = "") -> str:
    for domain, name in _SOURCE_BY_DOMAIN.items():
        if domain in feed_url:
            return name
    for needle, name in _SOURCE_NAMES:
        if needle in feed_title:
            return name
    return feed_title or "RSS"


async def _from_rss(client: httpx.AsyncClient, category: str, per_feed: int) -> List[Dict]:
    async def _one(url: str) -> List[Dict]:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.info("RSS %s -> HTTP %s", url, resp.status_code)
                return []
            feed = feedparser.parse(resp.content)
            source = _source_name(feed.feed.get("title", ""), url)
            out = []
            for e in feed.entries[:per_feed]:
                a = _article(
                    e.get("title"), e.get("link"), source,
                    e.get("published") or e.get("updated"),
                    e.get("summary") or e.get("description"), category,
                )
                if a:
                    out.append(a)
            return out
        except Exception as e:
            log.info("RSS %s failed: %s", url, type(e).__name__)
            return []

    results = await asyncio.gather(*[_one(u) for u in RSS_FEEDS[category]])
    return [a for sub in results for a in sub]


async def _from_gnews(client: httpx.AsyncClient, category: str, max_results: int) -> List[Dict]:
    if not settings.GNEWS_API_KEY:
        return []
    try:
        resp = await client.get(
            "https://gnews.io/api/v4/top-headlines",
            params={"category": GNEWS_CATEGORY[category], "lang": "en",
                    "max": min(max_results, 10), "apikey": settings.GNEWS_API_KEY,
                    **({"country": "in"} if category == "india" else {})},
        )
        if resp.status_code != 200:
            log.warning("GNews HTTP %s", resp.status_code)
            return []
        out = []
        for a in resp.json().get("articles") or []:
            item = _article(
                a.get("title"), a.get("url"), (a.get("source") or {}).get("name") or "GNews",
                a.get("publishedAt"),
                f"{a.get('description') or ''} {a.get('content') or ''}", category,
            )
            if item:
                out.append(item)
        return out
    except Exception as e:
        log.warning("GNews failed: %s", type(e).__name__)
        return []


async def _from_newsapi(client: httpx.AsyncClient, category: str, max_results: int) -> List[Dict]:
    if not settings.NEWS_API_KEY:
        return []
    headers = {"X-Api-Key": settings.NEWS_API_KEY}   # header, so the key never appears in URLs
    try:
        if category in NEWSAPI_CATEGORY:
            resp = await client.get(
                "https://newsapi.org/v2/top-headlines", headers=headers,
                params={"category": NEWSAPI_CATEGORY[category], "language": "en",
                        "pageSize": max_results},
            )
        else:
            resp = await client.get(
                "https://newsapi.org/v2/everything", headers=headers,
                params={"q": SEARCH_QUERIES[category], "language": "en",
                        "sortBy": "publishedAt", "pageSize": max_results},
            )
        if resp.status_code != 200:
            log.warning("NewsAPI HTTP %s", resp.status_code)
            return []
        out = []
        for a in resp.json().get("articles") or []:
            item = _article(
                a.get("title"), a.get("url"), (a.get("source") or {}).get("name"),
                a.get("publishedAt"),
                f"{a.get('description') or ''} {a.get('content') or ''}", category,
            )
            if item:
                out.append(item)
        return out
    except Exception as e:
        log.warning("NewsAPI failed: %s", type(e).__name__)
        return []


async def _from_serpapi(client: httpx.AsyncClient, category: str, max_results: int) -> List[Dict]:
    if not settings.SERPAPI_API_KEY:
        return []
    try:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_news", "q": SEARCH_QUERIES[category],
                    "gl": "us", "hl": "en", "api_key": settings.SERPAPI_API_KEY},
        )
        if resp.status_code != 200:
            log.warning("SerpAPI HTTP %s", resp.status_code)
            return []
        out = []
        for a in (resp.json().get("news_results") or [])[:max_results]:
            item = _article(
                a.get("title"), a.get("link"), (a.get("source") or {}).get("name") or "Google News",
                a.get("date"), a.get("snippet"), category,
            )
            if item:
                out.append(item)
        return out
    except Exception as e:
        log.warning("SerpAPI failed: %s", type(e).__name__)
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def _sort_key(a: Dict) -> float:
    dt: Optional[datetime] = a.get("published_at")
    return dt.timestamp() if dt else 0.0   # undated articles sort last


def dedupe(articles: List[Dict]) -> List[Dict]:
    seen_titles, seen_urls, out = set(), set(), []
    for a in articles:
        t = re.sub(r"\W+", " ", a["title"].lower()).strip()
        if t in seen_titles or a["url"] in seen_urls:
            continue
        seen_titles.add(t)
        seen_urls.add(a["url"])
        out.append(a)
    return out


async def fetch_category(category: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Fresh, de-duplicated, newest-first articles for one category."""
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category: {category}")

    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=HTTP_HEADERS) as client:
        articles = await _from_rss(client, category, per_feed=max_results)
        fresh =[a for a in articles if is_fresh(a["published_at"], settings.FRESHNESS_HOURS)]

        if len(fresh) < MIN_RSS_RESULTS:
            extra = await asyncio.gather(
                _from_gnews(client, category, max_results),
                _from_newsapi(client, category, max_results),
                _from_serpapi(client, category, max_results),
            )
            articles += [a for sub in extra for a in sub]

    articles = [
        a for a in articles
        if is_fresh(a["published_at"], settings.FRESHNESS_HOURS)
        and not belongs_elsewhere(a, category)
    ]
    articles.sort(key=_sort_key, reverse=True)
    return dedupe(articles)[:max_results]

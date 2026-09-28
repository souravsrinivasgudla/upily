"""
Local news for an Indian state / union territory and, optionally, a district (hybrid sources).

  1. Newspaper feeds (quality, with excerpts) — The Hindu state feeds and The Hindu /
     Times of India city feeds. A city feed counts as district news for the district
     the city is in; state and city feeds also yield district stories that mention it.
  2. Google News location search (India edition; coverage down to any district) —
     headline-only, so only stories whose headline names the place are kept, and
     low-quality sources (job alerts, tax sites…) are filtered out.

Stories are stored as category 'local' with the location, so they open in the article
page like any other story. Results are cached per location for CACHE_TTL.
"""
import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.database import AsyncSessionLocal
from db.models import Article
from services import clustering, locations
from services.dates import is_fresh
from services.news_service import HTTP_HEADERS, _article, dedupe

log = logging.getLogger(__name__)

LOCAL_CATEGORY = "local"
FRESH_HOURS = 72          # local desks publish less often than national ones
CACHE_TTL = 20 * 60
MAX_PER_LEVEL = 24

HINDU = "https://www.thehindu.com"
TOI = "https://timesofindia.indiatimes.com/rssfeeds"

# State feeds: every story is news for that state
STATE_FEEDS: Dict[str, List[Tuple[str, str]]] = {
    "Andhra Pradesh": [("The Hindu", f"{HINDU}/news/national/andhra-pradesh/feeder/default.rss")],
    "Karnataka":      [("The Hindu", f"{HINDU}/news/national/karnataka/feeder/default.rss")],
    "Kerala":         [("The Hindu", f"{HINDU}/news/national/kerala/feeder/default.rss")],
    "Tamil Nadu":     [("The Hindu", f"{HINDU}/news/national/tamil-nadu/feeder/default.rss")],
    "Telangana":      [("The Hindu", f"{HINDU}/news/national/telangana/feeder/default.rss")],
}

# City feeds: (publisher, url, state, districts the city covers)
CITY_FEEDS: List[Tuple[str, str, str, List[str]]] = [
    ("The Hindu", f"{HINDU}/news/cities/bangalore/feeder/default.rss", "Karnataka", ["Bengaluru Urban"]),
    ("The Hindu", f"{HINDU}/news/cities/chennai/feeder/default.rss", "Tamil Nadu", ["Chennai"]),
    ("The Hindu", f"{HINDU}/news/cities/Hyderabad/feeder/default.rss", "Telangana", ["Hyderabad"]),
    ("The Hindu", f"{HINDU}/news/cities/Kochi/feeder/default.rss", "Kerala", ["Ernakulam"]),
    ("The Hindu", f"{HINDU}/news/cities/Madurai/feeder/default.rss", "Tamil Nadu", ["Madurai"]),
    ("The Hindu", f"{HINDU}/news/cities/Mangalore/feeder/default.rss", "Karnataka", ["Dakshina Kannada"]),
    ("The Hindu", f"{HINDU}/news/cities/puducherry/feeder/default.rss", "Puducherry", ["Puducherry"]),
    ("The Hindu", f"{HINDU}/news/cities/Thiruvananthapuram/feeder/default.rss", "Kerala", ["Thiruvananthapuram"]),
    ("The Hindu", f"{HINDU}/news/cities/Tiruchirapalli/feeder/default.rss", "Tamil Nadu", ["Tiruchirappalli"]),
    ("The Hindu", f"{HINDU}/news/cities/Vijayawada/feeder/default.rss", "Andhra Pradesh", ["NTR"]),
    ("The Hindu", f"{HINDU}/news/cities/Visakhapatnam/feeder/default.rss", "Andhra Pradesh", ["Visakhapatnam"]),
    ("The Hindu", f"{HINDU}/news/cities/Delhi/feeder/default.rss", "Delhi", []),   # [] = every district
    ("The Hindu", f"{HINDU}/news/cities/kozhikode/feeder/default.rss", "Kerala", ["Kozhikode"]),
    ("The Hindu", f"{HINDU}/news/cities/Coimbatore/feeder/default.rss", "Tamil Nadu", ["Coimbatore"]),
    ("The Times of India", f"{TOI}/-2128838597.cms", "Maharashtra", ["Mumbai City", "Mumbai Suburban"]),
    ("The Times of India", f"{TOI}/-2128839596.cms", "Delhi", []),
    ("The Times of India", f"{TOI}/-2128833038.cms", "Karnataka", ["Bengaluru Urban"]),
    ("The Times of India", f"{TOI}/-2128816011.cms", "Telangana", ["Hyderabad"]),
    ("The Times of India", f"{TOI}/2950623.cms", "Tamil Nadu", ["Chennai"]),
    ("The Times of India", f"{TOI}/-2128830821.cms", "West Bengal", ["Kolkata"]),
    ("The Times of India", f"{TOI}/-2128821991.cms", "Maharashtra", ["Pune"]),
    ("The Times of India", f"{TOI}/-2128821153.cms", "Gujarat", ["Ahmedabad"]),
    ("The Times of India", f"{TOI}/-2128819658.cms", "Uttar Pradesh", ["Lucknow"]),
    ("The Times of India", f"{TOI}/3012544.cms", "Rajasthan", ["Jaipur"]),
]

# Other ways the news names a district (cities, old names, spellings)
DISTRICT_ALIASES: Dict[str, List[str]] = {
    "Visakhapatnam": ["Vizag"], "NTR": ["Vijayawada"], "Ananthapuramu": ["Anantapur"],
    "Sri Potti Sriramulu Nellore": ["Nellore"], "YSR Kadapa": ["Kadapa", "Cuddapah"],
    "Tirupati": ["Tirumala"], "Krishna": ["Machilipatnam", "Krishna district"],
    "Dr. B.R. Ambedkar Konaseema": ["Konaseema", "Amalapuram"], "Kakinada": ["Kakinada"],
    "Bengaluru Urban": ["Bengaluru", "Bangalore"], "Bengaluru South": ["Ramanagara"],
    "Dakshina Kannada": ["Mangaluru", "Mangalore"], "Mysuru": ["Mysore"], "Belagavi": ["Belgaum"],
    "Kalaburagi": ["Gulbarga"], "Shivamogga": ["Shimoga"], "Ernakulam": ["Kochi", "Cochin"],
    "Thiruvananthapuram": ["Trivandrum"], "Kozhikode": ["Calicut"], "Tiruchirappalli": ["Tiruchi", "Trichy"],
    "Kanniyakumari": ["Kanyakumari", "Nagercoil"], "Thoothukudi": ["Tuticorin"],
    "Mumbai City": ["Mumbai"], "Mumbai Suburban": ["Mumbai"], "Ahilyanagar": ["Ahmednagar"],
    "Chhatrapati Sambhajinagar": ["Aurangabad", "Sambhajinagar"], "Dharashiv": ["Osmanabad"],
    "Gautam Buddha Nagar": ["Noida", "Greater Noida"], "Prayagraj": ["Allahabad"],
    "Kanpur Nagar": ["Kanpur"], "Gurugram": ["Gurgaon"], "Kamrup Metropolitan": ["Guwahati"],
    "Sahibzada Ajit Singh Nagar": ["Mohali"], "Hanumakonda": ["Hanamkonda"], "Ranga Reddy": ["Rangareddy"],
    "Medchal-Malkajgiri": ["Medchal", "Malkajgiri"], "Paschim Bardhaman": ["Asansol", "Durgapur"],
    "Purba Bardhaman": ["Bardhaman", "Burdwan"], "Kolkata": ["Calcutta"], "Khordha": ["Bhubaneswar"],
    "Sribhumi": ["Karimganj"], "Narmadapuram": ["Hoshangabad"],
}

# Google News sources/titles that aren't local reporting
LOW_QUALITY = re.compile(
    r"job|recruit|vacanc|result|admit card|sarkari|exam|cleartax|dekho|autopundit|biltrax|"
    r"share price|stock|ipo|shareholder|dividend|quarterly results|horoscope|astrolog|freejob|"
    r"gold rate|silver rate|petrol price|diesel price|fuel price|weather today|show ?times?\b|"
    r"e-?paper|edition\s*[-–]\s*\w+\s+\d|"   # newspaper edition index pages ("Guntur edition - Sep 28")
    r"jagran josh|shiksha|^\[\d+\]|---",   # last two: race-card listings ("[116] The Nalgonda Plate ---")
    re.I,
)

_cache: Dict[tuple, Tuple[float, dict]] = {}
_locks: Dict[tuple, asyncio.Lock] = {}


# ── Matching ──────────────────────────────────────────────────────────────────

def mention_terms(district: str) -> List[str]:
    """Words that, in a headline or excerpt, mean the story is about this district."""
    terms = {district, locations.search_name(district), *DISTRICT_ALIASES.get(district, [])}
    out = []
    for t in terms:
        t = t.replace(" district", "").strip()
        # Very short or common-word names ("Mon", "Mau", "Una", "Krishna") need "X district"
        out.append(f"{t} district" if len(t) <= 4 or t in {"Krishna", "Dang", "Mandi", "Siang"} else t)
    return sorted(set(out), key=len, reverse=True)


def mentions(article: dict, terms: List[str], headline_only: bool = False) -> bool:
    text = article["title"] if headline_only else f"{article['title']} {article.get('content') or ''}"
    return any(re.search(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", text, re.I) for t in terms)


def _strip_publisher(title: str, publisher: str) -> str:
    suffix = f" - {publisher}"
    return title[: -len(suffix)] if publisher and title.endswith(suffix) else title


# ── Fetching ──────────────────────────────────────────────────────────────────

async def _feed(client: httpx.AsyncClient, publisher: str, url: str) -> List[dict]:
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []
        out = []
        for e in feedparser.parse(resp.content).entries[:60]:
            a = _article(e.get("title"), e.get("link"), publisher, e.get("published") or e.get("updated"),
                         e.get("summary") or e.get("description"), LOCAL_CATEGORY)
            if a and is_fresh(a["published_at"], FRESH_HOURS):
                out.append(a)
        return out
    except Exception as e:
        log.info("Local feed %s failed: %s", url, type(e).__name__)
        return []


async def _google(client: httpx.AsyncClient, query: str, must_mention: List[str]) -> List[dict]:
    try:
        resp = await client.get("https://news.google.com/rss/search", params={
            "q": f"{query} when:3d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en",
        })
        if resp.status_code != 200:
            return []
        out = []
        for e in feedparser.parse(resp.content).entries[:60]:
            publisher = (e.get("source") or {}).get("title") or "Google News"
            title = _strip_publisher(e.get("title") or "", publisher)
            if LOW_QUALITY.search(publisher) or LOW_QUALITY.search(title):
                continue
            a = _article(title, e.get("link"), publisher, e.get("published"), "", LOCAL_CATEGORY)
            if a and is_fresh(a["published_at"], FRESH_HOURS) and mentions(a, must_mention, headline_only=True):
                a["summary"] = ""   # Google gives only the headline — don't repeat it as a summary
                out.append(a)
        return out
    except Exception as e:
        log.info("Google News local search failed: %s", type(e).__name__)
        return []


def _newest_first(items: List[dict]) -> List[dict]:
    return sorted(dedupe(items), key=lambda a: a["published_at"].timestamp() if a["published_at"] else 0, reverse=True)


async def gather(state: str, district: Optional[str]) -> Dict[str, List[dict]]:
    """Fetch and split into district-level and state-level stories (not yet stored)."""
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=HTTP_HEADERS) as client:
        paper_feeds = [(p, u, None) for p, u in STATE_FEEDS.get(state, [])]
        paper_feeds += [(p, u, ds) for p, u, st, ds in CITY_FEEDS if st == state]
        papers = await asyncio.gather(*[_feed(client, p, u) for p, u, _ in paper_feeds])

        google_state = _google(client, f'"{state}"', [state])
        if district:
            terms = mention_terms(district)
            google_district = _google(client, f'"{locations.search_name(district)}"', terms)
            g_state, g_district = await asyncio.gather(google_state, google_district)
        else:
            g_state, g_district, terms = await google_state, [], []

    district_items: List[dict] = []
    state_items: List[dict] = list(g_state)
    for (_, _, covers), items in zip(paper_feeds, papers):
        for a in items:
            city_match = covers is not None and district and (covers == [] or district in covers)
            if district and (city_match or mentions(a, terms)):
                district_items.append(a)
            else:
                state_items.append(a)
    district_items += g_district

    district_items = _newest_first(district_items)[:MAX_PER_LEVEL]
    taken = {a["url"] for a in district_items}
    state_items = [a for a in _newest_first(state_items) if a["url"] not in taken][:MAX_PER_LEVEL]
    return {"district": district_items, "state": state_items}


# ── Storage ───────────────────────────────────────────────────────────────────

async def _store(items: List[dict], country: str, state: str, district: Optional[str]) -> List[Article]:
    """Upsert by URL; returns stored rows in the given order (existing stories are reused)."""
    if not items:
        return []
    async with AsyncSessionLocal() as db:
        urls = [a["url"] for a in items]
        existing = {a.url: a for a in (await db.execute(select(Article).where(Article.url.in_(urls)))).scalars()}
        rows = []
        for a in items:
            row = existing.get(a["url"])
            if row is None:
                row = Article(
                    title=a["title"], url=a["url"], source=a["source"], category=LOCAL_CATEGORY,
                    published_at=a["published_at"], raw_content=a["content"], summary=a["summary"],
                    importance_score=0.5, tags=[], loc_country=country, loc_state=state, loc_district=district,
                )
                db.add(row)
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                    row = (await db.execute(select(Article).where(Article.url == a["url"]))).scalar_one_or_none()
                    if row is None:
                        continue
            rows.append(row)
        return rows


def collapse(rows: List[Article]) -> List[dict]:
    """
    One entry per story: several outlets covering the same local event (e.g. a crime
    reported by four papers) become one card with an "N outlets" count. Uses the same
    grouping rules as the national sections; rows are newest-first, so each group's
    newest version leads.
    """
    if not rows:
        return []
    mapping = clustering.cluster(rows) if len(rows) > 1 else {rows[0].id: rows[0].id}
    groups: Dict[int, List[Article]] = {}
    for r in rows:
        groups.setdefault(mapping[r.id], []).append(r)
    out = []
    for members in groups.values():
        lead = members[0]
        story = lead.to_dict(include_content=False)
        seen, coverage = {lead.source}, []
        for m in members[1:]:
            if m.source not in seen:
                seen.add(m.source)
                coverage.append({"id": m.id, "source": m.source, "title": m.title, "url": m.url})
        story["coverage"], story["coverage_count"] = coverage, len(seen)
        out.append(story)
    return out


async def get_local(state: str, district: Optional[str] = None, country: str = "IN") -> dict:
    key = (country, state, district)
    cached = _cache.get(key)
    if cached and time.monotonic() < cached[0]:
        return {**cached[1], "cached": True}

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache.get(key)
        if cached and time.monotonic() < cached[0]:
            return {**cached[1], "cached": True}
        found = await gather(state, district)
        district_rows = await _store(found["district"], country, state, district)
        state_rows = await _store(found["state"], country, state, None)
        result = {
            "location": {"country": country, "country_name": locations.country_name(country),
                         "state": state, "district": district},
            "district_stories": collapse(district_rows),
            "state_stories": collapse(state_rows),
            "sources": sorted({r.source for r in district_rows + state_rows if r.source}),
        }
        _cache[key] = (time.monotonic() + CACHE_TTL, result)
        if len(_cache) > 500:   # keep memory bounded
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                _cache.pop(k, None)
        return {**result, "cached": False}

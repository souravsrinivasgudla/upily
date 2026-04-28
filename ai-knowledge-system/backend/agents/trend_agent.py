"""
TrendAgent — scans stored articles and identifies trending topics.
Calls LLMService directly.
"""
import json
import re
import math
from datetime import datetime, timezone
from typing import List, Dict, Any

from services import llm_service

SYSTEM = (
    "You are a real-time trend analyst for a live news dashboard. "
    "Your job is to identify what topics are HOT and VIRAL right now — "
    "topics that are surging in coverage, breaking news, or generating the most buzz. "
    "Prioritise recency, volume of coverage, and social/political impact."
)


def _hotness_score(article: Dict) -> float:
    """
    Composite hotness = recency_decay × importance × trending_boost
    - Recency decay: exponential falloff over 20 hours (max 1.0 = just published)
    - Importance: LLM-rated 0.0–1.0
    - Trending boost: 1.5× if already marked is_trending
    """
    importance = float(article.get("importance_score", 0.5))
    is_trending = bool(article.get("is_trending", False))

    # Parse published_at
    pub_raw = article.get("published_at")
    recency = 0.5  # default mid-score if date unknown
    if pub_raw:
        try:
            from dateutil import parser as dtparser
            pub_dt = dtparser.parse(str(pub_raw))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600
            # Exponential decay: full score at 0h, ~0.37 at 20h
            recency = math.exp(-age_hours / 10)
        except Exception:
            pass

    score = recency * importance
    if is_trending:
        score *= 1.5
    return round(score, 4)


class TrendAgent:

    async def analyse(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not articles:
            return {"trends": [], "categories": {}, "top_articles": []}

        # ── Compute hotness for every article ─────────────────────────────────
        for a in articles:
            a["_hotness"] = _hotness_score(a)

        # Sort by hotness descending — feed the hottest to the LLM
        hot_articles = sorted(articles, key=lambda x: x["_hotness"], reverse=True)

        # ── Category counts ────────────────────────────────────────────────────
        category_counts: Dict[str, int] = {}
        for a in articles:
            cat = a.get("category", "general")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # ── Build LLM prompt with hotness context ──────────────────────────────
        lines = []
        for a in hot_articles[:60]:
            hotness_pct = int(a["_hotness"] * 100)
            trending_tag = " [TRENDING]" if a.get("is_trending") else ""
            lines.append(
                f"[hotness:{hotness_pct}%{trending_tag}] [{a.get('category','?')}] "
                f"{a.get('title','')} (URL: {a.get('url','')})"
            )
        headlines = "\n".join(lines)

        prompt = f"""You are analysing LIVE news articles sorted by HOTNESS (recency × importance).
Articles marked [TRENDING] or with high hotness% are breaking/viral right now.

Identify the TOP 5 topics that are HOTTEST and most widely covered RIGHT NOW.
Focus on: breaking news, viral events, multiple sources covering the same story, high-impact events.

Return ONLY valid JSON with this exact structure:
{{
  "trends": [
    {{
      "topic":       "concise topic name",
      "emoji":       "relevant emoji",
      "count":       number_of_articles_about_this_topic,
      "summary":     "one-sentence description of what's happening now",
      "reason":      "why this is trending/breaking RIGHT NOW",
      "description": "2-3 sentence overview with context",
      "related_news": [
        {{ "title": "exact headline from the list above", "url": "exact URL from above" }},
        {{ "title": "exact headline from the list above", "url": "exact URL from above" }}
      ]
    }}
  ]
}}

LIVE ARTICLES (sorted hottest first):
{headlines}"""

        raw    = await llm_service.chat(prompt, system=SYSTEM, max_tokens=1200)
        trends = _parse_trends(raw)

        # ── Fallback if LLM fails ──────────────────────────────────────────────
        if not trends:
            sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
            for cat, count in sorted_cats[:3]:
                cat_arts = [a for a in hot_articles if a.get("category") == cat]
                trends.append({
                    "topic":       f"Breaking {cat.capitalize()} News",
                    "emoji":       "🔥",
                    "count":       count,
                    "summary":     f"Top developing stories in {cat} right now.",
                    "reason":      f"High volume of recent {cat} coverage detected.",
                    "description": f"Multiple sources are actively reporting on {cat} developments. These are the freshest articles in this category.",
                    "related_news": [
                        {"title": a["title"], "url": a["url"]}
                        for a in cat_arts[:3]
                    ]
                })

        # ── Top articles = hottest overall (not just importance_score) ─────────
        top_articles = hot_articles[:10]

        return {
            "trends":      trends,
            "categories":  category_counts,
            "top_articles": [
                {
                    "id":       a.get("id"),
                    "title":    a.get("title"),
                    "category": a.get("category"),
                    "hotness":  a.get("_hotness"),
                }
                for a in top_articles
            ],
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_trends(raw: str) -> List[Dict]:
    if not raw or "MOCK RESPONSE" in raw:
        return []

    try:
        # 1. Try direct JSON parse
        return json.loads(raw).get("trends", [])
    except Exception:
        pass

    try:
        # 2. Find JSON block via regex (handles markdown fences / preamble)
        m = re.search(r"(\{.*\})", raw, re.DOTALL)
        if m:
            return json.loads(m.group(1)).get("trends", [])
    except Exception:
        pass

    return []


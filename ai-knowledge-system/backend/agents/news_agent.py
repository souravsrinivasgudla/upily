"""
NewsAgent — fetches, deduplicates, and importance-ranks articles.
Uses NewsService directly (no MCP).
"""
import json
import re
from typing import List, Dict, Any

from services.news_service import fetch_all_categories
from services import llm_service

SYSTEM = (
    "You are a news quality analyst. "
    "Assess importance and filter out low-value or duplicate content."
)


class NewsAgent:

    async def fetch_and_rank(self, max_per_category: int = 10) -> List[Dict[str, Any]]:
        """Fetch all categories and rank by importance score."""
        articles = await fetch_all_categories(max_per_category)
        print(f"  [NewsAgent] Fetched {len(articles)} raw articles")
        ranked = await self._rank(articles)
        return ranked

    async def _rank(self, articles: List[Dict]) -> List[Dict]:
        if not articles:
            return []

        # Only send up to 30 articles to the LLM to keep token usage low
        batch = articles[:30]
        titles = "\n".join(
            f"{i+1}. [{a.get('category','?')}] {a.get('title','')}"
            for i, a in enumerate(batch)
        )
        prompt = (
            "Rate each article's importance 0.0–1.0 based on: global impact, novelty, public interest.\n"
            "Return ONLY a JSON array of numbers in the same order as the input. No explanation.\n\n"
            f"{titles}"
        )
        raw = await llm_service.chat(prompt, system=SYSTEM, max_tokens=300)
        scores = _parse_float_list(raw, len(batch))

        for i, a in enumerate(batch):
            a["importance_score"] = scores[i] if i < len(scores) else 0.5

        # Articles beyond the batch get a default score
        for a in articles[30:]:
            a.setdefault("importance_score", 0.5)

        return sorted(articles, key=lambda x: x["importance_score"], reverse=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_float_list(raw: str, expected: int) -> List[float]:
    try:
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            return [float(x) for x in json.loads(m.group())]
    except Exception:
        pass
    return [0.5] * expected

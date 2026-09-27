"""
NewsAgent — importance-ranks a batch of fetched articles with the LLM.
Falls back to a neutral score (newest-first order is kept) when the LLM is unavailable.
"""
import logging
from typing import Dict, List

from services import llm_service
from services.text import extract_json

log = logging.getLogger(__name__)

SYSTEM = (
    "You are a news quality analyst. "
    "Assess importance and filter out low-value or duplicate content."
)
MAX_BATCH = 30
DEFAULT_SCORE = 0.5


class NewsAgent:

    async def rank(self, articles: List[Dict]) -> List[Dict]:
        if not articles:
            return []

        batch = articles[:MAX_BATCH]
        scores = [DEFAULT_SCORE] * len(batch)

        if llm_service.is_llm_configured():
            titles = "\n".join(f"{i + 1}. {a['title']}" for i, a in enumerate(batch))
            prompt = (
                "Rate each headline's importance from 0.0 to 1.0 based on global impact, "
                "novelty and public interest.\n"
                f"Return ONLY a JSON array of exactly {len(batch)} numbers, in input order.\n\n"
                f"{titles}"
            )
            try:
                raw = await llm_service.chat(prompt, system=SYSTEM, max_tokens=300, temperature=0)
                scores = _parse_scores(raw, len(batch))
            except llm_service.LLMError as e:
                log.warning("Ranking skipped: %s", e)

        for a, s in zip(batch, scores):
            a["importance_score"] = s
        for a in articles[MAX_BATCH:]:
            a["importance_score"] = DEFAULT_SCORE

        # Stable sort keeps newest-first order among equal scores
        return sorted(articles, key=lambda x: x["importance_score"], reverse=True)


def _parse_scores(raw: str, expected: int) -> List[float]:
    values = extract_json(raw, expect=list) or []
    scores = []
    for v in values[:expected]:
        try:
            scores.append(min(max(float(v), 0.0), 1.0))
        except (TypeError, ValueError):
            scores.append(DEFAULT_SCORE)
    return scores + [DEFAULT_SCORE] * (expected - len(scores))

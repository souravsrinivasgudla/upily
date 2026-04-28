"""
SummarizerAgent — enriches each article with AI-generated insights.
Calls LLMService directly.
"""
import json
import re
from typing import Dict, Any

from services import llm_service

SYSTEM = (
    "You are an expert news analyst and educator. "
    "Explain news clearly, add context, and help readers understand "
    "why events matter and what background knowledge is relevant."
)


class SummarizerAgent:

    async def enrich(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds to the article dict:
          summary, deep_explanation, why_it_matters, background_info, tags
        """
        title   = article.get("title", "")
        content = (article.get("raw_content") or "")[:3000]

        prompt = f"""Analyse this news article and return a JSON object with exactly these keys:

{{
  "summary": "Engaging, click-worthy, and concise summary (MAX 2 sentences). Avoid generic phrases like 'This article discusses'.",
  "deep_explanation": "3-4 paragraphs with full context, technical details, and historical significance.",
  "why_it_matters": "1-2 paragraphs on real-world significance and direct impact on people or industry.",
  "background_info": "Educational background: key terms, history, and foundational concepts needed to understand this topic.",
  "tags": ["specific-entity", "topic-keyword", "location-or-event"]
}}

CRITICAL: Tags MUST be specific. Avoid generic tags like 'news', 'update', 'world', or the category name. 
Aim for 3-5 high-value searchable hashtags.

TITLE: {title}
CONTENT: {content}

Return ONLY valid JSON. No markdown fences."""

        raw    = await llm_service.chat(prompt, system=SYSTEM, max_tokens=1200)
        parsed = _parse_json(raw)

        if parsed:
            article.update(parsed)
        else:
            article.setdefault("summary",         title)
            article.setdefault("deep_explanation", content[:500])
            article.setdefault("why_it_matters",   "")
            article.setdefault("background_info",  "")
            article.setdefault("tags",             [])

        return article


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Dict | None:
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return None

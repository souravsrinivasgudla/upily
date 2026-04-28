"""
QAAgent — answers user questions.
Decision logic:
  1. Search memory (vector DB via SearchService)
  2. If low confidence → also search web
  3. Build context → call LLMService → return answer
"""
from typing import List, Dict, Any, Optional

from services import llm_service
from services.search_service import search_memory, search_web

SYSTEM = (
    "You are an intelligent news assistant with deep knowledge. "
    "Answer questions accurately and concisely with helpful context. "
    "Mention sources naturally when relevant. Be conversational but informative."
)

CONFIDENCE_THRESHOLD = 0.60


class QAAgent:

    async def answer(
        self,
        question: str,
        article_context: Optional[Dict] = None,
        db=None,
    ) -> Dict[str, Any]:
        # 1. Memory search with timeout to prevent hangs if DB is unreachable
        import asyncio
        try:
            memory_hits = await asyncio.wait_for(
                search_memory(question, top_k=5, db=db),
                timeout=2.0
            )
        except (asyncio.TimeoutError, Exception) as e:
            print(f"⚠️ Chat memory search skipped/timed out: {repr(e)}")
            memory_hits = []

        confidence  = memory_hits[0]["similarity"] if memory_hits else 0.0

        # 2. Web search disabled temporarily for maximum resilience
        web_hits: List[Dict] = []
        # if confidence < CONFIDENCE_THRESHOLD:
        #    web_hits = await search_web(question, max_results=3)

        # 3. Build prompt context
        prompt = _build_prompt(question, article_context, memory_hits, web_hits)

        # 4. Generate answer
        answer_text = await llm_service.chat(prompt, system=SYSTEM, max_tokens=800)

        return {
            "answer":          answer_text,
            "sources_used":    "memory+web" if web_hits else "memory",
            "confidence":      round(confidence, 3),
            "related_articles": [
                {"id": r["id"], "title": r["title"], "similarity": round(r["similarity"], 3)}
                for r in memory_hits[:3]
            ],
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_prompt(
    question: str,
    article_context: Optional[Dict],
    memory: List[Dict],
    web: List[Dict],
) -> str:
    parts = []

    if article_context:
        parts.append(
            "CURRENT ARTICLE CONTEXT:\n"
            f"Title: {article_context.get('title','')}\n"
            f"Summary: {article_context.get('summary','')}\n"
            f"Background: {article_context.get('background_info','')}"
        )

    if memory:
        mem_lines = "\n".join(
            f"- {r['title']}: {r.get('summary','')}" for r in memory[:3]
        )
        parts.append(f"RELEVANT STORED KNOWLEDGE:\n{mem_lines}")

    if web:
        web_lines = "\n".join(
            f"- {r['title']}: {r.get('snippet','')}" for r in web[:3]
        )
        parts.append(f"REAL-TIME WEB RESULTS:\n{web_lines}")

    parts.append(f"USER QUESTION: {question}")
    parts.append(
        "Answer the question using the above context. "
        "Be clear, helpful, and honest if you're uncertain."
    )
    return "\n\n".join(parts)

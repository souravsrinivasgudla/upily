from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import llm_service
import json
import re
from html import unescape

router = APIRouter()

class SummarizeRequest(BaseModel):
    title: str
    content: str


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _build_fallback_analysis(title: str, content: str) -> dict:
    cleaned = _strip_html(content)
    excerpt = cleaned[:1200]
    sentences = re.split(r"(?<=[.!?])\s+", cleaned) if cleaned else []
    summary = " ".join([s for s in sentences if s][:2]).strip()

    if not summary:
        summary = cleaned[:260].strip() or title

    deep_explanation = excerpt or "The article source did not include a readable excerpt. Open the original source for the full text."

    return {
        "summary": summary,
        "deep_explanation": deep_explanation,
        "why_it_matters": "AI analysis is unavailable until an LLM API key is configured in the backend .env file.",
        "background_info": "Original article excerpt shown instead of generated background context.",
        "ai_available": False,
    }

@router.post("/summarize")
async def summarize_live_article(req: SummarizeRequest):
    """Generate a full multi-part analysis for a live article using Groq."""
    text_to_summarize = req.content if req.content.strip() else req.title

    if not llm_service.is_llm_configured():
        return _build_fallback_analysis(req.title, text_to_summarize)
    
    prompt = f"""
    Analyze the following news article and provide a detailed 4-part report.
    CRITICAL INSTRUCTIONS:
    - DO NOT repeat the TITLE in your "summary".
    - The "summary" MUST be a detailed 5-sentence brief providing essential context.
    - The "deep_explanation" MUST be a comprehensive, 3-paragraph breakdown (min 200 words) addressing the facts and specifics.
    - The "why_it_matters" MUST explain the long-term impact and significance.
    - The "background_info" MUST provide historical context, "General Knowledge" (GK), and related facts about the topic.
    - Ensure all parts are complete and NO sentences are cut off.

    You MUST return your response as a valid JSON object with the following keys:
    - "summary": A rich, unique brief (exactly 5 sentences).
    - "deep_explanation": A detailed, multi-paragraph breakdown (minimum 3 paragraphs).
    - "why_it_matters": Perspective on significance and impact.
    - "background_info": Historical context and General Knowledge.

    Return ONLY the raw JSON.

    TITLE: {req.title}
    CONTENT TO ANALYZE: {text_to_summarize}
    """
    try:
        response_text = await llm_service.chat(prompt)
        if llm_service.is_mock_response(response_text):
            return _build_fallback_analysis(req.title, text_to_summarize)

        # Attempt to extract JSON from the LLM output
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            data["ai_available"] = True
            return data
        
        # Fallback if AI doesn't return JSON
        return {
            "summary": response_text[:200] + "...",
            "deep_explanation": response_text,
            "why_it_matters": "Analysis pending...",
            "background_info": "Context pending...",
            "ai_available": True,
        }
    except Exception as e:
        print(f"❌ AI Analysis failed: {repr(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate AI analysis.")

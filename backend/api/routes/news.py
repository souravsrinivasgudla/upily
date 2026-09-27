from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.orchestrator import OrchestratorAgent, PipelineBusy, RefreshCooldown, pipeline_running
from api.deps import analyze_limit, refresh_limit, require_admin
from db.database import get_db
from db.models import Article
from services import llm_service
from services.news_service import CATEGORIES

router = APIRouter()

# Undated articles sort by when we fetched them
_sort_date = func.coalesce(Article.published_at, Article.fetched_at)


def _check_category(category: str) -> str:
    category = category.lower()
    if category not in CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Unknown category '{category}'")
    return category


@router.get("/categories")
async def list_categories():
    return {"categories": CATEGORIES}


@router.get("/news")
async def list_news(
    category: Optional[str] = Query(None),
    trending: Optional[bool] = Query(None),
    page:  int = Query(1, ge=1, le=1000),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    q = select(Article)
    if category:
        q = q.where(Article.category == _check_category(category))
    if trending is not None:
        q = q.where(Article.is_trending == trending)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(
        q.order_by(desc(_sort_date), desc(Article.importance_score))
         .offset((page - 1) * limit).limit(limit)
    )).scalars().all()

    return {
        "articles": [a.to_dict(include_content=False) for a in rows],
        "page": page,
        "limit": limit,
        "total": total,
    }


@router.post("/news/refresh/{category}", dependencies=[Depends(refresh_limit)])
async def refresh_category(category: str, db: AsyncSession = Depends(get_db)):
    """
    Fetch fresh articles for one category and add them. Never deletes first, is
    rate-limited per client and per category, and returns quickly — AI analysis
    of the new articles continues in the background.
    """
    category = _check_category(category)
    try:
        added = await OrchestratorAgent().refresh_category(category)
    except RefreshCooldown as e:
        raise HTTPException(status_code=429, detail=f"{category.title()} was refreshed moments ago. "
                            f"Try again in {e.retry_after}s.", headers={"Retry-After": str(e.retry_after)})
    except PipelineBusy:
        raise HTTPException(status_code=409, detail="An update is already running. Try again in a minute.")

    rows = (await db.execute(
        select(Article).where(Article.category == category)
        .order_by(desc(_sort_date), desc(Article.importance_score)).limit(20)
    )).scalars().all()
    return {
        "category": category,
        "added": added,
        "analysis_pending": bool(added) and llm_service.is_llm_configured(),
        "articles": [a.to_dict(include_content=False) for a in rows],
    }


@router.get("/news/{article_id}")
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found — it may have been archived.")
    return article.to_dict()


@router.post("/news/{article_id}/analyze", dependencies=[Depends(analyze_limit)])
async def analyze_article(article_id: int):
    """
    Generate the AI analysis for a stored article, server-side, from its stored text.
    Idempotent: returns the saved analysis if it already exists.
    """
    if not llm_service.is_llm_configured():
        raise HTTPException(status_code=503, detail="AI analysis is not configured on this server.")
    try:
        article = await OrchestratorAgent().analyze_article(article_id)
    except llm_service.LLMError:
        raise HTTPException(status_code=502, detail="The AI service is unavailable right now. Try again shortly.")
    if not article:
        raise HTTPException(status_code=404, detail="Article not found — it may have been archived.")
    return article.to_dict()


# ── Admin only (requires X-Admin-Token: $ADMIN_API_KEY) ──────────────────────

class EnrichRequest(BaseModel):
    summary:          str = Field(min_length=1, max_length=1000)
    deep_explanation: str = Field(min_length=1, max_length=8000)
    why_it_matters:   Optional[str] = Field(None, max_length=4000)
    background_info:  Optional[str] = Field(None, max_length=4000)
    tags:             Optional[list[str]] = Field(None, max_length=8)


@router.patch("/news/{article_id}/enrich", dependencies=[Depends(require_admin)])
async def enrich_article(article_id: int, req: EnrichRequest, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    article.summary          = req.summary
    article.deep_explanation = req.deep_explanation
    article.why_it_matters   = req.why_it_matters
    article.background_info  = req.background_info
    if req.tags is not None:
        article.tags = req.tags
    await db.commit()
    return {"status": "enriched", "article_id": article_id}


@router.post("/admin/pipeline", dependencies=[Depends(require_admin)])
async def run_pipeline_now():
    if pipeline_running():
        raise HTTPException(status_code=409, detail="Pipeline already running")
    return await OrchestratorAgent().run_pipeline()

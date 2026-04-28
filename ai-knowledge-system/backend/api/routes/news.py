from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from pydantic import BaseModel
from typing import Optional
import asyncio

from db.database import get_db
from db.models import Article

router = APIRouter()


class EnrichRequest(BaseModel):
    summary: str
    deep_explanation: str
    why_it_matters: Optional[str] = None
    background_info: Optional[str] = None
    tags: Optional[list[str]] = None


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/news  — serve articles from DB only
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/news")
async def list_news(
    category: Optional[str] = Query(None),
    trending: Optional[bool] = Query(None),
    page:  int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    q = select(Article).order_by(desc(Article.published_at), desc(Article.importance_score))

    if category:
        q = q.where(Article.category == category)
    if trending is not None:
        q = q.where(Article.is_trending == trending)

    q = q.offset((page - 1) * limit).limit(limit)

    result   = await db.execute(q)
    articles = result.scalars().all()

    return {
        "articles": [a.to_dict() for a in articles],
        "page":     page,
        "limit":    limit,
        "source":   "db",
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/news/refresh/{category}
# Deletes ALL articles for that category, runs pipeline, returns new articles
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/news/refresh/{category}")
async def refresh_category(category: str, db: AsyncSession = Depends(get_db)):
    """
    Hard-refresh a single category:
      1. Delete every article in that category from the DB
      2. Fetch + rank + enrich fresh articles (waits for completion)
      3. Return the new articles directly
    """
    from sqlalchemy import delete as sql_delete
    from agents.orchestrator import OrchestratorAgent

    # Step 1: wipe the category
    await db.execute(sql_delete(Article).where(Article.category == category))
    await db.commit()
    print(f"[Refresh] Cleared all {category} articles from DB")

    # Step 2: run pipeline synchronously (await — not background task)
    await OrchestratorAgent().run_category_pipeline(category)

    # Step 3: return the freshly stored articles
    result = await db.execute(
        select(Article)
        .where(Article.category == category)
        .order_by(desc(Article.published_at), desc(Article.importance_score))
        .limit(20)
    )
    articles = result.scalars().all()
    return {
        "articles": [a.to_dict() for a in articles],
        "category": category,
        "count":    len(articles),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/news/{article_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/news/{article_id}")
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    result  = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/news/{article_id}/enrich
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/news/{article_id}/enrich")
async def enrich_article(
    article_id: int,
    req: EnrichRequest,
    db: AsyncSession = Depends(get_db),
):
    res     = await db.execute(select(Article).where(Article.id == article_id))
    article = res.scalar_one_or_none()
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

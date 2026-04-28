from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from agents.qa_agent import QAAgent

router   = APIRouter()
qa_agent = QAAgent()


class ChatRequest(BaseModel):
    question:     str
    article_id:   Optional[str]  = None
    article_data: Optional[dict] = None


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    article_ctx = req.article_data
    
    # If ID is provided (as a numeric string), try loading from DB
    if req.article_id and req.article_id.isdigit():
        from sqlalchemy import select
        from db.models import Article
        res = await db.execute(select(Article).where(Article.id == int(req.article_id)))
        a   = res.scalar_one_or_none()
        if a:
            article_ctx = a.to_dict()

    return await qa_agent.answer(
        question        = req.question,
        article_context = article_ctx,
        db              = db,
    )

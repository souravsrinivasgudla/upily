from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.qa_agent import QAAgent
from api.deps import chat_limit
from db.database import get_db
from db.models import Article
from services import llm_service

router = APIRouter()
qa_agent = QAAgent()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question:   str = Field(min_length=1, max_length=1000)
    # Article context is always loaded server-side from the DB — clients can't inject it
    article_id: Optional[int] = None
    history:    List[ChatTurn] = Field(default_factory=list, max_length=12)


@router.post("/chat", dependencies=[Depends(chat_limit)])
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Question is empty")

    article_ctx = None
    if req.article_id is not None:
        article = await db.get(Article, req.article_id)
        if article:
            article_ctx = article.to_dict()

    try:
        return await qa_agent.answer(
            question=question,
            db=db,
            article_context=article_ctx,
            history=[t.model_dump() for t in req.history],
        )
    except llm_service.LLMNotConfigured:
        raise HTTPException(status_code=503, detail="The AI assistant is not configured on this server.")
    except llm_service.LLMError:
        raise HTTPException(status_code=502, detail="The AI service is unavailable right now. Try again shortly.")

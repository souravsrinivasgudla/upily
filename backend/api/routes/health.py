from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config import settings
from db.database import engine

router = APIRouter()


@router.get("/health")
async def health():
    db_ok = True
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    body = {
        "status": "ok" if db_ok else "degraded",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "ok" if db_ok else "unavailable",
        "features": {
            "ai_analysis": settings.llm_configured,
            "chat":        settings.llm_configured,
            "trending":    bool(settings.GNEWS_API_KEY or settings.SERPAPI_API_KEY),
            "web_search":  True,   # DuckDuckGo fallback always available
        },
        "refresh_interval_hours": settings.FETCH_INTERVAL_HOURS,
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, health, news, trending
from config import settings
from db.database import engine, init_db
from scheduler.daily_pipeline import start_scheduler
from services.clustering import recluster
from services.tasks import cancel_all, spawn

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# httpx logs full request URLs at INFO — which would include API keys in query strings
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("upily")


async def _catch_up() -> None:
    """Group stories and finish any analysis a previous run didn't complete (e.g. rate limits)."""
    from agents.orchestrator import OrchestratorAgent
    await recluster()
    done = await OrchestratorAgent().analyze_pending(limit=200)
    if done:
        log.info("Startup catch-up: analysed %d stories", done)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    spawn(_catch_up(), name="startup-catch-up")
    scheduler = await start_scheduler()
    log.info("%s v%s started (LLM: %s%s)", settings.APP_NAME, settings.APP_VERSION,
             settings.LLM_PROVIDER, "" if settings.llm_configured else " — NOT CONFIGURED")
    yield
    scheduler.shutdown(wait=False)
    await cancel_all()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Upily — your daily news, explained. Refreshed every few hours.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)

app.include_router(health.router,   prefix="/api", tags=["health"])
app.include_router(news.router,     prefix="/api", tags=["news"])
app.include_router(chat.router,     prefix="/api", tags=["chat"])
app.include_router(trending.router, prefix="/api", tags=["trending"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=True)

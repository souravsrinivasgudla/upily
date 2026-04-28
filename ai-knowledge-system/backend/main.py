from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os

from api.routes import news, chat, trending, health, ai
from db.database import init_db
from scheduler.daily_pipeline import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    # Run the pipeline immediately on startup so DB is populated right away
    async def _initial_run():
        await asyncio.sleep(2)  # brief delay to let DB settle
        from agents.orchestrator import OrchestratorAgent
        await OrchestratorAgent().run_pipeline()
    asyncio.create_task(_initial_run())
    yield


app = FastAPI(
    title="AI Knowledge System",
    description="Personal knowledge system — news refreshed every 4 hours",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,   prefix="/api", tags=["health"])
app.include_router(news.router,     prefix="/api", tags=["news"])
app.include_router(chat.router,     prefix="/api", tags=["chat"])
app.include_router(trending.router, prefix="/api", tags=["trending"])
app.include_router(ai.router,       prefix="/api/ai", tags=["ai"])

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

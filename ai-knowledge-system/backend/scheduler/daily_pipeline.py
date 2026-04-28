from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import settings


def start_scheduler():
    scheduler = AsyncIOScheduler()

    async def _run():
        from agents.orchestrator import OrchestratorAgent
        await OrchestratorAgent().run_pipeline()

    # Single job: run every FETCH_INTERVAL_HOURS (default 4h)
    scheduler.add_job(
        _run,
        trigger=IntervalTrigger(hours=settings.FETCH_INTERVAL_HOURS),
        id="news_pipeline",
        replace_existing=True,
    )

    scheduler.start()
    print(f"[Scheduler] News pipeline runs every {settings.FETCH_INTERVAL_HOURS} hours.", flush=True)

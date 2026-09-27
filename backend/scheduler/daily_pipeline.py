import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from services.dates import utcnow

log = logging.getLogger(__name__)


async def _run_pipeline():
    from agents.orchestrator import OrchestratorAgent
    await OrchestratorAgent().run_pipeline()


async def start_scheduler() -> AsyncIOScheduler:
    """
    Run the pipeline every FETCH_INTERVAL_HOURS. On startup it runs immediately only
    if stored news is missing or older than the interval — so restarts and redeploys
    don't re-fetch and re-analyse everything (which costs LLM credits).
    """
    from agents.orchestrator import hours_since_last_fetch

    scheduler = AsyncIOScheduler(timezone="UTC")
    job_kwargs = {}

    if settings.RUN_PIPELINE_ON_STARTUP:
        age = await hours_since_last_fetch()
        if age is None or age >= settings.FETCH_INTERVAL_HOURS:
            job_kwargs["next_run_time"] = utcnow() + timedelta(seconds=5)
            log.info("Stored news is %s — running pipeline now",
                     "missing" if age is None else f"{age:.1f}h old")

    scheduler.add_job(
        _run_pipeline,
        trigger=IntervalTrigger(hours=settings.FETCH_INTERVAL_HOURS),
        id="news_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        **job_kwargs,
    )
    scheduler.start()
    log.info("Scheduler: news pipeline every %dh", settings.FETCH_INTERVAL_HOURS)
    return scheduler

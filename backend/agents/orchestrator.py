"""
OrchestratorAgent — the news pipeline.

Scheduled run (every FETCH_INTERVAL_HOURS):
  1. For each category: fetch → drop already-stored URLs → rank → store the top N
  2. Clean up: delete articles older than RETENTION_HOURS and cap each category
  3. Write AI analysis for articles that don't have it yet (outside the lock)

Manual category refresh does step 1 for one category. It never deletes before
new articles are safely stored, so a failed fetch can't empty a section.

All writes run under one asyncio.Lock, so the scheduler, startup run and manual
refreshes can't race each other into duplicate-URL errors.
"""
import asyncio
import logging
import time
from datetime import timedelta, timezone
from typing import List, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from agents.news_agent import NewsAgent
from agents.summarizer_agent import SummarizerAgent
from config import settings
from db.database import AsyncSessionLocal
from db.models import Article
from services import llm_service
from services.clustering import recluster
from services.dates import utcnow
from services.news_service import CATEGORIES, fetch_category
from services.tasks import spawn

log = logging.getLogger(__name__)

MAX_LOCAL_STORED = 3000

_write_lock = asyncio.Lock()
_analysis_locks: dict[int, asyncio.Lock] = {}
_last_refresh: dict[str, float] = {}


class PipelineBusy(Exception):
    """Another pipeline run is in progress."""


class RefreshCooldown(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"Refreshed recently; try again in {retry_after}s")
        self.retry_after = retry_after


class OrchestratorAgent:

    def __init__(self):
        self.news_agent = NewsAgent()
        self.summarizer = SummarizerAgent()

    # ── Full pipeline ─────────────────────────────────────────────────────────

    async def run_pipeline(self) -> dict:
        started = time.monotonic()
        log.info("Pipeline started")
        async with _write_lock:
            fetched = await asyncio.gather(
                *[self._fetch(cat) for cat in CATEGORIES], return_exceptions=True
            )
            stored: List[int] = []
            for cat, articles in zip(CATEGORIES, fetched):
                if isinstance(articles, Exception):
                    log.warning("Fetch failed for %s: %s", cat, type(articles).__name__)
                    continue
                try:
                    stored += await self._store(cat, articles)
                except Exception:   # one bad section must not stop the others
                    log.exception("Storing %s failed", cat)
            try:
                removed = await self._cleanup()
                await recluster()
            except Exception:
                log.exception("Cleanup failed")
                removed = 0

        analyzed = await self.analyze_pending()
        summary = {"stored": len(stored), "removed": removed, "analyzed": analyzed,
                   "seconds": round(time.monotonic() - started, 1)}
        log.info("Pipeline finished: %s", summary)
        return summary

    # ── Manual refresh of one category ────────────────────────────────────────

    async def refresh_category(self, category: str) -> int:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")

        elapsed = time.monotonic() - _last_refresh.get(category, float("-inf"))
        if elapsed < settings.REFRESH_COOLDOWN_SECONDS:
            raise RefreshCooldown(int(settings.REFRESH_COOLDOWN_SECONDS - elapsed) + 1)
        if _write_lock.locked():
            raise PipelineBusy()

        async with _write_lock:
            articles = await self._fetch(category)
            new_ids = await self._store(category, articles)
            await self._cleanup()
            try:
                await recluster()
            except Exception:
                log.exception("Story grouping failed")
            _last_refresh[category] = time.monotonic()

        if new_ids and llm_service.is_llm_configured():
            spawn(self.analyze_pending(ids=new_ids), name=f"analyze-{category}")
        return len(new_ids)

    # ── AI analysis ───────────────────────────────────────────────────────────

    async def analyze_pending(self, ids: Optional[List[int]] = None, limit: int = 60) -> int:
        """Analyse stored articles that have no analysis yet. Returns how many succeeded."""
        if not llm_service.is_llm_configured():
            return 0
        async with AsyncSessionLocal() as db:
            q = select(Article.id).where(Article.deep_explanation.is_(None))
            if not ids:
                # Local stories are analysed on demand (when opened) — readers can browse
                # hundreds of districts, and bulk-analysing all of them would drain the LLM quota
                q = q.where(Article.category != "local")
            if ids:
                q = q.where(Article.id.in_(ids))
            q = q.order_by(desc(Article.importance_score), desc(Article.fetched_at)).limit(limit)
            pending = (await db.execute(q)).scalars().all()

        done, consecutive_failures = 0, 0
        for n, article_id in enumerate(pending):
            if n:
                await asyncio.sleep(settings.ANALYSIS_PACE_SECONDS)   # stay under the LLM's per-minute limit
            try:
                if await self.analyze_article(article_id):
                    done += 1
                consecutive_failures = 0
            except llm_service.LLMRateLimited as e:
                log.warning("Analysis paused: %s — the rest waits for the next run", e)
                break
            except llm_service.LLMError as e:
                log.warning("Analysis failed for article %s: %s", article_id, e)
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    log.error("Stopping analysis after 3 consecutive LLM failures — check the "
                              "LLM key and model (LLM_PROVIDER=%s, model=%s)",
                              settings.LLM_PROVIDER, settings.llm_model)
                    break
            except Exception as e:   # e.g. article deleted by cleanup mid-analysis
                log.warning("Analysis skipped for article %s: %s", article_id, type(e).__name__)
        return done

    async def analyze_article(self, article_id: int) -> Optional[Article]:
        """Analyse one article (idempotent, one LLM call per article even if requested twice)."""
        lock = _analysis_locks.setdefault(article_id, asyncio.Lock())
        try:
            async with lock:
                async with AsyncSessionLocal() as db:
                    article = await db.get(Article, article_id)
                    if article is None or article.is_analyzed:
                        return article
                    result = await self.summarizer.analyze(
                        article.title, article.raw_content or article.summary or "", article.category or ""
                    )
                    article.summary          = result["summary"]
                    article.deep_explanation = result["deep_explanation"]
                    article.why_it_matters   = result["why_it_matters"]
                    article.background_info  = result["background_info"]
                    article.tags             = result["tags"]
                    try:
                        await db.commit()
                    except StaleDataError:   # archived by cleanup while the LLM was writing
                        await db.rollback()
                        return None
                    return article
        finally:
            if not lock.locked():
                _analysis_locks.pop(article_id, None)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _fetch(self, category: str) -> List[dict]:
        return await fetch_category(category, max_results=25)

    async def _store(self, category: str, articles: List[dict]) -> List[int]:
        if not articles:
            log.info("[%s] nothing fetched", category)
            return []

        async with AsyncSessionLocal() as db:
            urls = [a["url"] for a in articles]
            existing = set((await db.execute(
                select(Article.url).where(Article.url.in_(urls))
            )).scalars().all())
            new = [a for a in articles if a["url"] not in existing]
            if not new:
                log.info("[%s] no new articles", category)
                return []

            ranked = await self.news_agent.rank(new)
            ids: List[int] = []
            for a in ranked[: settings.ARTICLES_PER_CATEGORY]:
                row = Article(
                    title=a["title"], url=a["url"], source=a["source"], category=category,
                    published_at=a["published_at"], raw_content=a["content"],
                    summary=a["summary"], importance_score=a["importance_score"], tags=[],
                )
                db.add(row)
                try:
                    await db.commit()
                    ids.append(row.id)
                except IntegrityError:   # URL stored meanwhile by another process
                    await db.rollback()
                except SQLAlchemyError as e:   # e.g. a value too long for Postgres
                    await db.rollback()
                    log.warning("[%s] skipped one article: %s", category, type(e).__name__)
            log.info("[%s] stored %d new articles", category, len(ids))
            return ids

    async def _cleanup(self) -> int:
        removed = 0
        async with AsyncSessionLocal() as db:
            cutoff = utcnow() - timedelta(hours=settings.RETENTION_HOURS)
            res = await db.execute(delete(Article).where(Article.fetched_at < cutoff))
            removed += res.rowcount or 0

            for cat in CATEGORIES:
                keep = (
                    select(Article.id).where(Article.category == cat)
                    .order_by(desc(Article.fetched_at), desc(Article.id))
                    .limit(settings.MAX_STORED_PER_CATEGORY)
                )
                res = await db.execute(
                    delete(Article).where(Article.category == cat, Article.id.not_in(keep))
                )
                removed += res.rowcount or 0

            # Local stories: bounded overall (they're fetched per location, on demand)
            keep_local = (
                select(Article.id).where(Article.category == "local")
                .order_by(desc(Article.fetched_at), desc(Article.id)).limit(MAX_LOCAL_STORED)
            )
            res = await db.execute(
                delete(Article).where(Article.category == "local", Article.id.not_in(keep_local))
            )
            removed += res.rowcount or 0
            await db.commit()
        if removed:
            log.info("Cleanup removed %d old articles", removed)
        return removed


def pipeline_running() -> bool:
    return _write_lock.locked()


async def hours_since_last_fetch() -> Optional[float]:
    async with AsyncSessionLocal() as db:
        latest = (await db.execute(select(func.max(Article.fetched_at)))).scalar()
    if latest is None:
        return None
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return (utcnow() - latest).total_seconds() / 3600

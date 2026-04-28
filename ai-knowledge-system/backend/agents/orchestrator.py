"""
OrchestratorAgent — single pipeline that runs every 4 hours.

Flow:
  1. Delete all articles older than 4 hours (full replacement cycle)
  2. Fetch fresh articles per category from RSS/API
  3. Rank each category independently
  4. Store top 5 per category
  5. Enrich each article with AI (summary, tags, explanation)
"""
from datetime import datetime, timezone, timedelta

from agents.news_agent       import NewsAgent
from agents.summarizer_agent import SummarizerAgent
from db.database             import AsyncSessionLocal
from db.models               import Article
from services.search_service import embed_text
from services.news_service   import fetch_articles, sanitize_summary, CATEGORIES


ARTICLES_PER_CATEGORY = 5   # stored per category per cycle
FETCH_PER_CATEGORY    = 12  # fetched before ranking


class OrchestratorAgent:

    def __init__(self):
        self.news_agent = NewsAgent()
        self.summarizer = SummarizerAgent()

    async def run_pipeline(self):
        print(f"\n[Pipeline] Started — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

        async with AsyncSessionLocal() as db:
            from sqlalchemy import delete, select, or_, and_

            # ── Step 1: Remove all articles older than 4 hours ────────────────
            cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
            del_result = await db.execute(
                delete(Article).where(
                    or_(
                        Article.fetched_at < cutoff,
                        and_(Article.fetched_at == None, Article.published_at < cutoff),  # noqa: E711
                    )
                )
            )
            await db.commit()
            removed = del_result.rowcount
            if removed:
                print(f"  [Cleanup] Removed {removed} old articles")

            # ── Step 2: Fetch articles per category in parallel ───────────────
            print("  [Fetch] Fetching articles for all categories...")
            import asyncio
            fetch_tasks = [
                fetch_articles(category=cat, max_results=FETCH_PER_CATEGORY)
                for cat in CATEGORIES if cat != "general"
            ]
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            cat_results = {}
            for cat, result in zip([c for c in CATEGORIES if c != "general"], results):
                if isinstance(result, Exception):
                    print(f"  [Warning] Fetch failed for {cat}: {result}")
                    cat_results[cat] = []
                else:
                    cat_results[cat] = result

            total = sum(len(v) for v in cat_results.values())
            print(f"  [Fetch] Got {total} articles across {len(cat_results)} categories")

            # ── Step 3 & 4: Rank per category and store top N ─────────────────
            saved: list[Article] = []
            print("  [Store] Ranking and saving articles...")

            for cat, articles_data in cat_results.items():
                if not articles_data:
                    print(f"  [Skip] No articles for {cat}")
                    continue

                # Rank independently per category
                try:
                    ranked = await self.news_agent._rank(articles_data)
                except Exception as e:
                    print(f"  [Warning] Ranking failed for {cat}, using unranked: {e}")
                    ranked = articles_data

                cat_saved = 0
                for art_data in ranked[:ARTICLES_PER_CATEGORY]:
                    url = art_data.get("url", "")
                    if not url:
                        continue

                    # Skip duplicates
                    dup = await db.execute(select(Article).where(Article.url == url))
                    if dup.scalar_one_or_none():
                        continue

                    pub_at = _parse_dt(art_data.get("published_at")) or datetime.now(timezone.utc)

                    article = Article(
                        title            = art_data.get("title", ""),
                        url              = url,
                        source           = art_data.get("source", ""),
                        category         = cat,
                        published_at     = pub_at,
                        importance_score = art_data.get("importance_score", 0.5),
                        summary          = sanitize_summary(
                            art_data.get("raw_content") or art_data.get("title") or ""
                        ),
                        raw_content      = art_data.get("raw_content") or "",
                    )
                    db.add(article)
                    await db.commit()
                    await db.refresh(article)
                    saved.append(article)
                    cat_saved += 1

                print(f"  [Store] {cat}: {cat_saved} new articles")

            # ── Step 5: Enrich with AI ────────────────────────────────────────
            if saved:
                print(f"  [Enrich] Enriching {len(saved)} articles with AI...")
                for i, article in enumerate(saved):
                    try:
                        enriched = await self.summarizer.enrich(article.to_dict())
                        article.summary          = enriched.get("summary", article.summary)
                        article.deep_explanation = enriched.get("deep_explanation", "")
                        article.why_it_matters   = enriched.get("why_it_matters", "")
                        article.background_info  = enriched.get("background_info", "")
                        article.tags             = enriched.get("tags", [])
                        embed_input = f"{article.title} {article.summary} {' '.join(article.tags or [])}"
                        article.embedding = await embed_text(embed_input)
                        await db.commit()
                        print(f"  [Enrich] [{i+1}/{len(saved)}] {article.title[:60]}")
                    except Exception as e:
                        print(f"  [Enrich] Skipped {article.id}: {e}")

        print(f"[Pipeline] Done — {len(saved)} articles stored\n")

    async def run_category_pipeline(self, category: str):
        """
        Refresh a single category:
        - Fetch fresh articles from RSS/API (more than needed so we have variety)
        - Rank and store top 5 that aren't already in DB (by URL or title)
        - Enrich with AI
        Note: deletion of old articles is handled by the route before calling this.
        """
        print(f"\n[CategoryPipeline] Refreshing: {category}")

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select

            # Fetch more articles to ensure variety on repeat refreshes
            articles_data = await fetch_articles(category=category, max_results=25)
            # Keep only articles matching this category
            articles_data = [a for a in articles_data if a.get("category", category) == category]
            print(f"  [Fetch] {len(articles_data)} articles for {category}")

            if not articles_data:
                print(f"  [Skip] No articles found for {category}")
                return

            # Rank
            try:
                ranked = await self.news_agent._rank(articles_data)
            except Exception as e:
                print(f"  [Warning] Ranking failed: {e}")
                ranked = articles_data

            # Store top N — deduplicate by both URL and title
            saved = []
            seen_titles: set[str] = set()

            for art_data in ranked:
                if len(saved) >= ARTICLES_PER_CATEGORY:
                    break

                url   = art_data.get("url", "")
                title = art_data.get("title", "").strip().lower()

                if not url or not title:
                    continue

                # Skip if URL already in DB
                dup_url = await db.execute(select(Article).where(Article.url == url))
                if dup_url.scalar_one_or_none():
                    continue

                # Skip if we've already queued this title in this batch
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                pub_at = _parse_dt(art_data.get("published_at")) or datetime.now(timezone.utc)
                article = Article(
                    title            = art_data.get("title", ""),
                    url              = url,
                    source           = art_data.get("source", ""),
                    category         = category,
                    published_at     = pub_at,
                    importance_score = art_data.get("importance_score", 0.5),
                    summary          = sanitize_summary(art_data.get("raw_content") or art_data.get("title") or ""),
                    raw_content      = art_data.get("raw_content") or "",
                )
                db.add(article)
                await db.commit()
                await db.refresh(article)
                saved.append(article)

            print(f"  [Store] Saved {len(saved)} new {category} articles")

            if not saved:
                print(f"  [Warning] No new articles found for {category} — all were duplicates")
                return

            # Enrich
            for i, article in enumerate(saved):
                try:
                    enriched = await self.summarizer.enrich(article.to_dict())
                    article.summary          = enriched.get("summary", article.summary)
                    article.deep_explanation = enriched.get("deep_explanation", "")
                    article.why_it_matters   = enriched.get("why_it_matters", "")
                    article.background_info  = enriched.get("background_info", "")
                    article.tags             = enriched.get("tags", [])
                    embed_input = f"{article.title} {article.summary} {' '.join(article.tags or [])}"
                    article.embedding = await embed_text(embed_input)
                    await db.commit()
                    print(f"  [Enrich] [{i+1}/{len(saved)}] {article.title[:60]}")
                except Exception as e:
                    print(f"  [Enrich] Skipped {article.id}: {e}")

        print(f"[CategoryPipeline] Done — {category} refreshed with {len(saved)} articles\n")


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_dt(value):
    if not value:
        return None
    from dateutil import parser as dtparser
    _TZINFOS = {
        "EST": timezone(timedelta(hours=-5)), "EDT": timezone(timedelta(hours=-4)),
        "CST": timezone(timedelta(hours=-6)), "CDT": timezone(timedelta(hours=-5)),
        "MST": timezone(timedelta(hours=-7)), "MDT": timezone(timedelta(hours=-6)),
        "PST": timezone(timedelta(hours=-8)), "PDT": timezone(timedelta(hours=-7)),
        "GMT": timezone.utc, "UTC": timezone.utc,
    }
    try:
        return dtparser.parse(str(value), tzinfos=_TZINFOS)
    except Exception:
        return None
